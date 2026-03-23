@echo off
start "" /B python "%~dp0server.py"
timeout /t 2 /nobreak >nul
start "" http://localhost:5555
