@echo off
rem Smart Energy Guardian - run everything locally with one command (Windows).
rem Needs Python 3.11+ and Node.js 20+.  Usage: run-local.bat [--rebuild]
setlocal
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3.11+ is required: https://www.python.org/downloads/ & exit /b 1)
where npm >nul 2>nul || (echo Node.js 20+ is required: https://nodejs.org/ & exit /b 1)

if not exist backend\.venv\Scripts\python.exe (
  echo ==^> Creating Python virtual environment
  python -m venv backend\.venv || exit /b 1
)
if not exist backend\.venv\.installed (
  echo ==^> Installing backend dependencies
  backend\.venv\Scripts\python -m pip install -q --upgrade pip
  backend\.venv\Scripts\python -m pip install -q -r backend\requirements.txt || exit /b 1
  type nul > backend\.venv\.installed
)
set REBUILD=0
if not exist frontend\dist\index.html set REBUILD=1
if "%~1"=="--rebuild" set REBUILD=1
if "%REBUILD%"=="1" (
  echo ==^> Building the dashboard
  pushd frontend
  call npm ci --no-audit --no-fund || exit /b 1
  call npm run build || exit /b 1
  popd
)

if "%PORT%"=="" set PORT=8000
echo.
echo ==^> Smart Energy Guardian: http://localhost:%PORT%   (login: admin / guardian-demo)
echo     API docs: http://localhost:%PORT%/docs   - press Ctrl+C to stop
echo.
cd backend
.venv\Scripts\python -m uvicorn app.asgi:app --host 0.0.0.0 --port %PORT%
