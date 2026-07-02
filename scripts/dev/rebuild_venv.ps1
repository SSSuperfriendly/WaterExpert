$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$VenvRoot = Join-Path $RepoRoot ".ai4s"
$ExpectedTarget = [System.IO.Path]::GetFullPath($VenvRoot)
$VenvPython = Join-Path $VenvRoot "Scripts\python.exe"

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

if (Test-Path -LiteralPath $VenvRoot) {
    $ResolvedTarget = [System.IO.Path]::GetFullPath($VenvRoot)
    if ($ResolvedTarget -ne $ExpectedTarget) {
        throw "Refusing to remove unexpected path: $ResolvedTarget"
    }
    Remove-Item -LiteralPath $VenvRoot -Recurse -Force
}

$BootstrapPython = Get-BootstrapPython
& $BootstrapPython -m venv $VenvRoot
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create virtual environment."
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "Virtual environment was created without Scripts\\python.exe. A non-Windows Python was likely used."
}

& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upgrade pip."
}

& $VenvPython -m pip install -r (Join-Path $RepoRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install requirements."
}

Write-Host "Virtual environment rebuilt successfully at $VenvRoot"
