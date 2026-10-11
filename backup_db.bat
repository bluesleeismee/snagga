@echo off
REM ---------------------------------------------------------------------------
REM Snagga-Datenbank sichern (alle Tabellen als CSV.gz). Liest nur.
REM Ergebnis: backend\backup_JJJJ-MM-TT\
REM ---------------------------------------------------------------------------
cd /d D:\Claude\DealRadar\backend
if exist ".venv\Scripts\activate.bat" call .venv\Scripts\activate.bat
python -c "import asyncpg, dotenv" 2>nul || pip install -q asyncpg python-dotenv
python backup_db.py
echo.
pause
