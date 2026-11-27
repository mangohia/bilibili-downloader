@echo off
cd /d "%~dp0"
echo ==== Bilibili downloader (debug console) ====
where py >nul 2>nul
if %errorlevel%==0 goto usepy
python gui.py
goto end
:usepy
py -3 gui.py
:end
echo.
echo exit code: %errorlevel%
pause
