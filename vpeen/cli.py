"""Linux VPS CLI and interactive management menu for VPeeN."""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .api import ApiError, VeePNApi
from .daemon import DEFAULT_CONFIG, load_config
from .upstream import check_exit_ip, probe_server_latency
from .utils import State

APP_DIR = os.environ.get("VPEEN_APP_DIR", "/opt/veepn")
CONFIG_PATH = os.environ.get("VPEEN_CONFIG", DEFAULT_CONFIG)
SERVICE = "veepn"


def _read_cfg(): return load_config(CONFIG_PATH)


def _save_cfg(cfg):
    Path(CONFIG_PATH).parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(cfg, f, indent=2)
    os.replace(tmp, CONFIG_PATH)
    try: os.chmod(CONFIG_PATH, 0o600)
    except OSError: pass


def _systemctl(*args, check=False):
    return subprocess.run(["systemctl", *args], text=True, capture_output=True, check=check)


def _sudo_prefix(): return [] if os.geteuid() == 0 else ["sudo"]


def _service(action):
    r = subprocess.run([*_sudo_prefix(), "systemctl", action, SERVICE], text=True)
    return r.returncode == 0


def _state_path(): return _read_cfg().get("state_path", "/var/lib/veepn/state.json")


async def locations():
    api = VeePNApi(State(_state_path()))
    all_locs, free = await api.locations()
    rows = sorted([l for l in free if l.get("region")], key=lambda x: x.get("region", ""))
    print("\nFree locations:")
    for i, loc in enumerate(rows, 1): print(f"  {i:2}. {loc.get('region',''):<12} {loc.get('countryCode','--'):<4} {loc.get('name','')}")
    return rows


async def test_region(region=None):
    cfg = _read_cfg(); api = VeePNApi(State(_state_path()))
    if not region or region == "optimal":
        loc = await api.optimal_location(); region = loc.get("region", "nl")
    servers = await api.server_list(region)
    measured = await probe_server_latency(servers[:5], budget=3)
    print(f"\n{region}: {len(servers)} upstream server(s)")
    for idx, ms in measured.items(): print(f"  server {idx + 1}: {ms} ms")
    try:
        ip = await check_exit_ip(servers[0], connect_timeout=8)
        print(f"  exit IP: {ip or 'unknown'}")
    except Exception as exc: print(f"  exit check failed: {exc}")


def show_status():
    r = _systemctl("is-active", SERVICE)
    print(f"Service: {r.stdout.strip() or 'inactive'}")
    r = _systemctl("show", SERVICE, "--property=ActiveEnterTimestamp,MainPID", "--no-pager")
    print(r.stdout.strip())
    cfg = _read_cfg(); print(f"Region: {cfg.get('region')} | SOCKS5: {cfg.get('bind')}:{cfg.get('socks_port')} | HTTP: {cfg.get('bind')}:{cfg.get('http_port')}")


def configure():
    cfg = _read_cfg()
    print("\nCurrent settings:", json.dumps(cfg, indent=2))
    for key, label in (("region", "Region (or optimal)"), ("bind", "Bind address"), ("socks_port", "SOCKS5 port"), ("http_port", "HTTP port"), ("proxy_user", "Proxy username"), ("proxy_pass", "Proxy password")):
        value = input(f"{label} [{cfg.get(key, '')}]: ").strip()
        if value:
            cfg[key] = int(value) if key.endswith("_port") else value
    if cfg["socks_port"] == cfg["http_port"]: print("Ports must be different."); return
    _save_cfg(cfg); print("Saved. Restart the service to apply changes.")


def uninstall():
    print("This will stop VPeeN and remove the service, program files, and wrapper.")
    answer = input("Type UNINSTALL to continue: ").strip()
    if answer != "UNINSTALL":
        print("Cancelled.")
        return
    cmd = "/usr/local/bin/veepn-uninstall"
    if not os.path.exists(cmd):
        print("Uninstall helper is missing. Reinstall with the updated install.sh first.")
        return
    subprocess.run([*_sudo_prefix(), "bash", cmd])


def update():
    if not os.path.isdir(os.path.join(APP_DIR, ".git")):
        print("Source checkout not found; reinstall from the official installer."); return
    cmd = [*_sudo_prefix(), "git", "-c", f"safe.directory={APP_DIR}", "-C", APP_DIR, "pull", "--ff-only"]
    if subprocess.run(cmd).returncode == 0:
        subprocess.run([*_sudo_prefix(), "bash", os.path.join(APP_DIR, "install.sh"), "--upgrade"])
        _service("restart")


def menu():
    while True:
        print("\n=== VPeeN Linux VPS ===")
        print("1) Status       2) Start        3) Stop")
        print("4) Restart      5) Locations    6) Select location")
        print("7) Ports/bind   8) Test         9) Logs")
        print("u) Update       x) Uninstall    0) Exit")
        try: choice = input("\nveepn> ").strip().lower()
        except (EOFError, KeyboardInterrupt): print(); return 0
        try:
            if choice == "1": show_status()
            elif choice == "2": _service("start")
            elif choice == "3": _service("stop")
            elif choice == "4": _service("restart")
            elif choice == "5": asyncio.run(locations())
            elif choice == "6":
                rows = asyncio.run(locations()); n = int(input("Number: "))
                if 1 <= n <= len(rows): cfg = _read_cfg(); cfg["region"] = rows[n-1]["region"]; _save_cfg(cfg); _service("restart")
            elif choice == "7": configure()
            elif choice == "8": asyncio.run(test_region(_read_cfg().get("region")))
            elif choice == "9": subprocess.run([*_sudo_prefix(), "journalctl", "-u", SERVICE, "-n", "80", "--no-pager"])
            elif choice == "u": update()
            elif choice == "x": uninstall()
            elif choice == "0": return 0
        except Exception as exc: print(f"Error: {exc}")


def build_parser():
    p = argparse.ArgumentParser(prog="veepn", description="Manage VPeeN on a Linux VPS")
    sub = p.add_subparsers(dest="cmd")
    for cmd in ("start", "stop", "restart", "status", "update", "uninstall", "locations", "configure", "logs"): sub.add_parser(cmd)
    t = sub.add_parser("test"); t.add_argument("region", nargs="?", default="optimal")
    s = sub.add_parser("select"); s.add_argument("region")
    return p


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv: return menu()
    args = build_parser().parse_args(argv)
    if args.cmd in ("start", "stop", "restart"): return 0 if _service(args.cmd) else 1
    if args.cmd == "status": show_status(); return 0
    if args.cmd == "update": update(); return 0
    if args.cmd == "uninstall": uninstall(); return 0
    if args.cmd == "locations": asyncio.run(locations()); return 0
    if args.cmd == "test": asyncio.run(test_region(args.region)); return 0
    if args.cmd == "configure": configure(); return 0
    if args.cmd == "logs": subprocess.run([*_sudo_prefix(), "journalctl", "-u", SERVICE, "-f"]); return 0
    if args.cmd == "select": cfg = _read_cfg(); cfg["region"] = args.region; _save_cfg(cfg); print(f"Selected {args.region}"); return 0
    return menu()

if __name__ == "__main__": raise SystemExit(main())
