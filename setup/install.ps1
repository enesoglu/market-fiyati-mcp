param([string]$PythonPath = "python")
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
& $PythonPath -c "import sys; sys.exit(0 if sys.version_info >= (3,13) else 'Python 3.13+ is required')"
if ($LASTEXITCODE -ne 0) { throw "Choose a Python 3.13+ executable with -PythonPath." }
& $PythonPath -m venv (Join-Path $ProjectRoot ".venv")
if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed." }
$EnvironmentPython = Join-Path $ProjectRoot ".venv/Scripts/python.exe"
& $EnvironmentPython -m pip install -r (Join-Path $ProjectRoot "requirements.lock")
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
& $EnvironmentPython -m pip install --no-deps $ProjectRoot
if ($LASTEXITCODE -ne 0) { throw "Package installation failed." }
Write-Host "Installed. Generate your MCP client configuration with:"
Write-Host ('& "' + $EnvironmentPython + '" -m market_fiyati_mcp --client-config')
