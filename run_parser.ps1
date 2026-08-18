param(
    [string]$InputDir = ".\resumes",
    [string]$OutputDir = ".\parsed_resumes",
    [string]$Model = "mistral-small-latest",
    [int]$Retries = 2,
    [switch]$Resume,
    [string]$PythonPath = "python"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $ProjectRoot
try {
    $arguments = @(
        ".\resume_parser.py",
        "--provider", "mistral",
        "--model", $Model,
        "--input-dir", $InputDir,
        "--output-dir", $OutputDir,
        "--retries", $Retries
    )
    if ($Resume) {
        $arguments += "--resume"
    }
    & $PythonPath @arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
