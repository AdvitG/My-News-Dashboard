@echo off
echo ========================================
echo   Personal Dashboard - Backend Server
echo ========================================
echo.

:: Check if .env file exists
if not exist .env (
    echo [WARNING] .env file not found!
    echo.
    echo Please create a .env file with your API keys.
    echo You can copy .env.example to .env and add your keys.
    echo.
    pause
    exit /b 1
)

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    echo.
    echo Please install Python 3.8+ from https://python.org
    echo.
    pause
    exit /b 1
)

echo [INFO] Checking dependencies...
echo.

:: Check if requirements are installed
python -c "import flask" 2>nul
if errorlevel 1 (
    echo [INFO] Installing required packages...
    pip install -r requirements.txt
    echo.
)

echo [INFO] Starting backend server...
echo.
echo The dashboard will be available at:
echo - Backend API: http://localhost:5000
echo - Open Index.html in your browser to view the dashboard
echo.
echo Press Ctrl+C to stop the server
echo.
echo ========================================
echo.

:: Start the server
python data_puller.py

pause
