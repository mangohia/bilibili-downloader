@echo off
chcp 65001 >nul
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw gui.py
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        start "" python gui.py
    ) else (
        echo 未找到 Python，请先安装 Python 3.8+ 并勾选 Add python.exe to PATH
        pause
    )
)
