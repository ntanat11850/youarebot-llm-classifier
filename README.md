# Echo Bot

A simple echo bot for the HumanOrBot project that replies to any received message with the same text.

## Overview

This service provides a FastAPI-based API endpoint that receives messages and echoes them back. It is designed to work with the HumanOrBot service, responding to each message with the same text.

## Running the Service

Go to the project directory:

### On Linux/macOS

```bash
chmod +x run_all_linux.sh
```

```bash
./run_all_linux.sh
```

### On Windows

Install Python 3.12 first, then run:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\run_all_windows.ps1
```

If Windows fails around `pydantic-core`, check that `py -3.12 --version` works and remove any copied virtualenv:

```powershell
Remove-Item -Recurse -Force .venv
```

#### These scripts will:
1. Install Poetry (if needed)
2. Install project dependencies
3. Set up an SSH tunnel to the remote host
4. Start the FastAPI application on port 6872
