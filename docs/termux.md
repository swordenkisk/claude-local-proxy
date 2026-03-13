# Termux (Android) Setup Guide

## Prerequisites

```bash
pkg update && pkg upgrade -y
pkg install python git
```

## Installation

```bash
git clone https://github.com/swordenkisk/claude-local-proxy
cd claude-local-proxy
pip install -r requirements.txt
cp .env.example .env
nano .env    # set ANTHROPIC_API_KEY=sk-ant-...
```

## Run

```bash
python -m src.server
```

Open your phone browser: `http://127.0.0.1:8080`

## Auto-start with Termux:Boot

```bash
mkdir -p ~/.termux/boot
echo '#!/data/data/com.termux/files/usr/bin/bash
cd ~/claude-local-proxy && source venv/bin/activate && python -m src.server &' > ~/.termux/boot/claude.sh
chmod +x ~/.termux/boot/claude.sh
```

## Access from other devices on Wi-Fi

```
BIND_ADDR=0.0.0.0
UI_AUTH_TOKEN=my-secret-token
```
Open `http://<phone-IP>:8080?token=my-secret-token` on another device.
Find your phone IP: `ip addr show wlan0`
