@echo off
setlocal EnableExtensions

title RECOURSE Launcher
cd /d "%~dp0"

echo.
echo ========================================
echo   RECOURSE - Local Demo Launcher
echo ========================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH.
    echo Install Python 3.11 or newer, then run this file again.
    pause
    exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] npm was not found in PATH.
    echo Install Node.js 20 or newer, then run this file again.
    pause
    exit /b 1
)

echo [1/4] Checking backend dependencies...
set "PYTHONPATH=apps/api/src"
python -c "import fastapi, sqlalchemy, uvicorn, recourse" >nul 2>nul
if errorlevel 1 (
    echo Installing backend dependencies...
    python -m pip install -e ".[dev]"
    if errorlevel 1 goto :install_failed
) else (
    echo Backend dependencies are ready.
)

echo [2/4] Checking frontend dependencies...
if not exist "apps\web\node_modules\.package-lock.json" (
    echo Installing frontend dependencies...
    call npm --prefix "apps\web" install
    if errorlevel 1 goto :install_failed
) else (
    echo Frontend dependencies are ready.
)

if /I "%~1"=="--check" (
    echo.
    echo All prerequisites are ready.
    exit /b 0
)

echo [3/4] Starting the API at http://127.0.0.1:8000 ...
start "RECOURSE API" /D "%~dp0" cmd /k "set PYTHONPATH=apps/api/src&& set OPENROUTER_ENABLED=false&& set RAZORPAY_ENABLED=false&& python -m uvicorn recourse.main:app --host 127.0.0.1 --port 8000"

echo [4/4] Starting the web app at http://127.0.0.1:5173 ...
start "RECOURSE Web" /D "%~dp0apps\web" cmd /k "npm run dev -- --host 127.0.0.1"

echo Waiting for the web app to become ready...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ready=$false; for($i=0; $i -lt 40; $i++){ try { $response=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5173/' -TimeoutSec 1; if($response.StatusCode -eq 200){ $ready=$true; break } } catch {}; Start-Sleep -Milliseconds 500 }; if(-not $ready){ exit 1 }"

if errorlevel 1 (
    echo.
    echo [WARNING] The servers were launched, but the web app did not respond yet.
    echo Check the RECOURSE API and RECOURSE Web windows for errors.
    pause
    exit /b 1
)

echo.
echo RECOURSE is ready. Opening the browser...
start "" "http://127.0.0.1:5173/"
echo.
echo Close the RECOURSE API and RECOURSE Web windows to stop the project.
timeout /t 4 /nobreak >nul
exit /b 0

:install_failed
echo.
echo [ERROR] Dependency installation failed.
echo Review the output above, then run this file again.
pause
exit /b 1
