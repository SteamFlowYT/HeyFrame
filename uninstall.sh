#!/usr/bin/env bash
set -Eeuo pipefail
SYSTEMCTL="$(command -v systemctl || true)"
if [[ -z "$SYSTEMCTL" && -x /usr/bin/systemctl ]]; then SYSTEMCTL=/usr/bin/systemctl; fi
if [[ -n "$SYSTEMCTL" ]]; then
  "$SYSTEMCTL" --user disable --now hey-frame.service >/dev/null 2>&1 || true
  "$SYSTEMCTL" --user disable --now hey-frame-dashboard.service >/dev/null 2>&1 || true
  if "$SYSTEMCTL" --user is-active --quiet hey-frame.service 2>/dev/null || "$SYSTEMCTL" --user is-active --quiet hey-frame-dashboard.service 2>/dev/null; then
    echo 'Hey Frame is still running. Nothing removed.' >&2
    exit 1
  fi
fi
rm -f -- "$HOME/.local/bin/hey-frame" "$HOME/.local/bin/hey-frame-dashboard" "$HOME/.config/systemd/user/hey-frame.service" "$HOME/.config/systemd/user/hey-frame-dashboard.service"
if [[ -n "$SYSTEMCTL" ]]; then "$SYSTEMCTL" --user daemon-reload || true; fi
rm -rf -- "$HOME/.local/share/hey-frame-v3"
# The old v0.1/v0.2 folder is intentionally untouched; remove it manually if desired.
echo 'Hey Frame listener and dashboard removed. Personal quotes and notes are preserved.'
