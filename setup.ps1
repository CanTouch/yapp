# Set up YAPP (push-to-talk dictation) on Windows.
# Safe to re-run. Requires Python 3.9+ on PATH.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host ">> Creating virtualenv"
    python -m venv .venv
}

Write-Host ">> Installing Python packages"
.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt

Write-Host ">> Pre-downloading Whisper 'base' model"
.venv\Scripts\python.exe -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8'); print('model ready')"

Write-Host ""
Write-Host "Setup complete. Run with:  .venv\Scripts\python.exe dictate.py"
Write-Host "Hold Right Ctrl to dictate into the focused window."
