Param(
    [string]$EntryPoint = "scripts/run_gui.py"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $ProjectRoot

Write-Host "[1/4] Python 버전 확인"
python --version

Write-Host "[2/4] 의존성 설치"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

Write-Host "[3/4] PyInstaller 빌드"
python -m PyInstaller `
  --clean `
  --noconfirm `
  --onefile `
  --windowed `
  --name RUWifiViewMonitor `
  --paths src `
  $EntryPoint

Write-Host "[4/4] 완료"
Write-Host "실행 파일: .\dist\RUWifiViewMonitor.exe"
