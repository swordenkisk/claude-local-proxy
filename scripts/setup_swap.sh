#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════
#  setup_swap.sh — Create and activate a swap file
#  Useful on phones/RPi/VPS with 2-4 GB RAM to prevent OOM.
#  Requires root / sudo.
#
#  Usage:
#    sudo bash setup_swap.sh              # default 1 GB
#    sudo SWAP_MB=2048 bash setup_swap.sh # 2 GB
# ════════════════════════════════════════════════════════════════
set -euo pipefail

SWAP_MB="${SWAP_MB:-1024}"
SWAP_FILE="${SWAP_FILE:-/swapfile_claude_proxy}"

if [[ "$EUID" -ne 0 ]]; then
  echo "[ERROR] This script must be run as root (sudo)."
  exit 1
fi

# Check if already active
if swapon --show 2>/dev/null | grep -q "$SWAP_FILE"; then
  echo "[INFO] Swap already active at $SWAP_FILE"
  swapon --show
  exit 0
fi

echo "[INFO] Creating ${SWAP_MB}MB swap at $SWAP_FILE..."

# Create swap file
if command -v fallocate &>/dev/null; then
  fallocate -l "${SWAP_MB}M" "$SWAP_FILE"
else
  dd if=/dev/zero of="$SWAP_FILE" bs=1M count="$SWAP_MB" status=progress
fi

chmod 600 "$SWAP_FILE"
mkswap "$SWAP_FILE"
swapon "$SWAP_FILE"

echo "[OK] Swap activated: $(swapon --show)"
echo ""
echo "To make swap permanent across reboots, add this line to /etc/fstab:"
echo "  $SWAP_FILE swap swap defaults 0 0"
