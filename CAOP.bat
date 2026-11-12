@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "BACKEND_PORT=8000"
set "FRONTEND_PORT=3006"
set "BACKEND_URL=http://127.0.0.1:%BACKEND_PORT%/api/health"
set "FRONTEND_URL=http://127.0.0.1:%FRONTEND_PORT%"

echo.
echo ==========================================
echo   Campus Autonomous Operations Platform
echo ==========================================
echo.

where npm >nul 2>nul
if errorlevel 1 (
  echo ERROR: npm was not found on PATH.
  echo Install Node.js, then run CAOP.bat again.
  pause
  exit /b 1
)

set "PYTHON=%ROOT%\.venv_local\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  where python >nul 2>nul
  if errorlevel 1 (
    echo ERROR: Python was not found.
    pause
    exit /b 1
  )
  set "PYTHON=python"
)

if not exist "%ROOT%\backend\main.py" (
  echo ERROR: backend\main.py was not found under "%ROOT%".
  pause
  exit /b 1
)
if not exist "%ROOT%\frontend\package.json" (
  echo ERROR: frontend\package.json was not found under "%ROOT%".
  pause
  exit /b 1
)

for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%BACKEND_PORT% .*LISTENING"') do set "BACKEND_PID=%%P"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%FRONTEND_PORT% .*LISTENING"') do set "FRONTEND_PID=%%P"
if defined BACKEND_PID if defined FRONTEND_PID (
  echo CAOP is already running.
  start "" "%FRONTEND_URL%"
  exit /b 0
)
if defined BACKEND_PID (
  echo ERROR: port %BACKEND_PORT% is already in use by PID %BACKEND_PID%.
  echo Stop that service or run CAOP-STOP.bat.
  pause
  exit /b 1
)
if defined FRONTEND_PID (
  echo ERROR: port %FRONTEND_PORT% is already in use by PID %FRONTEND_PID%.
  echo Stop that service or run CAOP-STOP.bat.
  pause
  exit /b 1
)

echo Starting backend...
start "CAOP Backend" /D "%ROOT%" cmd /k ""%PYTHON%" -m uvicorn backend.main:app --host 127.0.0.1 --port %BACKEND_PORT%"
echo Starting frontend...
start "CAOP Frontend" /D "%ROOT%\frontend" cmd /k "npm run dev -- --host 127.0.0.1 --port %FRONTEND_PORT%"

echo Waiting for backend readiness...
set /a ATTEMPTS=0
:wait_backend
set /a ATTEMPTS+=1
if %ATTEMPTS% GEQ 60 (
  echo ERROR: backend did not become ready within 60 seconds.
  echo Inspect the CAOP Backend window for the startup error.
  pause
  exit /b 1
)
curl.exe --silent --fail "%BACKEND_URL%" >nul 2>nul
if errorlevel 1 (
  timeout /t 1 /nobreak >nul
  goto wait_backend
)

echo Backend is ready.
echo Opening %FRONTEND_URL%
start "" "%FRONTEND_URL%"
echo CAOP is running. Close the backend and frontend windows, or run CAOP-STOP.bat.
exit /b 0
