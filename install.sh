#!/usr/bin/env sh
# Standup installer — fetches the latest release wheel and installs it.
set -e

REPO=v1-nce/standup

wheel_url=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
    | sed -n 's/.*"browser_download_url": *"\([^"]*standup-[^"]*py3-none-any\.whl\)".*/\1/p' \
    | head -n1)

if [ -z "$wheel_url" ]; then
    echo "No release wheel found. Publish one at https://github.com/$REPO/releases" >&2
    exit 1
fi

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

echo "Downloading $wheel_url"
curl -fsSL "$wheel_url" -o "$tmpdir/standup.whl"

echo "Installing Standup..."
if command -v uv >/dev/null 2>&1; then
    uv tool install "$tmpdir/standup.whl"
elif command -v python3 >/dev/null 2>&1; then
    python3 -m pip install --user "$tmpdir/standup.whl"
else
    echo "Need Python 3.12+ to install Standup." >&2
    exit 1
fi

echo
echo "Standup is installed. Run it with:"
echo "  standup"
echo "If 'standup' isn't found, restart your terminal."
