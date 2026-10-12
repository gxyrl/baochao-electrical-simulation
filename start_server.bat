@echo off
setlocal enabledelayedexpansion
title Electrical Control Virtual Simulation - Local Launcher

cd /d "%~dp0"

echo.
echo  ===============================================================
echo    Electrical Control Technology Virtual Simulation System
echo    Local Launcher
echo  ===============================================================
echo.

if not exist "index.html" (
    echo  [ERROR] index.html not found in current folder.
    echo          Please place this script next to index.html.
    echo.
    pause
    exit /b 1
)

set "PY_CMD="

if exist "%USERPROFILE%\.workbuddy\binaries\python\versions\3.13.12\python.exe" (
    set "PY_CMD="%USERPROFILE%\.workbuddy\binaries\python\versions\3.13.12\python.exe""
    goto :py_found
)

where python >nul 2>nul
if not errorlevel 1 (
    set "PY_CMD=python"
    goto :py_found
)

where py >nul 2>nul
if not errorlevel 1 (
    set "PY_CMD=py -3"
    goto :py_found
)

for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python39\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python38\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python37\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Python310\python.exe"
) do (
    if exist %%P (
        set "PY_CMD=%%~P"
        goto :py_found
    )
)

echo  [ERROR] Python not found on this computer.
echo.
echo          This project is pure front-end, but ES Modules must be
echo          served over HTTP. A local Python is used as the server.
echo.
echo          Please install Python: https://www.python.org/downloads/
echo          (remember to check "Add Python to PATH")
echo.
pause
exit /b 1

:py_found

set "PORT=8000"
set /a TRY=0
:port_loop
set /a TRY+=1
netstat -ano | findstr /r /c:"LISTENING .*:%PORT% " >nul 2>nul
if not errorlevel 1 (
    echo  [WARN] Port %PORT% is busy, trying next port...
    set /a PORT+=1
    if !TRY! lss 20 goto :port_loop
    echo  [ERROR] Too many ports occupied. Close some programs first.
    pause
    exit /b 1
)

set "URL=http://localhost:%PORT%"

echo  [OK] Python    : !PY_CMD!
echo  [OK] Port      : %PORT%
echo  [OK] Open this : %URL%
echo.
echo  ---------------------------------------------------------------
echo   * The browser will open automatically.
echo   * Close THIS window to stop the server.
echo.
echo   * Do NOT double-click index.html (it will show a blank page).
echo     Always use the HTTP server started by this script.
echo  ---------------------------------------------------------------
echo.

start "" cmd /c "timeout /t 2 /nobreak >nul & start "" "%URL%""

!PY_CMD! -m http.server %PORT% --bind 0.0.0.0

echo.
echo  [INFO] Server stopped.
pause
endlocal
