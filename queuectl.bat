@echo off
REM QueueCTL Wrapper Script

REM Activate virtual environment if it exists
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

REM Run queuectl.py with all arguments
python queuectl.py %*