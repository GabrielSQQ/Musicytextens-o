@echo off
setlocal
cd /d "%~dp0.."
echo Opera Music Downloader - compilacao para desenvolvedores
echo Este arquivo nao e necessario para quem recebeu o Setup.exe pronto.
py -3.12 scripts\build_windows.py
if errorlevel 1 (
  echo.
  echo A compilacao falhou. Consulte docs\BUILD-WINDOWS.md.
  pause
  exit /b 1
)
echo.
echo Instalador pronto na pasta dist.
pause
