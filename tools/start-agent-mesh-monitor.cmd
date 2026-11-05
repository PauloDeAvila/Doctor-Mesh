@echo off
title Doctor Mesh Agent Mesh - Monitor
echo Iniciando monitor do Doctor Mesh...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -NoExit -File "C:\Users\phsra\OneDrive\Documents\Doctor Mesh\tools\monitor-agent-mesh.ps1"
echo.
echo O monitor terminou ou encontrou um erro.
pause
