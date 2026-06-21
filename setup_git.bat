@echo off
cd /d D:\Claude\DealRadar

echo Initialisiere Git-Repository...
git init
git branch -m main
git config user.name "bluesleeismee"
git config user.email "davidpauli@gmx.ch"

echo Fuege Dateien hinzu...
git add -A
git commit -m "Initial commit: Snagga Deal-PWA"

echo.
echo Jetzt Repository auf GitHub anlegen:
echo 1. Gehe zu https://github.com/new
echo 2. Name: snagga
echo 3. KEIN README, KEINE .gitignore
echo 4. Klicke "Create repository"
echo.
echo Danach diese Befehle hier kopieren und ausfuehren:
echo git remote add origin https://github.com/bluesleeismee/snagga.git
echo git push -u origin main
echo.
pause
