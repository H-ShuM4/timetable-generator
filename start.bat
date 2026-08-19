@echo off
rem ---------------------------------------------------------------------------
rem  Start the timetable generator from Windows.
rem
rem  The application runs inside WSL. This script hands off to start.sh there,
rem  which starts the server and opens your browser.
rem
rem  Close this window or press Ctrl+C to stop the server.
rem ---------------------------------------------------------------------------

setlocal

set "DISTRO=Ubuntu"
set "PROJECT=/home/myarm/py_venvs/Project_3"

where wsl.exe >nul 2>&1
if errorlevel 1 (
    echo ERROR: wsl.exe was not found. WSL must be installed to run this system.
    pause
    exit /b 1
)

echo Starting the timetable generator in WSL ^(%DISTRO%^)...
echo.

wsl.exe -d %DISTRO% -- bash -lc "cd '%PROJECT%' && ./start.sh %*"

if errorlevel 1 (
    echo.
    echo The server exited with an error. See the messages above.
    pause
)

endlocal
