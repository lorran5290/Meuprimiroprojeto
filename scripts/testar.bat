@echo off
rem Roda os testes automatizados (sem chamar a API real do Gemini).
setlocal
cd /d "%~dp0\.."
if not exist ".venv\Scripts\python.exe" (
  echo [LS] Rode primeiro scripts\instalar_windows.bat
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -q -r requirements-dev.txt
".venv\Scripts\python.exe" -m pytest -v
set "CODIGO=%errorlevel%"
echo.
echo Para testar a API real (gasta cota), defina GEMINI_API_KEY e rode:
echo   .venv\Scripts\python.exe -m pytest -m live
pause
endlocal & exit /b %CODIGO%
