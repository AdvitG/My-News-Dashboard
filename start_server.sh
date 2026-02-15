#!/bin/bash

echo "========================================"
echo "  Personal Dashboard - Backend Server"
echo "========================================"
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
    echo "[WARNING] .env file not found!"
    echo ""
    echo "Please create a .env file with your API keys."
    echo "You can copy .env.example to .env and add your keys."
    echo ""
    read -p "Press Enter to exit..."
    exit 1
fi

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 is not installed"
    echo ""
    echo "Please install Python 3.8+ from https://python.org"
    echo ""
    read -p "Press Enter to exit..."
    exit 1
fi

echo "[INFO] Checking dependencies..."
echo ""

# Check if requirements are installed
python3 -c "import flask" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "[INFO] Installing required packages..."
    pip3 install -r requirements.txt
    echo ""
fi

echo "[INFO] Starting backend server..."
echo ""
echo "The dashboard will be available at:"
echo "- Backend API: http://localhost:5000"
echo "- Open Index.html in your browser to view the dashboard"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""
echo "========================================"
echo ""

# Start the server
python3 data_puller.py
