$ErrorActionPreference = "Stop"

$env:PYTHONUTF8 = "1"

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python venv not found at $python. Run: py -3.13 -m venv .venv"
}

Get-CimInstance Win32_Process |
    Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*webui.py*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

& $python (Join-Path $PSScriptRoot "webui.py")
