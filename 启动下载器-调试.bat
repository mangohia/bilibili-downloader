@echo off
cd /d "%~dp0"
echo ==== Bilibili downloader (debug console) ====
python gui.py
echo.
echo exit code: %errorlevel%
pause
