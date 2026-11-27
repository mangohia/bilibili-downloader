@echo off
cd /d "%~dp0"
where pyw >nul 2>nul
if %errorlevel%==0 goto usepyw
where pythonw >nul 2>nul
if %errorlevel%==0 goto usew
where python >nul 2>nul
if %errorlevel%==0 goto usec
echo Python 3.8+ not found. Install it and tick "Add python.exe to PATH".
pause
exit /b
:usepyw
start "" pyw -3 gui.py
exit /b
:usew
start "" pythonw gui.py
exit /b
:usec
start "" python gui.py
exit /b
