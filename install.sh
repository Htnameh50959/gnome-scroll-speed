#!/usr/bin/env bash
# Installs the Scroll Speed GNOME extension (per user) and the scroll-speedd service (system).
set -euo pipefail
cd "$(dirname "$0")"

UUID=scroll-speed@hemanth
CONF="$HOME/.config/scroll-speed/factor"
EXT_DIR="$HOME/.local/share/gnome-shell/extensions/$UUID"

echo "==> Config: $CONF"
mkdir -p "$(dirname "$CONF")"
[ -f "$CONF" ] || echo 1 > "$CONF"

echo "==> Installing extension to $EXT_DIR"
mkdir -p "$EXT_DIR"
cp extension/metadata.json extension/extension.js extension/stylesheet.css "$EXT_DIR/"

echo "==> Installing daemon (needs sudo)"
sudo apt-get install -y python3-evdev
sudo install -m 755 daemon/scroll-speedd.py /usr/local/bin/scroll-speedd
sed "s|@CONFIG@|$CONF|" daemon/scroll-speedd.service \
    | sudo tee /etc/systemd/system/scroll-speedd.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now scroll-speedd
sudo systemctl restart scroll-speedd

echo "==> Enabling extension"
if ! gnome-extensions enable "$UUID" 2>/dev/null; then
    # On Wayland a brand-new extension is only discovered after re-login,
    # so mark it enabled now and it will load on next login.
    current=$(gsettings get org.gnome.shell enabled-extensions)
    if [[ "$current" != *"$UUID"* ]]; then
        if [[ "$current" == "@as []" || "$current" == "[]" ]]; then
            new="['$UUID']"
        else
            new="${current%]}, '$UUID']"
        fi
        gsettings set org.gnome.shell enabled-extensions "$new"
    fi
    echo "    Log out and back in to load the extension."
fi

echo "Done. Scroll speed: Quick Settings (top-right) -> mouse slider."
echo "Daemon status: systemctl status scroll-speedd"
