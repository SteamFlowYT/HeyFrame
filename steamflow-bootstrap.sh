#!/usr/bin/env bash
# Bootstrap Hey Frame directly on Steam Frame via GitHub without a PC.
# Fetch the maintained source archive, then run its installation script.
set -Eeuo pipefail

REPO="SteamFlowYT/HeyFrame"
# Normal installations always use main. Explicit, narrowly allowlisted
# development branch installs are opt-in and never automatic.
REF="${HEY_FRAME_REF:-main}"
case "$REF" in
  main|optimize-v0.6.4) : ;;
  *) printf 'Unsupported Hey Frame source ref: %s\n' "$REF" >&2; exit 1 ;;
esac
for command_name in curl tar mktemp bash; do
  command -v "$command_name" >/dev/null 2>&1 || { printf 'Missing command: %s\n' "$command_name" >&2; exit 1; }
done

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/hey-frame.XXXXXXXX")"
cleanup() { rm -rf -- "$TMP_DIR"; }
trap cleanup EXIT

printf 'Downloading Hey Frame source from %s (%s)...\n' "$REPO" "$REF"
curl --fail --location --show-error --silent --retry 2 \
  --output "$TMP_DIR/source.tar.gz" "https://github.com/$REPO/archive/refs/heads/$REF.tar.gz"

# GitHub builds branch archives with a repo-branch root (HeyFrame-main).
# Check for an expected installer before running anything.
mkdir -p "$TMP_DIR/source"
tar -xzf "$TMP_DIR/source.tar.gz" -C "$TMP_DIR/source" --no-same-owner
INSTALL="$TMP_DIR/source/HeyFrame-${REF}/install.sh"
if [[ ! -f "$INSTALL" ]]; then
  printf 'Installer missing. Check that the repository has install.sh at its root.\n' >&2
  exit 1
fi

printf 'Running Hey Frame installer (it will not enable the microphone until you request it)...\n'
bash "$INSTALL"
