@echo off
cd /d "%~dp0"
if not exist ".venv" (
    echo Erstelle Python venv...
    python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -r requirements.txt -q
echo.
echo  Backend laeuft auf http://localhost:8000
echo  API Docs: http://localhost:8000/docs
echo.
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause
