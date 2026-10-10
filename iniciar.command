#!/bin/bash
# Abre o Jarvis com um clique: instala o necessário, pede a chave na primeira vez e inicia o servidor.
cd "$(dirname "$0")" || exit 1

fail() {
  echo "$1"
  read -r -p "Aperte Enter para fechar..."
  exit 1
}

command -v node >/dev/null 2>&1 || fail "Node.js não encontrado. Instale a versão LTS em https://nodejs.org e rode este arquivo de novo."

if [ ! -d node_modules ]; then
  echo "Instalando as dependências. Isso pode levar alguns minutos..."
  npm install || fail "Falha ao instalar as dependências."
fi

[ -f .env ] || cp .env.example .env

if ! grep -qE '^ANTHROPIC_API_KEY=.' .env && ! grep -qE '^JARVIS_MODO_TESTE=1' .env; then
  echo "Cole sua chave da API da Anthropic e aperte Enter."
  echo "Se ainda não tiver chave, digite TESTE e aperte Enter para usar o modo de teste, sem custo."
  read -r APIKEY
  if [ "$APIKEY" = "TESTE" ]; then
    grep -v '^JARVIS_MODO_TESTE=' .env > .env.tmp && echo 'JARVIS_MODO_TESTE=1' >> .env.tmp && mv .env.tmp .env
  elif [ -n "$APIKEY" ]; then
    grep -v '^ANTHROPIC_API_KEY=' .env > .env.tmp && printf 'ANTHROPIC_API_KEY=%s\n' "$APIKEY" >> .env.tmp && mv .env.tmp .env
  fi
fi

echo "Iniciando o Jarvis. O navegador vai abrir em http://localhost:3000"
echo "Para desligar, feche esta janela ou aperte Ctrl+C."
( sleep 4 && command -v open >/dev/null 2>&1 && open http://localhost:3000 ) &
npm start
