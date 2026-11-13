#!/usr/bin/env bash
set -euo pipefail
UUID=scroll-speed@hemanth

gnome-extensions disable "$UUID" 2>/dev/null || true
rm -rf "$HOME/.local/share/gnome-shell/extensions/$UUID"

sudo systemctl disable --now scroll-speedd 2>/dev/null || true
sudo rm -f /etc/systemd/system/scroll-speedd.service /usr/local/bin/scroll-speedd
sudo systemctl daemon-reload
echo "Removed. (Config left at ~/.config/scroll-speed)"
