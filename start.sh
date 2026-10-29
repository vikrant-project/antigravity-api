#!/usr/bin/env bash
set -e

echo "=================================================="
echo "    Starting Antigravity Direct API & Chatbot     "
echo "=================================================="

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is required but not installed. Exiting."
    exit 1
fi

# Setup Virtual Environment if not exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "Checking dependencies..."
pip install -q -r requirements.txt

echo "Starting server on port 8000..."
python3 run.py --host 0.0.0.0 --port 8000
