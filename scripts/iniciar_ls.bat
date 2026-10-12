@echo off
rem ============================================================
rem  LS — inicia o assistente.
rem  Uso:  scripts\iniciar_ls.bat               (abre a janela)
rem        scripts\iniciar_ls.bat --no-window   (so o servidor; abra a URL no navegador)
rem        scripts\iniciar_ls.bat --autostart   (inicia minimizado na bandeja)
rem  Mostra o console com os logs. Para encerrar: feche a janela ou use o icone da bandeja.
rem ============================================================
setlocal
cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
  echo [LS] Ambiente nao encontrado. Rode primeiro:  scripts\instalar_windows.bat
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m ls_assistant %*
set "CODIGO=%errorlevel%"
if not "%CODIGO%"=="0" (
  echo.
  echo [LS] Encerrou com erro (codigo %CODIGO%). Veja as mensagens acima e logs\ls.log
  pause
)
endlocal & exit /b %CODIGO%
