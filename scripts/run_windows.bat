@echo off
setlocal

set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..

REM 기본: GUI 실행 (자동 모드 + 윈도우 토스트 알림)
python "%PROJECT_ROOT%\scripts\run_gui.py" --mode auto --notify toast %*
