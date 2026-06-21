@echo off
cd /d "%~dp0"
if not exist "node_modules" (
    echo Installiere npm-Pakete (einmalig, 1-2 Min)...
    npm install
)
echo.
echo  Frontend laeuft auf http://localhost:5173
echo.
npm run dev
pause
