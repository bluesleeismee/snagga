@echo off
setlocal
set ROOT=%~dp0
echo.
echo  Snagga wird gestartet...
echo.

if not exist "%ROOT%.env" (
    copy "%ROOT%.env.example" "%ROOT%.env" >nul
    echo  .env erstellt
)

python --version >nul 2>&1
if errorlevel 1 (
    echo  FEHLER: Python nicht gefunden!
    echo  https://www.python.org/downloads/
    pause & exit /b 1
)

node --version >nul 2>&1
if errorlevel 1 (
    echo  FEHLER: Node.js nicht gefunden!
    echo  https://nodejs.org/
    pause & exit /b 1
)

echo  Starte Backend...
start "Snagga Backend" "%ROOT%backend\run.bat"
timeout /t 3 /nobreak >nul

echo  Starte Frontend...
start "Snagga Frontend" "%ROOT%frontend\run.bat"

echo.
echo  ================================================
echo   Frontend:  http://localhost:5173
echo   Backend:   http://localhost:8000
echo   API Docs:  http://localhost:8000/docs
echo  ================================================
echo.
pause
