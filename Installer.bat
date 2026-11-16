@echo off
title Topaz Local - Installation
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 (
  echo.
  echo *** L'installation a rencontre une erreur. Verifie ta connexion Internet. ***
)
echo.
pause
