@echo off
rem ===========================================================================
rem  Start the timetable generator (Windows).
rem
rem  Run setup.bat once before using this script.
rem
rem  Usage:
rem    start.bat          start on port 8000 and open a browser
rem    start.bat 8080     start on port 8080
rem
rem  Close this window or press Ctrl+C to stop the server.
rem ===========================================================================

setlocal
cd /d "%~dp0"

set "PORT=8000"
if not "%~1"=="" set "PORT=%~1"

set "VENV_PY=%~dp0.venv\Scripts\python.exe"
set "URL=http://localhost:%PORT%/"

rem --- Check the environment ------------------------------------------------

if not exist "%VENV_PY%" (
    echo ERROR: the Python environment is missing.
    echo.
    if exist ".venv" (
        echo A .venv folder exists but was not built for Windows.
        echo Delete it and run setup.bat:
        echo.
        echo     rmdir /s /q .venv
        echo.
    ) else (
        echo Run setup.bat first. It only needs to be done once.
        echo.
    )
    pause
    exit /b 1
)

rem --- Check the port -------------------------------------------------------

netstat -ano | findstr /r /c:":%PORT% .*LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo ERROR: port %PORT% is already in use.
    echo.
    echo The system may already be running. Look for another window, or
    echo start on a different port:
    echo.
    echo     start.bat 8001
    echo.
    pause
    exit /b 1
)

rem --- Start ----------------------------------------------------------------

echo ==========================================================
echo   Timetable Generator
echo.
echo   Address: %URL%
echo   Press Ctrl+C in this window to stop the server.
echo ==========================================================
echo.

rem Open the browser shortly after the server begins listening.
start "" /b cmd /c "timeout /t 3 /nobreak >nul & start %URL%"

cd backend
"%VENV_PY%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%

if errorlevel 1 (
    echo.
    echo The server stopped with an error. See the messages above.
    pause
)

endlocal
