@echo off
title AI Gateway Service (Port 8800)
echo Starting AI Gateway Service...
py "%~dp0run_server.py" %*
pause

