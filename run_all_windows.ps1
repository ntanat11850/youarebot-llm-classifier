# run_all_windows.ps1
# IMPORTANT: Run this script in PowerShell with execution policy set appropriately

# Setup: Stop on errors
$ErrorActionPreference = "Stop"

# Vars
$remote_host = "158.160.135.246"
$private_key = "portforward_key"  # Adjust path if needed
$port_file   = Join-Path $env:TEMP "random_port.txt"
$required_python = "3.12"
$poetry_version = "2.1.1"

function Get-Python312 {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        throw "Python Launcher 'py' was not found. Install Python 3.12 from python.org and enable 'py launcher'."
    }

    $python_path = & py -3.12 -c "import sys; print(sys.executable)"
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($python_path)) {
        throw "Python 3.12 is required. Install it, then check with: py -3.12 --version"
    }

    return $python_path.Trim()
}

function Get-PoetryCommand {
    $cmd = Get-Command poetry -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $candidate = Join-Path $env:APPDATA "Python\Scripts\poetry.exe"
    if (Test-Path $candidate) {
        return $candidate
    }

    return $null
}

function Install-Poetry {
    Write-Host "Installing Poetry $poetry_version..."
    $env:POETRY_VERSION = $poetry_version
    try {
        (Invoke-WebRequest -Uri "https://install.python-poetry.org" -UseBasicParsing).Content | & $python -
    } finally {
        Remove-Item Env:\POETRY_VERSION -ErrorAction SilentlyContinue
    }
}

# 1. Generate or load random port
if (Test-Path $port_file) {
    $random_port = (Get-Content $port_file -Raw).Trim()
} else {
    $random_port = Get-Random -Minimum 1024 -Maximum 65536
    Set-Content -Path $port_file -Value $random_port
}
Write-Host "Random port generated: $random_port"

# 2. Select Python 3.12. Newer Python versions can make pydantic-core build from source on Windows.
Write-Host "Checking Python $required_python..."
$python = Get-Python312
Write-Host "Using Python: $python"

# 3. Add Poetry bin directory to PATH
$poetryBin = Join-Path $env:APPDATA "Python\Scripts"
if ($env:PATH -notmatch [regex]::Escape($poetryBin)) {
    $env:PATH = "$poetryBin;$env:PATH"
    Write-Host "Added Poetry bin directory to PATH: $poetryBin"
} else {
    Write-Host "Poetry bin directory already in PATH: $poetryBin"
}

# 4. Install or pin Poetry
$poetry = Get-PoetryCommand
if (-not $poetry) {
    Install-Poetry
    $poetry = Get-PoetryCommand
}

if (-not $poetry) {
    throw "Poetry was installed, but poetry.exe was not found in PATH or $poetryBin."
}

$installed_poetry_version = (& $poetry --version) -replace "Poetry \(version ([^)]+)\)", '$1'
if ($installed_poetry_version -ne $poetry_version) {
    Write-Host "Replacing Poetry $installed_poetry_version with $poetry_version..."
    Install-Poetry
    $poetry = Get-PoetryCommand
}
Write-Host "Using Poetry: $(& $poetry --version)"

# 5. Remove virtualenvs that cannot work on Windows or use an unsupported Python version.
if ((Test-Path ".venv\bin") -and -not (Test-Path ".venv\Scripts")) {
    Write-Host "Removing non-Windows .venv copied from macOS/Linux..."
    Remove-Item -Recurse -Force ".venv"
}

if (Test-Path ".venv\pyvenv.cfg") {
    $venv_cfg = Get-Content ".venv\pyvenv.cfg" -Raw
    if ($venv_cfg -notmatch "3\.12") {
        Write-Host "Removing .venv created with a Python version other than 3.12..."
        Remove-Item -Recurse -Force ".venv"
    }
}

# 6. Install project dependencies
Write-Host "Installing Project's dependencies..."
& $poetry config virtualenvs.in-project true --local
& $poetry env use $python
& $poetry install
Write-Host "Dependencies installed successfully."

# 7. Fix access rules on the SSH key
$icaclsOutput = icacls $private_key /inheritance:r /grant:r "$($env:USERNAME):F"
Write-Host "icacls output:" $icaclsOutput

# 8. Start SSH tunnel (reverse port forwarding)
$sshArgs = "-i `"$private_key`" -N -R 0.0.0.0:${random_port}:localhost:6872 forwarduser@${remote_host} -o StrictHostKeyChecking=no"
Write-Host "Starting SSH tunnel with: ssh $sshArgs"
Start-Process ssh -ArgumentList $sshArgs -NoNewWindow

# Time for Tunnel to start
Start-Sleep -Seconds 2

# 9. Launch FastAPI uvicorn
Write-Host "Launching the FastAPI app on port 6872..."
Start-Process -FilePath $poetry -ArgumentList "run", "fastapi", "dev", "app/api/main.py", "--host", "127.0.0.1", "--port", "6872"

# Time for FastAPI to start
Start-Sleep -Seconds 5

# 10. Check local port 6872
Write-Host "Checking local port 6872..."
$tcLocal = Test-NetConnection -ComputerName localhost -Port 6872
if ($tcLocal.TcpTestSucceeded) {
    Write-Host "Local port 6872 is UP (FastAPI should be running)."
} else {
    Write-Host "Local port 6872 is DOWN."
}

# Time for checking
Start-Sleep -Seconds 1

# 11. Launch Streamlit on local port 8502
Write-Host "Launching the Streamlit app on port 8502..."
$env:PYTHONPATH = (Get-Location).Path
Start-Process -FilePath $poetry -ArgumentList "run", "streamlit", "run", "app/web/streamlit_app.py", "--server.port=8502", "--server.address=127.0.0.1"

# 12. Log address for registration
Write-Host "Your address for registration is:"
Write-Host "http://${remote_host}:${random_port}"
