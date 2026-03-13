#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════
#  claude-local-proxy — One-Command Setup Script
#  Works on: Debian/Ubuntu, Arch, macOS, Termux (Android)
#
#  Usage:
#    bash setup.sh
#  or:
#    curl -fsSL https://raw.githubusercontent.com/swordenkisk/claude-local-proxy/main/scripts/setup.sh | bash
# ════════════════════════════════════════════════════════════════
set -euo pipefail

# ── Colours ─────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'

log()  { echo -e "${BLUE}[INFO]${RESET} $*"; }
ok()   { echo -e "${GREEN}[OK]${RESET}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${RESET} $*"; }
err()  { echo -e "${RED}[ERROR]${RESET} $*"; exit 1; }

# ── Detect environment ───────────────────────────────────────────
IS_TERMUX=false
IS_MACOS=false
if [[ -n "${TERMUX_VERSION:-}" ]] || [[ -d "/data/data/com.termux" ]]; then
  IS_TERMUX=true
elif [[ "$(uname)" == "Darwin" ]]; then
  IS_MACOS=true
fi

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║      claude-local-proxy — Setup              ║${RESET}"
echo -e "${BOLD}║      github.com/swordenkisk/claude-local-proxy   ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════════════╝${RESET}"
echo ""

# ── Install system deps ──────────────────────────────────────────
log "Checking system dependencies..."

if $IS_TERMUX; then
  log "Termux detected — installing python, git..."
  pkg install -y python git 2>/dev/null || true
elif $IS_MACOS; then
  if ! command -v python3 &>/dev/null; then
    err "python3 not found. Install via: brew install python"
  fi
  if ! command -v git &>/dev/null; then
    err "git not found. Install via: brew install git"
  fi
else
  # Linux
  if command -v apt-get &>/dev/null; then
    sudo apt-get install -y python3 python3-pip python3-venv git 2>/dev/null || true
  elif command -v pacman &>/dev/null; then
    sudo pacman -S --noconfirm python python-pip git 2>/dev/null || true
  fi
fi

ok "System dependencies ready."

# ── Clone or update repo ─────────────────────────────────────────
INSTALL_DIR="${INSTALL_DIR:-$HOME/claude-local-proxy}"

if [[ -d "$INSTALL_DIR/.git" ]]; then
  log "Repository found at $INSTALL_DIR — pulling latest..."
  cd "$INSTALL_DIR"
  git pull --ff-only 2>/dev/null || warn "Could not pull; using existing version."
else
  log "Cloning repository to $INSTALL_DIR..."
  git clone https://github.com/swordenkisk/claude-local-proxy "$INSTALL_DIR"
  cd "$INSTALL_DIR"
fi

ok "Repository ready at $INSTALL_DIR"

# ── Virtual environment ──────────────────────────────────────────
VENV="$INSTALL_DIR/venv"
log "Setting up Python virtual environment..."
python3 -m venv "$VENV"
source "$VENV/bin/activate"
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
ok "Dependencies installed."

# ── .env setup ───────────────────────────────────────────────────
ENV_FILE="$INSTALL_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  cp "$INSTALL_DIR/.env.example" "$ENV_FILE"
  log "Created .env from template."
fi

# Prompt for API key if not set
if grep -q "sk-ant-YOUR_KEY_HERE" "$ENV_FILE"; then
  echo ""
  echo -e "${YELLOW}────────────────────────────────────────────────────${RESET}"
  echo -e "${BOLD}  Anthropic API Key Required${RESET}"
  echo -e "  Get yours at: ${BLUE}https://console.anthropic.com${RESET}"
  echo -e "${YELLOW}────────────────────────────────────────────────────${RESET}"
  echo ""
  read -rp "  Paste your API key (sk-ant-...): " apikey
  if [[ -n "$apikey" ]]; then
    sed -i.bak "s|sk-ant-YOUR_KEY_HERE|$apikey|g" "$ENV_FILE"
    rm -f "$ENV_FILE.bak"
    ok "API key saved to .env"
  else
    warn "No API key provided. Edit $ENV_FILE later before starting."
  fi
fi

# ── Create data directory ────────────────────────────────────────
mkdir -p "$INSTALL_DIR/data"

# ── Create launch script ─────────────────────────────────────────
LAUNCH="$INSTALL_DIR/start.sh"
cat > "$LAUNCH" << LAUNCH_EOF
#!/usr/bin/env bash
# Launch claude-local-proxy
cd "$INSTALL_DIR"
source "$VENV/bin/activate"
python -m src.server
LAUNCH_EOF
chmod +x "$LAUNCH"
ok "Created launch script: $LAUNCH"

# ── Done ─────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}════════════════════════════════════════════════════${RESET}"
echo -e "${GREEN}  ✅  Setup complete!${RESET}"
echo -e "${GREEN}════════════════════════════════════════════════════${RESET}"
echo ""
echo -e "  Start the server:"
echo -e "    ${BOLD}$LAUNCH${RESET}"
echo -e "  or:"
echo -e "    ${BOLD}cd $INSTALL_DIR && source venv/bin/activate && python -m src.server${RESET}"
echo ""
echo -e "  Open in browser: ${BLUE}http://127.0.0.1:8080${RESET}"
echo ""
echo -e "  Edit settings: ${BOLD}$ENV_FILE${RESET}"
echo ""
