#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════
#  install_service.sh — Install claude-local-proxy as a systemd
#  service so it starts automatically on boot.
#
#  Usage:
#    sudo bash scripts/install_service.sh
# ════════════════════════════════════════════════════════════════
set -euo pipefail

if [[ "$EUID" -ne 0 ]]; then
  echo "[ERROR] Run with sudo: sudo bash scripts/install_service.sh"
  exit 1
fi

# Auto-detect install directory (this script is in scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$(dirname "$SCRIPT_DIR")"
VENV="$INSTALL_DIR/venv"
SERVICE_NAME="claude-local-proxy"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# Detect the invoking user (not root)
REAL_USER="${SUDO_USER:-$(logname 2>/dev/null || echo 'nobody')}"

echo "[INFO] Installing $SERVICE_NAME as systemd service..."
echo "[INFO] Install dir : $INSTALL_DIR"
echo "[INFO] Run as user : $REAL_USER"
echo "[INFO] Venv        : $VENV"

if [[ ! -f "$VENV/bin/python" ]]; then
  echo "[ERROR] Virtual environment not found at $VENV"
  echo "        Run scripts/setup.sh first."
  exit 1
fi

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Claude Local Proxy — AI chat web UI
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
Restart=always
RestartSec=3
User=${REAL_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${VENV}/bin/python -m src.server
EnvironmentFile=${INSTALL_DIR}/.env
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl start  "$SERVICE_NAME"

echo ""
echo "✅ Service installed and started."
echo ""
echo "Commands:"
echo "  sudo systemctl status  $SERVICE_NAME"
echo "  sudo systemctl stop    $SERVICE_NAME"
echo "  sudo systemctl restart $SERVICE_NAME"
echo "  sudo journalctl -u     $SERVICE_NAME -f"
echo ""
echo "Open: http://127.0.0.1:8080"
