@echo off
REM QueueCTL Setup Script for Windows

echo ========================================
echo QueueCTL Setup Script
echo ========================================
echo.

REM Check Python installation
echo [1/5] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/downloads/
    pause
    exit /b 1
)
echo Python found!
echo.

REM Create virtual environment
echo [2/5] Creating virtual environment...
if exist venv (
    echo Virtual environment already exists, skipping...
) else (
    python -m venv venv
    echo Virtual environment created!
)
echo.

REM Activate virtual environment and install dependencies
echo [3/5] Installing dependencies...
call venv\Scripts\activate.bat
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)
echo Dependencies installed!
echo.

REM Create data directory
echo [4/5] Creating data directory...
if not exist data mkdir data
echo Data directory ready!
echo.

REM Run tests
echo [5/5] Running tests...
python test_queuectl.py
if errorlevel 1 (
    echo WARNING: Some tests failed
) else (
    echo All tests passed!
)
echo.

echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo To get started:
echo   1. Run: venv\Scripts\activate.bat
echo   2. Then: python queuectl.py --help
echo.
echo For full documentation, see README.md
echo.
pause