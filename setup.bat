@echo off
rem ===========================================================================
rem  One-time setup for the timetable generator (Windows).
rem
rem  Creates a local Python virtual environment and installs everything the
rem  system needs. Run this once. After that, use start.bat to launch.
rem
rem  Requires Python 3.11 or newer, installed from python.org with the
rem  "Add python.exe to PATH" option enabled.
rem ===========================================================================

setlocal
cd /d "%~dp0"

echo ==========================================================
echo   Timetable Generator - Setup
echo ==========================================================
echo.

rem --- Locate Python --------------------------------------------------------

set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python --version >nul 2>&1 && set "PY=python"
)

if not defined PY (
    echo ERROR: Python was not found on this computer.
    echo.
    echo Install Python 3.11 or newer from:
    echo     https://www.python.org/downloads/windows/
    echo.
    echo During installation, tick "Add python.exe to PATH".
    echo Then run this script again.
    echo.
    pause
    exit /b 1
)

%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
    echo ERROR: Python 3.11 or newer is required.
    echo Installed version:
    %PY% --version
    echo.
    echo Install a newer version from https://www.python.org/downloads/windows/
    echo.
    pause
    exit /b 1
)

echo Using Python:
%PY% --version
echo.

rem --- Check for a virtual environment from another platform ----------------

if exist ".venv" (
    if not exist ".venv\Scripts\python.exe" (
        echo ERROR: a .venv folder exists but was not built for Windows.
        echo.
        echo This usually means the project was copied from another computer.
        echo Delete the .venv folder and run this script again:
        echo.
        echo     rmdir /s /q .venv
        echo.
        pause
        exit /b 1
    )
    echo An existing environment was found. It will be reused and updated.
    echo.
)

rem --- Create the environment -----------------------------------------------

if not exist ".venv\Scripts\python.exe" (
    echo Creating the virtual environment...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo ERROR: could not create the virtual environment.
        pause
        exit /b 1
    )
    echo Done.
    echo.
)

rem --- Install dependencies -------------------------------------------------

echo Installing dependencies. This may take a few minutes.
echo.

".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo ERROR: could not update pip.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"
if errorlevel 1 (
    echo.
    echo ERROR: could not install the dependencies.
    echo Check your internet connection and run this script again.
    pause
    exit /b 1
)

rem --- Verify ---------------------------------------------------------------

echo.
echo Verifying the installation...
".venv\Scripts\python.exe" -c "import fastapi, uvicorn, openpyxl, markitdown, google.genai; print('All required packages import correctly.')"
if errorlevel 1 (
    echo.
    echo ERROR: the installation is incomplete.
    echo Try deleting the .venv folder and running this script again.
    pause
    exit /b 1
)

echo.
echo ==========================================================
echo   Setup complete.
echo.
echo   Start the system by double-clicking start.bat
echo ==========================================================
echo.
pause
endlocal
