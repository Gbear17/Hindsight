#!/bin/bash
# Start / Restart all Hindsight services (idempotent)
set -e

SYSTEMD_UNITS=("hindsight-api.service" "hindsight-daemon.service" "hindsight-rebuild.timer")

systemctl --user daemon-reload || true

for unit in "${SYSTEMD_UNITS[@]}"; do
  if systemctl --user list-unit-files | grep -q "$unit"; then
    systemctl --user enable --now "$unit" >/dev/null 2>&1 || true
    systemctl --user restart "$unit" || true
  fi
done

# Fallback for daemon if systemd unit failed
if ! systemctl --user is-active --quiet hindsight-daemon.service; then
  SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
  APP_PATH="$SCRIPT_DIR/.."
  (cd "$APP_PATH" && nohup ./scripts/start_daemon.sh &>/dev/null &)
fi

notify-send "Hindsight" "Services started / restarted." -i utilities-terminal 2>/dev/null || true
