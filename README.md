# LS — assistente pessoal para Windows

Assistente inspirado no JARVIS, com identidade e implementação próprias. Ele conversa em português
do Brasil com o **Google Gemini**, lembra do que você autorizou, abre programas e organiza arquivos,
pede sua aprovação antes de qualquer ação destrutiva e tem um núcleo animado que reflete o estado real
do sistema.

> **Antes de começar:** leia a seção 4 (chave da API) e o arquivo [`docs/STATUS_TESTES.md`](docs/STATUS_TESTES.md).
> Ele diz o que já foi testado, o que ainda não foi e o que depende de configuração sua.

---

## 1. O que o LS faz hoje

| Área | Situação |
|---|---|
| Conversa com Gemini (português) | Funciona e foi testada com a API real |
| Memória pessoal (SQLite, editável, com backup) | Funciona; dados iniciais de ExNet Fiber e DOM CULINÁRIO |
| Aprovações antes de ações sensíveis | Funciona; testada na interface real |
| Abrir apps, janelas, arquivos, pastas, sites | Implementado; APIs do Windows **não executadas ainda neste ambiente** |
| Estado do computador (CPU, memória, disco, rede, temperatura quando disponível) | Funciona |
| Captura de tela sob demanda (com aprovação) | Implementado; não testado no Windows |
| Palavra de ativação "LS" e fala | Implementado com Vosk (offline) e voz do Windows; **não testado com microfone real** |
| Núcleo holográfico com estados reais | Funciona no navegador (canvas 2D) |
| Parada de emergência e cancelamento | Funciona |
| Teclado e mouse (digitar, atalhos, cliques) | **Não implementado** (ver seção 11) |

---

## 2. Requisitos

