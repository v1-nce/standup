# Standup installer (Windows) — fetches the latest release wheel and installs it.
$ErrorActionPreference = "Stop"

$repo = "v1-nce/standup"
$release = Invoke-RestMethod "https://api.github.com/repos/$repo/releases/latest"
$asset = $release.assets | Where-Object { $_.name -like "standup-*-py3-none-any.whl" } | Select-Object -First 1

if (-not $asset) {
    Write-Error "No release wheel found. Publish one at https://github.com/$repo/releases"
    exit 1
}

$tempDir = Join-Path $env:TEMP ([guid]::NewGuid())
New-Item -ItemType Directory -Path $tempDir | Out-Null
$wheel = Join-Path $tempDir $asset.name
Write-Host "Downloading $($asset.browser_download_url)"
Invoke-WebRequest $asset.browser_download_url -OutFile $wheel

Write-Host "Installing Standup..."
if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv tool install $wheel
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    python -m pip install --user $wheel
} else {
    Write-Error "Need Python 3.12+ to install Standup."
    exit 1
}
if ($LASTEXITCODE -ne 0) {
    Write-Error "Installation failed."
    exit 1
}

Remove-Item -Recurse -Force $tempDir

Write-Host ""
Write-Host "Standup is installed. Run it with:"
Write-Host "  standup"
Write-Host "If 'standup' isn't found, restart your terminal."
