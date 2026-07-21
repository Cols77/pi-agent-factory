#!/bin/sh
# Installs a `pif` command into the npm global bin directory (the same
# directory `pi` itself already lives in, already on PATH) that launches
# `pi` with the factory-watch extension loaded, always operating on this
# repo regardless of which directory `pif` is invoked from.
#
# Run once, from anywhere, via Git Bash:
#   sh scripts/install-pif.sh
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -W)"

NPM_PREFIX_WIN="$(npm config get prefix)"
if [ -z "$NPM_PREFIX_WIN" ]; then
  echo "error: could not resolve npm global prefix (is npm installed?)" >&2
  exit 1
fi
if command -v cygpath > /dev/null 2>&1; then
  NPM_BIN="$(cygpath -u "$NPM_PREFIX_WIN")"
else
  NPM_BIN="$NPM_PREFIX_WIN"
fi
if [ ! -d "$NPM_BIN" ]; then
  echo "error: npm global bin dir does not exist: $NPM_BIN" >&2
  exit 1
fi

EXT_PATH="$REPO_ROOT/pi-ext/factory-watch/src/index.ts"

# POSIX shim (Git Bash / MSYS / any sh)
cat > "$NPM_BIN/pif" <<EOF
#!/bin/sh
cd "$REPO_ROOT" || exit 1
exec pi --extension "$EXT_PATH" "\$@"
EOF
chmod +x "$NPM_BIN/pif"

# cmd.exe shim
cat > "$NPM_BIN/pif.cmd" <<EOF
@echo off
cd /d "$REPO_ROOT"
pi --extension "$EXT_PATH" %*
EOF

# PowerShell shim
cat > "$NPM_BIN/pif.ps1" <<EOF
#!/usr/bin/env pwsh
Set-Location "$REPO_ROOT"
& pi --extension "$EXT_PATH" @args
exit \$LASTEXITCODE
EOF

echo "Installed pif -> $NPM_BIN (pif, pif.cmd, pif.ps1)"
echo "Try from any directory:"
echo "  pif -p \"/factory-tasks\" --mode json"
