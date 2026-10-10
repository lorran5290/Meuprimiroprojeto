@echo off
setlocal EnableDelayedExpansion
title Jarvis
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 (
  echo Node.js nao encontrado. Instale a versao LTS em https://nodejs.org e rode este arquivo de novo.
  pause
  exit /b 1
)

if not exist node_modules (
  echo Instalando as dependencias. Isso pode levar alguns minutos...
  call npm install
  if errorlevel 1 (
    echo Falha ao instalar as dependencias.
    pause
    exit /b 1
  )
)

if not exist .env copy /y .env.example .env >nul

findstr /r /c:"^ANTHROPIC_API_KEY=." .env >nul 2>nul
if errorlevel 1 (
  findstr /r /c:"^JARVIS_MODO_TESTE=1" .env >nul 2>nul
  if errorlevel 1 (
    echo.
    echo Cole sua chave da API da Anthropic e aperte Enter.
    echo Se ainda nao tiver chave, digite TESTE e aperte Enter para usar o modo de teste, sem custo.
    set /p "APIKEY=Chave ou TESTE: "
    if /i "!APIKEY!"=="TESTE" (
      findstr /v /b /c:"JARVIS_MODO_TESTE=" .env > .env.tmp
      echo JARVIS_MODO_TESTE=1>> .env.tmp
      move /y .env.tmp .env >nul
    ) else if not "!APIKEY!"=="" (
      findstr /v /b /c:"ANTHROPIC_API_KEY=" .env > .env.tmp
      echo ANTHROPIC_API_KEY=!APIKEY!>> .env.tmp
      move /y .env.tmp .env >nul
    )
  )
)

echo.
echo Iniciando o Jarvis. O navegador vai abrir em http://localhost:3000
echo Para desligar, feche esta janela ou aperte Ctrl+C.
start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 4; Start-Process 'http://localhost:3000'"
call npm start
pause
