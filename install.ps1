# Standup installer (Windows) — fetches the latest release wheel and installs it.
$ErrorActionPreference = "Stop"

$repo = "v1-nce/standup"
$release = Invoke-RestMethod "https://api.github.com/repos/$repo/releases/latest"
$asset = $release.assets | Where-Object { $_.name -like "standup-*-py3-none-any.whl" } | Select-Object -First 1

if (-not $asset) {
    Write-Error "No release wheel found. Publish one at https://github.com/$repo/releases"
    exit 1
}

$wheel = Join-Path $env:TEMP ("standup-" + [guid]::NewGuid() + ".whl")
Write-Host "Downloading $($asset.browser_download_url)"
Invoke-WebRequest $asset.browser_download_url -OutFile $wheel

if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv tool install $wheel
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    python -m pip install --user $wheel
    Write-Host "If 'standup' isn't found, add %APPDATA%\Python\Scripts to your PATH."
} else {
    Write-Error "Need Python 3.12+ or uv."
    exit 1
}

Remove-Item $wheel

Write-Host ""
Write-Host "Standup is installed. Run it with:"
Write-Host "  standup"