- Windows 10 (22H2 ou superior) ou Windows 11.
- **Python 3.11 ou mais novo** (https://www.python.org/downloads/). Marque *"Add python.exe to PATH"* na instalação.
- **WebView2 Runtime** para a janela. Ele já vem no Windows 11. No Windows 10, instale o *Evergreen Bootstrapper* em
  https://developer.microsoft.com/microsoft-edge/webview2/ (o LS continua funcionando pelo navegador se não houver).
- Conexão com a internet para falar com o Gemini.
- Microfone e um modelo de voz do Vosk, **somente** se quiser ativação por voz (seção 5).

---

## 3. Instalação passo a passo (Windows)

Os comandos abaixo são para o **PowerShell** (o padrão do Windows 11 no Terminal). Se o projeto ainda
não estiver na sua máquina, primeiro clone o repositório (`git clone https://github.com/lorran5290/Meuprimiroprojeto.git`).

```powershell
# 1) Entre na pasta do projeto
cd C:\Users\SeuUsuario\Meuprimiroprojeto

# 2) Baixe a branch do LS (ela foi criada depois do seu clone, então é preciso buscar)
git fetch origin ccr-86bee323-knq7uo
git checkout ccr-86bee323-knq7uo
#    Se o Git disser que a branch não existe localmente, use:
#    git checkout -b ccr-86bee323-knq7uo origin/ccr-86bee323-knq7uo

# 3) Instale tudo (cria .venv, instala dependências e cria o arquivo .env)
.\scripts\instalar_windows.bat
#    Com voz (palavra "LS" e microfone), use:
#    .\scripts\instalar_windows.bat --voz

# 4) Abra o .env no Bloco de Notas e cole a chave (seção 4)
notepad .env

# 5) Inicie o LS
.\scripts\iniciar_ls.bat
```

**Atenção ao terminal:**

- No **PowerShell**, scripts da pasta atual precisam de `.\` antes do caminho (`.\scripts\...`).
- Não cole linhas com `REM` no PowerShell: `REM` é do `cmd`. No PowerShell, comentários começam com `#`.
- No **Prompt de Comando (cmd)**, os mesmos comandos ficam sem `.\`: `scripts\instalar_windows.bat`.

O que o instalador faz: cria o ambiente `.venv`, instala as dependências fixadas em `requirements.txt`,
registra o pacote localmente (`pip install -e .`) e copia `.env.example` para `.env`.
Ele **não** grava nenhuma chave; isso é você quem faz.

Para rodar os testes automatizados depois (PowerShell):

```powershell
.\scripts\testar.bat
```

---

## 4. Configurar a API do Gemini

1. Acesse https://aistudio.google.com/apikey e crie uma chave de API.
2. Abra o arquivo `.env` (na raiz do projeto) com o Bloco de Notas e preencha, **sem aspas**:

   ```ini
   GEMINI_API_KEY=cole_sua_chave_aqui
   GEMINI_MODEL=gemini-3.5-flash
   ```

3. Salve e reinicie o LS.

Pontos importantes:

- **Nunca** coloque a chave no código, no README, em prints ou em commits. O `.gitignore` já exclui `.env`.
  O LS também nunca mostra a chave na interface nem nos logs (ele mascara qualquer valor com cara de chave).
- Se a chave aparecer em algum lugar público, **revogue e crie outra** no AI Studio.
- O modelo `gemini-2.5-flash` **não está mais disponível para novas chaves**. Por isso o padrão é `gemini-3.5-flash`.
  Você pode trocar o modelo na tela de Configurações, sem reiniciar.
- Sem chave, o LS funciona em **modo local**: consulta memória, mostra o estado do computador e abre aplicativos.
  Ele avisa isso na conversa.
- **Limites de uso:** se a cota for atingida, o LS informa e passa ao modo local; ele não inventa respostas.
  No **plano gratuito** o limite diário é baixo: durante os testes, a API informou **20 requisições por dia** para o
  modelo, e a cota acabou no mesmo dia. Para uso diário, ative o faturamento no Google AI Studio ou aguarde a renovação.
  Pesquisa na web com fontes depende de cota e de o recurso estar liberado para sua chave.

---

## 5. Configurar o microfone e a palavra de ativação (opcional)

A ativação por voz é local: o áudio só é analisado no seu computador pelo Vosk. Nada é enviado à nuvem por causa dela.

1. **Permissão do Windows:** *Configurações → Privacidade e segurança → Microfone* → ative o acesso para
   aplicativos de área de trabalho.
2. **Modelo de voz em português:** baixe um modelo pt-BR em https://alphacephei.com/vosk/models
   (por exemplo `vosk-model-small-pt-0.3`; confira o nome atual na lista). Descompacte em uma pasta, como
   `C:\modelos\vosk-model-small-pt-0.3`.
3. No `.env`, aponte para essa pasta:

   ```ini
   LS_VOSK_MODEL_PATH=C:\modelos\vosk-model-small-pt-0.3
   LS_VOICE_ENABLED=true
   LS_WAKE_WORD_ENABLED=true
   ```

4. Se houver mais de um microfone, descubra o índice e defina `LS_MIC_DEVICE=1` (por exemplo).
5. Reinicie. No LS, clique no botão de microfone: o indicador fica verde quando está ligado.
   Para desligar por completo, clique de novo. O botão **Falar** escuta um comando sem precisar da palavra.

Palavras de ativação padrão: `ls`, `ele esse`, `elesse` (variam conforme como o reconhecedor ouve).
Ajuste em `LS_WAKE_WORDS`. Palavras comuns demais podem gerar acionamentos falsos; o LS tem
intervalo mínimo entre acionamentos e filtro de volume para reduzir isso.

**Voz de resposta:** o LS usa as vozes instaladas no Windows (System.Speech). Para ver a lista, abra as
Configurações do LS → "Voz". Para mudar a velocidade e o volume, use os controles dali.
Para interromper a fala na hora, use o botão **Calar**.

---

## 6. Como usar

Abra a janela com `scripts\iniciar_ls.bat`. Você pode:

- **Escrever** no campo inferior e apertar Enter, ou
- **Falar**: diga "LS" e depois o comando (ou clique em Falar).

Exemplos:

- "LS, quais projetos estou desenvolvendo?"
- "LS, o que você sabe sobre a ExNet Fiber?"
- "LS, lembre que eu prefiro respostas curtas."
- "LS, abra o bloco de notas." (o LS confirma que o programa abriu)
- "LS, liste os arquivos da pasta Documentos."
- "LS, pesquise ferramentas de IA para criar sites e me diga as fontes."
- "LS, como está o uso de CPU e memória?"
- "LS, veja minha tela e explique esse erro." (pede sua aprovação para capturar)

**Aprovações:** ações como apagar memória, fechar janelas, capturar a tela ou aplicar um plano de
organização aparecem como cartão e pop-up. **Recusar** é o botão focado por padrão. **Aprovar** só fica
disponível depois de 1,5 s, para evitar um clique ou Enter acidental.
Se você não responder, a ação é **recusada automaticamente** após o prazo (padrão de 120 s).

**Parada de emergência:** o botão vermelho no topo cancela tarefas em andamento, recusa aprovações
pendentes e cala a fala. Novas ações ficam bloqueadas até você clicar em **Liberar**.

**Painéis à direita:** *Memória* (buscar, editar, corrigir, apagar, contradições, backup/importação),
*Sistema* (uso de recursos) e *Histórico* (conversas e registro de auditoria, que você pode apagar).

---

## 7. Configurações

Pela janela, em **Configurações**: modelo, intensidade dos efeitos visuais, resposta em voz, voz,
velocidade e volume, palavra de ativação, histórico e início com o Windows.

Pelo `.env` (veja `.env.example`, com comentários): pastas permitidas (`LS_ALLOWED_ROOTS`), pasta de dados
(`LS_DATA_DIR`), tempos limite, porta do servidor local e demais opções avançadas.

Precedência: valores padrão < preferências salvas pela janela (`settings.json`) < `.env` < variáveis do sistema.

**Iniciar com o Windows:** ative em Configurações. O LS grava uma entrada em
`HKCU\Software\Microsoft\Windows\CurrentVersion\Run` (sem administrador), iniciando minimizado na bandeja.
Desative na mesma tela para remover a entrada.

**Bandeja:** ao minimizar a janela, o LS vai para a bandeja (ícone azul perto do relógio) e **continua
ouvindo** a palavra de ativação. Pelo menu da bandeja você mostra a janela, liga/desliga o microfone ou
aciona a parada de emergência.

---

## 8. Privacidade e dados

- **Onde ficam os dados:** `%LOCALAPPDATA%\LS` (memória, auditoria, logs, planos, quarentena, backups).
  Pela configuração `LS_DATA_DIR` você escolhe outra pasta.
- **O que vai para o Gemini:** o que você digita ou fala, os itens de memória não sensíveis relevantes para a
  conversa, e o resultado das ferramentas que você usou. Capturas de tela só são enviadas quando você aprova.
- **Memória sensível:** itens marcados como sensíveis ficam fora do contexto enviado ao modelo e aparecem mascarados.
- **Senhas, tokens e chaves** são recusados pela memória e mascarados nos registros.
- **Apagar:** cada memória pode ser apagada; o histórico e a auditoria têm botões de limpeza.
- **Backup:** *Memória → Fazer backup* gera um JSON legível. Importe em *mesclar* (padrão) ou *substituir*
  (o LS salva antes uma cópia da memória atual).
- **Sem exclusão definitiva por acidente:** "excluir" arquivos envia para a **quarentena do LS**, de onde é possível
  restaurar. O LS não apaga nada permanentemente.
- **Pastas protegidas:** o LS só toca nas pastas permitidas e nunca em áreas do sistema (`Windows`, `Program Files`,
  `AppData`, `.ssh` etc.), mesmo que um link simbólico aponte para elas.

---

## 9. Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `pathspec 'ccr-86bee323-knq7uo' did not match any file(s) known to git` | O clone não tem a branch ainda | `git fetch origin ccr-86bee323-knq7uo` e depois `git checkout ccr-86bee323-knq7uo` (seção 3) |
| `Não foi possível carregar o módulo 'scripts'` ao rodar `scripts\...` | No PowerShell, caminhos da pasta atual precisam de `.\` | Use `.\scripts\instalar_windows.bat` e `.\scripts\iniciar_ls.bat` |
| `'REM' não é reconhecido` / `'sem' não é reconhecido` | Linhas `REM` foram coladas no PowerShell | Use os comandos da seção 3 (PowerShell). `REM` é só do cmd |
| `.bat` abre mas para no meio, ou `goto` não funciona | Arquivo `.bat` com quebras de linha Unix | Atualize o clone; o arquivo `.gitattributes` faz o Git entregar CRLF no Windows. Se persistir, rode `git checkout -- scripts` |
| `instalar_windows.bat` diz que `python` não é reconhecido | Python não está no PATH | Reinstale o Python marcando *Add python.exe to PATH*, ou use `py -3` |
| Janela não abre; erro de WebView2 | Runtime ausente (comum no Windows 10) | Instale o WebView2 Runtime (seção 2). Enquanto isso: `scripts\iniciar_ls.bat --no-window` e abra a URL que aparece no console |
| Pill "IA: modo local" | `GEMINI_API_KEY` vazia ou não lida | Confira o `.env` (sem aspas, sem espaços em volta do `=`) e reinicie |
| "A cota de uso da API Gemini foi atingida" | Limite do plano ou da chave | Aguarde ou verifique o plano no AI Studio. O LS segue em modo local |
| "chave ... recusada" (auth) | Chave errada, revogada ou sem acesso ao modelo | Gere outra chave; confirme que o modelo do `.env` está disponível para ela |
| "modelo indisponível" / 404 | Modelo descontinuado | Troque `GEMINI_MODEL` por um modelo atual (ex.: `gemini-3.5-flash`) |
| Voz não ativa; "Modelo de voz não encontrado" | `LS_VOSK_MODEL_PATH` errado | Aponte para a pasta descompactada do modelo |
| Voz ativa mas nunca reconhece "LS" | Microfone errado, volume baixo ou permissão | Teste `LS_MIC_DEVICE`; aumente o volume de entrada; verifique a permissão do Windows |
| Muitos acionamentos falsos | Palavra comum, ambiente barulhento | Use `LS_WAKE_WORDS` mais específicas; desative a palavra e use o botão Falar |
| "Não consegui abrir o microfone" | Outro programa usando o dispositivo | Feche o outro programa ou escolha outro `LS_MIC_DEVICE` |
| Ação "não confirmada" ao abrir um app | O Windows não expôs o processo (ex.: app que se reinicia) | Confira manualmente; o LS não declara sucesso sem confirmação |
| Porta já em uso | Outro programa usa a porta de `LS_PORT` | Deixe `LS_PORT=0` (automático) |
| Erro no console ao iniciar | Dependência faltando | Rode `scripts\instalar_windows.bat` de novo |
| "Caminho fora das pastas permitidas" | Pasta não está em `LS_ALLOWED_ROOTS` | Adicione a pasta na variável, separada por `;` |

Os logs ficam em `%LOCALAPPDATA%\LS\logs\ls.log`. Eles nunca contêm a chave da API.

---

## 10. Testes

```bat
scripts\testar.bat
```

Os testes automatizados (109) cobrem configuração, segurança, memória, arquivos, executor, provedor Gemini
com erros simulados, orquestrador, voz com reconhecedores falsos, janelas e aplicativos com backends simulados,
e a API/WebSocket com token. Os testes "live" (4) chamam a API real: não entram na execução padrão, rodam com
`-m live` e exigem a chave no ambiente. Se a cota diária estiver esgotada, eles são pulados com esse motivo:

```bat
set GEMINI_API_KEY=cole_sua_chave_aqui
.venv\Scripts\python.exe -m pytest -m live
```

O relatório detalhado de cada teste de aceitação está em [`docs/STATUS_TESTES.md`](docs/STATUS_TESTES.md).

---

## 11. Limitações conhecidas

- **Teclado e mouse** (digitar em outros programas, atalhos, cliques em coordenadas) **não estão implementados**.
  Essa é a próxima tarefa da Fase 3.
- **Ler uma página web** que você abriu no navegador não é possível: o LS abre o navegador, mas não lê a página.
  Para pesquisar e resumir, use a pesquisa com fontes.
- **Não há envio de e-mails, mensagens ou compras.** Essas ações são de risco externo e ficam fora do escopo atual.
- **Monitoramento contínuo de tela:** não existe. A captura é sempre sob demanda, com aprovação.
- **OCR dedicado:** não há mecanismo separado; o Gemini analisa a imagem capturada.
- **Núcleo visual:** usa canvas 2D (leve para a RTX 2050). Não é 3D; a decisão está em `docs/ARQUITETURA.md`.
- **Memória sem criptografia em disco:** protegida pelas permissões do seu usuário do Windows. Não use
  o LS num computador compartilhado sem conta separada.
- **Testes de janelas, apps, microfone, fala e início automático** foram feitos por simulação; não foram
  executados em um Windows real neste ambiente. Veja o status detalhado.

---

## 12. Estrutura do projeto

```
ls_assistant/
  app.py, __main__.py   montagem e ponto de entrada (python -m ls_assistant)
  config.py             configuração (.env, settings.json, variáveis)
  context.py            serviços compartilhados (AppContext)
  events.py             barramento de eventos (núcleo → interface)
  ai/                   contrato de IA, provedor Gemini, orquestrador, prompts e modo local
  automation/           execução de pedidos em segundo plano, cancelável
  desktop/              arquivos, aplicativos, janelas, sistema, navegador e área de transferência
  memory/               memória SQLite, dados iniciais e backups
  security/             riscos, aprovações, auditoria, caminhos protegidos e parada de emergência
  settings/             preferências validadas e início com o Windows
  tools/                catálogo de ferramentas, registro e executor
  ui/                   servidor local (FastAPI/WebSocket), janela (pywebview), bandeja e static/
  vision/               captura de tela sob demanda
  voice/                palavra de ativação, microfone, máquina de estados e fala
tests/                  suíte automatizada
scripts/                instalação, inicialização e testes no Windows
docs/                   arquitetura e status dos testes
```

Mais detalhes em [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md).
