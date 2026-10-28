# LocalAudit AI Launcher Script
$UvPython = "$env:APPDATA\uv\python\cpython-3.11.17-windows-x86_64-none\python.exe"
$VenvRoot = "$env:LOCALAPPDATA\LocalAuditAI-venv"
$SitePackages = "$VenvRoot\Lib\site-packages"

if (-Not (Test-Path $SitePackages)) {
    Write-Host "Creating Python virtual environment at $VenvRoot..." -ForegroundColor Cyan
    uv venv $VenvRoot --python 3.11
    uv pip install --system-certs --python $VenvRoot -r requirements.txt
}

$env:PYTHONPATH = "$PSScriptRoot;$SitePackages"
Write-Host "Starting LocalAudit AI at http://127.0.0.1:8000 ..." -ForegroundColor Green
& $UvPython -m uvicorn main:app --host 127.0.0.1 --port 8000
