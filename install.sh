#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${VPEEN_APP_DIR:-/opt/veepn}"
SERVICE_USER="${VPEEN_USER:-veepn}"
REPO="https://github.com/arefhere51/veepn.git"

if [[ "${1:-}" != "--upgrade" ]]; then
  if [[ $EUID -ne 0 ]]; then
    echo "Run with: curl -fsSL https://raw.githubusercontent.com/arefhere51/veepn/main/install.sh | sudo bash"
    exit 1
  fi

  id "$SERVICE_USER" >/dev/null 2>&1 || \
    useradd --system \
            --home-dir /var/lib/veepn \
            --create-home \
            --shell /usr/sbin/nologin \
            "$SERVICE_USER"

  if [[ ! -d "$APP_DIR/.git" ]]; then
    rm -rf "$APP_DIR"
    git clone --depth 1 "$REPO" "$APP_DIR"
  else
    git -c safe.directory="$APP_DIR" -C "$APP_DIR" pull --ff-only
  fi
else
  if [[ $EUID -ne 0 ]]; then
    echo "Upgrade requires root."
    exit 1
  fi
fi

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip >/dev/null
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt" >/dev/null

install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 \
  /var/lib/veepn /var/log/veepn /etc/veepn

if [[ ! -f /etc/veepn/config.json ]]; then
  cat >/etc/veepn/config.json <<'JSON'
{
  "region": "optimal",
  "bind": "127.0.0.1",
  "socks_port": 1080,
  "http_port": 8080,
  "proxy_user": "",
  "proxy_pass": "",
  "insecure_tls": false,
  "state_path": "/var/lib/veepn/state.json"
}
JSON
  chown "$SERVICE_USER:$SERVICE_USER" /etc/veepn/config.json
  chmod 600 /etc/veepn/config.json
fi

cat >/etc/systemd/system/veepn.service <<UNIT
[Unit]
Description=VPeeN Linux VPS proxy daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python -m vpeen.daemon --config /etc/veepn/config.json
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=/var/lib/veepn /var/log/veepn

[Install]
WantedBy=multi-user.target
UNIT

cat >/usr/local/bin/veepn <<SCRIPT
#!/usr/bin/env bash
cd "$APP_DIR"
exec "$APP_DIR/.venv/bin/python" -m vpeen.cli "\$@"
SCRIPT
chmod 0755 /usr/local/bin/veepn

cat >/usr/local/bin/veepn-uninstall <<SCRIPT
#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$APP_DIR"
SERVICE_USER="$SERVICE_USER"

systemctl stop veepn.service 2>/dev/null || true
systemctl disable veepn.service 2>/dev/null || true
rm -f /etc/systemd/system/veepn.service
systemctl daemon-reload
rm -f /usr/local/bin/veepn

read -r -p "Delete configuration, cached credentials, and logs too? [y/N] " answer
if [[ "\$answer" =~ ^[Yy]$ ]]; then
  rm -rf /etc/veepn /var/lib/veepn /var/log/veepn
  userdel "$SERVICE_USER" 2>/dev/null || true
else
  echo "Configuration and data were preserved in /etc/veepn, /var/lib/veepn, and /var/log/veepn."
fi
rm -rf "$APP_DIR"
rm -f /usr/local/bin/veepn-uninstall
echo "VPeeN uninstalled."
SCRIPT
chmod 0755 /usr/local/bin/veepn-uninstall

chown -R "$SERVICE_USER:$SERVICE_USER" \
  "$APP_DIR" /var/lib/veepn /var/log/veepn

systemctl daemon-reload
systemctl enable veepn.service >/dev/null
systemctl restart veepn.service

echo
echo "VPeeN installed. Run: veepn"
