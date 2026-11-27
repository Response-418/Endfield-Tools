@echo off
chcp 65001 >nul
title 应用本地定制补丁

cd /d "%~dp0"
set PY=%~dp0runtime\python.exe

if not exist "%PY%" (
    echo [错误] 找不到内置 Python：%PY%
    pause
    exit /b 1
)

echo ==================================================
echo  EndfieldRotPilot 本地定制补丁
echo  基线：v1.4.1  定制版本：2026-11-27.1
echo ==================================================
echo.
"%PY%" "%~dp0patches\apply_custom.py" %*
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (
    echo [OK] 补丁已就绪，可以启动程序了。
) else (
    echo [提示] 补丁脚本返回码 %RC%，请看上面的说明。
)
echo.
pause
