@echo off
echo ===================================================
echo   Syncing __gateway-service to GitHub (Both Branches)
echo ===================================================
py "%~dp0tools\sync_gateway_to_github.py" %*
pause
