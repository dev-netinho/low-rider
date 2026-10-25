#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WORLD_FILE="$SCRIPT_DIR/worlds/carro_4x4.wbt"

if command -v webots >/dev/null 2>&1; then
  exec webots "$WORLD_FILE"
fi

USER_DIR=$(getent passwd "$(id -u)" | cut -d: -f6)
CACHED_WEBOTS="$USER_DIR/.cache/codex-webots-r2025a/webots"
CACHED_DEPS="$USER_DIR/.cache/codex-webots-deps"

if [ -x "$CACHED_WEBOTS" ]; then
  if command -v flatpak-spawn >/dev/null 2>&1; then
    exec flatpak-spawn --host env LD_LIBRARY_PATH="$CACHED_DEPS" "$CACHED_WEBOTS" "$WORLD_FILE"
  fi
  exec env LD_LIBRARY_PATH="$CACHED_DEPS" "$CACHED_WEBOTS" "$WORLD_FILE"
fi

printf '%s\n' \
  'Webots não encontrado.' \
  'Instale o Webots R2025a e execute novamente este arquivo.' >&2
exit 1
