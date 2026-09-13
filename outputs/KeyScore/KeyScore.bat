@echo off
setlocal
set "APP_DIR=%~dp0"
set "PYTHON_EXE=%APP_DIR%..\..\.venv\Scripts\pythonw.exe"
if not exist "%PYTHON_EXE%" if exist "%APP_DIR%..\..\runtime-path.txt" set /p "PYTHON_EXE=" < "%APP_DIR%..\..\runtime-path.txt"
if not exist "%PYTHON_EXE%" (
  echo KeyScore runtime is missing. See README.md.
  pause
  exit /b 1
)
start "" "%PYTHON_EXE%" "%APP_DIR%app.py"
