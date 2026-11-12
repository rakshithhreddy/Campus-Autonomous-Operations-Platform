@echo off
setlocal EnableExtensions

echo Stopping CAOP services...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":8000 .*LISTENING"') do (
  echo Stopping backend PID %%P
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Stop-Process -Id %%P -Force -ErrorAction SilentlyContinue"
)
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":3006 .*LISTENING"') do (
  echo Stopping frontend PID %%P
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Stop-Process -Id %%P -Force -ErrorAction SilentlyContinue"
)
echo Done.
pause
