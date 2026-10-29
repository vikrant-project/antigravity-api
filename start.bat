@echo off
title Antigravity Direct API & Chatbot Server
echo ==================================================
echo     Starting Antigravity Direct API ^& Chatbot     
echo ==================================================

python -m pip install -q -r requirements.txt
python run.py --host 0.0.0.0 --port 8000
pause
