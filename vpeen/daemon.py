"""Linux VPS daemon for VPeeN's local SOCKS5/HTTP proxy."""
from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import time
from pathlib import Path

from .api import ApiError, VeePNApi
from .localproxy import READ_LIMIT, LocalProxyServer, Stats, TunnelFactory
from .upstream import check_exit_ip
from .utils import State

DEFAULT_CONFIG = "/etc/veepn/config.json"


def load_config(path: str = DEFAULT_CONFIG) -> dict:
    defaults = {
        "region": "optimal",
        "bind": "127.0.0.1",
        "socks_port": 1080,
        "http_port": 8080,
        "proxy_user": "",
        "proxy_pass": "",
        "insecure_tls": False,
        "state_path": "/var/lib/veepn/state.json",
    }
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            defaults.update({k: v for k, v in raw.items() if k in defaults})
    except (OSError, ValueError):
        pass
    return defaults


def _log(path: str, line: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{stamp} {line}\n")
    except OSError:
        print(line, file=sys.stderr, flush=True)


async def run(config_path: str = DEFAULT_CONFIG) -> int:
    cfg = load_config(config_path)
    bind = str(cfg["bind"])
    socks_port, http_port = int(cfg["socks_port"]), int(cfg["http_port"])
    if socks_port == http_port:
        raise ValueError("SOCKS5 and HTTP ports must be different")
    user, password = str(cfg.get("proxy_user") or ""), str(cfg.get("proxy_pass") or "")
    if bind not in ("127.0.0.1", "localhost", "::1") and not (user and password):
        raise ValueError("public bind requires proxy_user and proxy_pass")

    state_path = str(cfg["state_path"])
    api = VeePNApi(State(state_path), insecure_tls=bool(cfg.get("insecure_tls")))
    region = str(cfg.get("region") or "optimal")
    if region == "optimal":
        loc = await api.optimal_location()
        region = loc.get("region") if loc.get("proxyType") == 0 else "nl"
    servers = await api.server_list(region)
    log_path = "/var/log/veepn/veepn.log"
    _log(log_path, f"starting region={region} bind={bind} socks={socks_port} http={http_port}")

    factory = TunnelFactory(api, servers, insecure_tls=bool(cfg.get("insecure_tls")),
                            log=lambda msg, lvl="info": _log(log_path, f"[{lvl}] {msg}"))
    factory.start_latency_probe()
    stats = Stats()
    auth = (user, password) if user and password else None
    proxy = LocalProxyServer(factory, stats, auth=auth)
    tasks: set[asyncio.Task] = set()

    def spawn(coro):
        task = asyncio.create_task(coro)
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        return task

    socks_srv = await asyncio.start_server(
        lambda r, w: spawn(proxy.handle_socks5(r, w)), bind, socks_port, limit=READ_LIMIT)
    http_srv = await asyncio.start_server(
        lambda r, w: spawn(proxy.handle_http(r, w)), bind, http_port, limit=READ_LIMIT)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    def shutdown(*_):
        stop.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown)

    try:
        _log(log_path, f"ready region={region} exit_ip=checking")
        try:
            ip = await asyncio.wait_for(check_exit_ip(servers[0], insecure_tls=bool(cfg.get("insecure_tls")), connect_timeout=6), 15)
            _log(log_path, f"exit_ip={ip or 'unknown'}")
        except Exception as exc:
            _log(log_path, f"exit_ip check failed: {exc}")
        await stop.wait()
    finally:
        socks_srv.close(); http_srv.close()
        for task in list(tasks): task.cancel()
        if tasks: await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.gather(socks_srv.wait_closed(), http_srv.wait_closed())
        await factory.stop()
        _log(log_path, "stopped cleanly")
    return 0


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="veepn-daemon")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)
    try:
        return asyncio.run(run(args.config))
    except (ApiError, OSError, ValueError) as exc:
        print(f"veepn-daemon: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
