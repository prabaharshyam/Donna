#!/usr/bin/env bash
# Run Donna in the background on a Mac: starts at login, restarts if it crashes,
# and keeps the Mac awake while on mains power (it sleeps normally on battery).
#
#   ./deploy/mac/autostart.sh            install / refresh
#   ./deploy/mac/autostart.sh uninstall  remove
#
# Keep the project outside ~/Documents, ~/Desktop and ~/Downloads: macOS privacy rules stop
# background services from reading those folders.
set -euo pipefail
DIR="$(cd "$(dirname "$0")/../.." && pwd)"
LABEL=com.donna.server
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOGS="$HOME/Library/Logs/Donna"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
if [ "${1:-}" = uninstall ]; then
  rm -f "$PLIST"; echo "Donna auto-start removed."; exit 0
fi
case "$DIR" in "$HOME/Documents"*|"$HOME/Desktop"*|"$HOME/Downloads"*)
  echo "Move the Donna folder out of $DIR first (e.g. to ~/Donna): macOS blocks background access there." >&2; exit 1;;
esac

mkdir -p "$HOME/Library/LaunchAgents" "$LOGS"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/usr/bin/caffeinate</string><string>-s</string><string>$DIR/run.sh</string></array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>EnvironmentVariables</key><dict><key>TZ</key><string>Asia/Kolkata</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>15</integer>
  <key>StandardOutPath</key><string>$LOGS/donna.log</string>
  <key>StandardErrorPath</key><string>$LOGS/donna.log</string>
</dict>
</plist>
EOF
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Donna will now start at login and restart automatically. Logs: $LOGS/donna.log"
