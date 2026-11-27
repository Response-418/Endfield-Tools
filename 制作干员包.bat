@echo off
chcp 65001 >nul
"%~dp0runtime\python.exe" "%~dp0tools\make_op_pack.py"
if errorlevel 1 pause
