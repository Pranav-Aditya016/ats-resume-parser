param(
    [string]$PythonPath = "python"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Push-Location $ProjectRoot
try {
    & $PythonPath -m pip install --upgrade pip
    & $PythonPath -m pip install -r .\requirements.txt
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
