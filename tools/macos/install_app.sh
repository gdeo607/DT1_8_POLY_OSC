#!/bin/bash
# Make one elekloader.app in your Elektron folder: elekloader's window that checks for updates when it
# opens, and has a "Check for updates" button (tools/elekloader_app.py).
#
#   tools/macos/install_app.sh [Elektron folder]        default: ~/Desktop/Elektron
#
# Older launchers it finds (elekloader.app in the Elektron folder and in "Digitakt 1", and the
# "Open elekloader" and "Update Digitakt mods" .command files) are moved to
# "Digitakt 1/4_bin/old_launchers_<date>", not deleted. Run it again after moving the repo.
set -euo pipefail

REPO=$(cd "$(dirname "$0")/../.." && pwd)
ELEKTRON=$(cd "${1:-$HOME/Desktop/Elektron}" && pwd)
DT1="$ELEKTRON/Digitakt 1"
for d in "$ELEKTRON/Digitakt 1"*; do      # the folder's name may end in a space
    if [[ -d $d ]]; then DT1=$d; break; fi
done
APP="$ELEKTRON/elekloader.app"
MARK=Contents/Resources/digi1_mods-launcher
OLD="$DT1/4_bin/old_launchers_$(date +%Y-%m-%d_%H%M)"

py=
for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import tkinter' 2>/dev/null; then py=$c; break; fi
done
[[ -n $py ]] || { echo "error: no Python with Tkinter: brew install python-tk"; exit 1; }

# an icon: the old launcher's (or the one this script gave the app before), if it has one
icon=
for a in "$APP" "$DT1/elekloader.app"; do
    if [[ -d $a ]]; then
        icon=$(ls "$a"/Contents/Resources/*.icns 2>/dev/null | head -1 || true)
        if [[ -n $icon ]]; then break; fi
    fi
done
tmp_icon=
if [[ -n $icon ]]; then tmp_icon=$(mktemp -d)/AppIcon.icns; cp "$icon" "$tmp_icon"; fi

# the old launchers to the bin
for a in "$APP" "$DT1/elekloader.app" "$ELEKTRON/Open elekloader.command" "$ELEKTRON/Update Digitakt mods.command"; do
    [[ -e $a ]] || continue
    if [[ -e $a/$MARK ]]; then
        rm -rf "$a"                           # this script's own app: replaced
    else
        mkdir -p "$OLD"
        dst="$OLD/$(basename "$(dirname "$a")" | sed 's/ *$//') - $(basename "$a")"   # two are called elekloader.app
        mv "$a" "$dst"
        echo "moved to the bin: $a"
    fi
done

# the app
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
touch "$APP/$MARK"
iconline=
if [[ -n $tmp_icon ]]; then
    mv "$tmp_icon" "$APP/Contents/Resources/AppIcon.icns"
    iconline="<key>CFBundleIconFile</key><string>AppIcon</string>"
fi
cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>elekloader</string>
<key>CFBundleDisplayName</key><string>elekloader</string>
<key>CFBundleIdentifier</key><string>local.digi1-mods.elekloader</string>
<key>CFBundleExecutable</key><string>elekloader</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleVersion</key><string>1</string>
<key>LSMinimumSystemVersion</key><string>10.13</string>
<key>NSHighResolutionCapable</key><true/>
$iconline
</dict></plist>
EOF
cat > "$APP/Contents/MacOS/elekloader" <<EOF
#!/bin/bash
# elekloader with updates: made by digi1_mods/tools/macos/install_app.sh
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:\$PATH"
export ELEKTRON_DIR="$ELEKTRON"
REPO="$REPO"
LOG="\$HOME/Library/Logs/elekloader.log"
if [[ ! -f \$REPO/tools/elekloader_app.py ]]; then
    osascript -e 'display alert "elekloader" message "digi1_mods is not at $REPO any more. Run tools/macos/install_app.sh again from where it is now."'
    exit 1
fi
for py in /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    if command -v "\$py" >/dev/null 2>&1 && "\$py" -c 'import tkinter' 2>/dev/null; then
        exec "\$py" "\$REPO/tools/elekloader_app.py" >> "\$LOG" 2>&1
    fi
done
osascript -e 'display alert "elekloader" message "No Python with Tkinter. In Terminal, run: brew install python-tk"'
exit 1
EOF
chmod +x "$APP/Contents/MacOS/elekloader"
touch "$APP"

echo "made: $APP"
echo "double-click elekloader in $ELEKTRON. It checks for updates when it opens; its log is ~/Library/Logs/elekloader.log"
