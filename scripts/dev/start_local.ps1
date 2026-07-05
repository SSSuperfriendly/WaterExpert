param(
    [switch]$RecreateVenv,
    [switch]$SkipInstall,
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$VenvRoot = Join-Path $RepoRoot ".ai4s"
$VenvPython = Join-Path $VenvRoot "Scripts\python.exe"
$RequirementsFile = Join-Path $RepoRoot "requirements.txt"

function Get-BootstrapPython {
    $Candidates = [System.Collections.Generic.List[string]]::new()

    if ($env:CONDA_PREFIX) {
        $Candidates.Add((Join-Path $env:CONDA_PREFIX "python.exe"))
    }
    if ($env:CONDA_EXE) {
        $CondaRoot = Split-Path (Split-Path $env:CONDA_EXE -Parent) -Parent
        $Candidates.Add((Join-Path $CondaRoot "python.exe"))
    }
    if ($env:USERPROFILE) {
        $Candidates.Add((Join-Path $env:USERPROFILE "anaconda3\python.exe"))
    }

    try {
        $ResolvedPython = (Get-Command python -ErrorAction Stop).Source
        $Candidates.Add($ResolvedPython)
    }
    catch {
        # ignore lookup failures
    }

    foreach ($Candidate in $Candidates) {
        if (-not $Candidate) {
            continue
        }
        if (-not (Test-Path -LiteralPath $Candidate)) {
            continue
        }
        if ($Candidate -match "msys|mingw") {
            continue
        }
        return [System.IO.Path]::GetFullPath($Candidate)
    }

    throw "Unable to find a supported Windows Python interpreter. Please activate Conda or install CPython, then rerun this script."
}

function Test-VenvHealthy {
    param(
        [string]$PythonPath,
        [string]$ExpectedPrefix
    )

    if (-not (Test-Path -LiteralPath $PythonPath)) {
        return $false
    }

    try {
        $Prefix = & $PythonPath -c "import pathlib, sys; print(pathlib.Path(sys.prefix).resolve())"
        if ($LASTEXITCODE -ne 0) {
            return $false
        }
        return ([System.IO.Path]::GetFullPath($Prefix.Trim()) -eq [System.IO.Path]::GetFullPath($ExpectedPrefix))
    }
    catch {
        return $false
    }
}

function Remove-StaleVenv {
    param([string]$TargetPath)

    $ResolvedTarget = [System.IO.Path]::GetFullPath($TargetPath)
    $ExpectedTarget = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot ".ai4s"))
    if ($ResolvedTarget -ne $ExpectedTarget) {
        throw "Refusing to remove unexpected path: $ResolvedTarget"
    }
    if (Test-Path -LiteralPath $ResolvedTarget) {
        Remove-Item -LiteralPath $ResolvedTarget -Recurse -Force
    }
}

if ($RecreateVenv) {
    Remove-StaleVenv -TargetPath $VenvRoot
}

if (-not (Test-VenvHealthy -PythonPath $VenvPython -ExpectedPrefix $VenvRoot)) {
    $BootstrapPython = Get-BootstrapPython

    if (Test-Path -LiteralPath $VenvRoot) {
        Write-Host "Detected a stale or moved virtual environment at $VenvRoot. Recreating it..."
        Remove-StaleVenv -TargetPath $VenvRoot
    }

    Write-Host "Creating virtual environment in $VenvRoot using $BootstrapPython ..."
    & $BootstrapPython -m venv $VenvRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create virtual environment."
    }
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        throw "Virtual environment was created without Scripts\\python.exe. A non-Windows Python was likely used."
    }
}

if (-not $SkipInstall) {
    Write-Host "Installing dependencies with $VenvPython ..."
    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upgrade pip."
    }
    & $VenvPython -m pip install -r $RequirementsFile
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install requirements."
    }
}

Write-Host "Starting WaterExpert on http://$BindHost`:$Port ..."
Push-Location $RepoRoot
try {
    & $VenvPython -m uvicorn backend.app.main:app --reload --host $BindHost --port $Port
}
finally {
    Pop-Location
}
