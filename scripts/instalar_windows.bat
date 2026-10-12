@echo off
rem ============================================================
rem  LS — instalação no Windows
rem  Uso:  scripts\instalar_windows.bat          (sem voz)
rem        scripts\instalar_windows.bat --voz    (com palavra de ativação e microfone)
rem ============================================================
setlocal
cd /d "%~dp0\.."

where py >nul 2>nul
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")

echo [LS] Criando o ambiente virtual em .venv ...
%PY% -m venv .venv
if errorlevel 1 goto :erro

call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :erro

echo [LS] Atualizando o pip ...
python -m pip install --upgrade pip
if errorlevel 1 goto :erro

echo [LS] Instalando dependencias principais (requirements.txt) ...
python -m pip install -r requirements.txt
if errorlevel 1 goto :erro

if /i "%~1"=="--voz" (
  echo [LS] Instalando dependencias de voz (requirements-voice.txt) ...
  python -m pip install -r requirements-voice.txt
  if errorlevel 1 goto :erro
)

echo [LS] Registrando o pacote local (permite iniciar com o Windows de qualquer pasta) ...
python -m pip install -e .
if errorlevel 1 goto :erro

if not exist ".env" (
  copy /y ".env.example" ".env" >nul
  echo [LS] Arquivo .env criado a partir de .env.example.
)

echo.
echo [LS] Instalacao concluida.
echo   1. Abra o arquivo .env e cole sua GEMINI_API_KEY (veja o README, secao 3).
echo   2. Inicie com:  scripts\iniciar_ls.bat
echo.
endlocal
exit /b 0

:erro
echo.
echo [LS] A instalacao falhou. Leia a mensagem acima.
echo      Guia de solucao de problemas: README.md, secao 9.
echo.
endlocal
exit /b 1
