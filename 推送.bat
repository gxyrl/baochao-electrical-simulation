@echo off
setlocal

rem ============================================================
rem  Push this project to GitHub (one-click)
rem  Just double-click this file.
rem
rem  NOTE 1: keep this .bat ASCII-only. This machine's cmd.exe
rem  cannot reliably parse .bat files that contain Chinese
rem  characters (tested with UTF-8 BOM / UTF-8 no-BOM / GBK).
rem  NOTE 2: chcp 65001 sets the console to UTF-8 so that the
rem  Python script's Chinese output renders correctly.
rem ============================================================

chcp 65001 >nul

set "PY="

if exist "%USERPROFILE%\.workbuddy\binaries\python\versions\3.13.12\python.exe" (
    set "PY=%USERPROFILE%\.workbuddy\binaries\python\versions\3.13.12\python.exe"
    goto :found
)

where python >nul 2>nul
if not errorlevel 1 (
    set "PY=python"
    goto :found
)

where py >nul 2>nul
if not errorlevel 1 (
    set "PY=py"
    goto :found
)

echo.
echo  [ERROR] Python not found on this machine.
echo          Please install Python 3 and retry.
echo.
pause
exit /b 1

:found
cls
"%PY%" "%~dp0push_to_github.py"
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo  [OK] Done.
) else (
    echo  [FAILED] Exit code: %RC%
    echo         See the messages above for details.
)
echo.
pause
