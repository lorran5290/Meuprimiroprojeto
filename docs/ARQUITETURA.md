# Arquitetura do LS

Este documento explica as escolhas técnicas, como os componentes conversam, como o programa inicia e
para, e onde estão as fronteiras de segurança. Para instalar e usar, veja o [README](../README.md).
Para o que foi testado, veja [STATUS_TESTES.md](STATUS_TESTES.md).

## 1. Visão geral

```
┌──────────────── Janela nativa (pywebview → WebView2) ─────────────────┐
│  index.html · styles.css · core.js (núcleo canvas) · app.js          │
│  • REST  /api/*   (header X-LS-Token)                                 │
│  • WS    /ws      (eventos ao vivo, token na query)                   │
└──────────────┬───────────────────────────────────────────▲────────────┘
               │ pedidos                                     │ eventos
┌──────────────▼───────────────────────────────────────────┴────────────┐
│ Processo Python: ls_assistant                                         │
│                                                                       │
│  ui.server (FastAPI)            AppContext (context.py)               │
│        │                             │                                 │
│        ▼                             ▼                                 │
│  automation.TaskRunner ──► ai.Assistant ──► ai.GeminiProvider ──► API  │
│   (1 pedido por vez,          │   (laço de ferramentas,               │   Google
│    cancelável)                │    modo local de contingência)        │   Gemini
│                               ▼                                       │
│                     tools.ToolExecutor ◄── tools.ToolRegistry         │
│                       │   valida args (Pydantic)                      │
│                       │   aplica risco (security.decide)              │
│                       │   pede aprovação (ConfirmationBroker)         │
│                       │   limite de tempo, cancelamento, auditoria    │
│                       ▼                                               │
│     tools.builtin ──► desktop/ (arquivos, apps, janelas, sistema,     │
│                       shell) · memory/ (SQLite) · vision/ (captura)   │
│                                                                       │
│  voice.VoiceController ──► voice.VoiceListener (Vosk + microfone)     │
│                        └─► voice.tts (System.Speech do Windows)       │
│                                                                       │
│  events.EventBus  ◄── todos os módulos publicam; a UI assina          │
└───────────────────────────────────────────────────────────────────────┘
```

## 2. Escolhas de tecnologia e motivos

| Decisão | Escolha | Por quê | Alternativas consideradas |
|---|---|---|---|
| Núcleo | **Python 3.11+** | Bibliotecas maduras para Windows (ctypes, psutil, sqlite3, SDK oficial do Gemini) | Node (menos acesso nativo direto a janelas) |
| Interface | **pywebview** (WebView2) + HTML/JS | Janela moderna sem empacotar Chromium inteiro; um único processo Python controla tudo | Electron + React: mais peso (≈150 MB de runtime), duas linguagens e dois processos para manter |
| Núcleo visual | **Canvas 2D** | Leve o bastante para a RTX 2050 e para notebooks sem GPU dedicada; sem build de frontend | Three.js/WebGL: mais peso e sem ganho claro para anéis, partículas e ondas |
| API de IA | **google-genai** (SDK oficial atual) | Chamadas de função, imagens, pesquisa com fontes; SDK mantido pelo Google | `google-generativeai` (legado) |
| Modelo padrão | **gemini-3.5-flash** | Testado com chaves reais: responde em português, faz chamadas de função | `gemini-2.5-flash`: descontinuado para novas chaves |
| Persistência | **SQLite** (biblioteca padrão) | Sem servidor, sem dependência extra, arquivo único e portátil | FTS5/busca vetorial: não necessário para o volume de uma memória pessoal; a busca é por palavras-chave com pontuação |
| Palavra de ativação | **Vosk** com gramática restrita às palavras de ativação | Offline; áudio nunca vai para a nuvem; gramática limita falsos positivos | Porcupine: exige conta e treinamento de palavra; SpeechRecognition na nuvem: viola a regra de não enviar tudo |
| Captura de voz | **sounddevice** | Usa PortAudio com wheel pronto para Windows | pyaudio: instalação mais difícil no Windows |
| Síntese de voz | **System.Speech (SAPI) via PowerShell** | Já vem no Windows, tem vozes pt-BR, zero dependências, interrupção imediata (encerrar o processo) | pyttsx3: interrupção frágil; TTS na nuvem: envia o texto da conversa para fora |
| Servidor local | **FastAPI + uvicorn**, só em 127.0.0.1 | Validação tipada dos pedidos, WebSocket nativo | Servidor HTTP próprio: mais código para manter |
| Automação de janelas | **ctypes/user32** | Sem dependência extra; APIs oficiais do Windows | pywin32, pyautogui: mais peso; pyautogui depende da tela e de foco |
| Bandeja | **pystray** (opcional) | Simples; se faltar, a janela segue normal | — |

## 3. Como os componentes se comunicam

1. **Interface → núcleo:** chamadas REST em `/api/*` com o cabeçalho `X-LS-Token`. O token é gerado a cada execução
   (`secrets.token_urlsafe`) e entregue à janela pelo fragmento da URL (`#t=`), que não vai para logs de servidor.
   O servidor só aceita os hosts `127.0.0.1` e `localhost` (proteção contra DNS rebinding).
2. **Núcleo → interface:** um `EventBus` em memória publica eventos (`state`, `task`, `message`, `tool`,
   `confirmation`, `voice`, `emergency`). O WebSocket `/ws` entrega os eventos ao vivo e, ao conectar, reenvia
   os últimos 100 seguidos de `replay_end`. Eventos antes do `replay_end` são histórico (não abrem aprovações).
3. **Pedido de texto ou voz:** `TaskRunner.submit` cria uma thread, um `CancelToken` e publica `processing`.
   `Assistant.respond` monta o contexto (memória não sensível relevante), chama o modelo e executa as chamadas de
   ferramenta pelo `ToolExecutor`. Os resultados voltam ao modelo, que responde com base neles.
4. **Voz:** `VoiceController` mantém o microfone. Um thread lê blocos PCM de 250 ms e os entrega a
   `VoiceListener.feed`, que é uma máquina de estados: **espera** (só palavra de ativação, com filtro de volume)
   → **acordado** (captura o comando com um reconhecedor sem gramática) → **espera**. O comando vai para o
   `TaskRunner` como qualquer outro pedido.

## 4. Ciclo de vida

**Início** (`ls_assistant.app.main`):

1. `load_settings`: valores padrão, `settings.json`, `.env`, variáveis do sistema. Valores inválidos param aqui.
2. `configure_logging`: console e arquivo rotativo, com filtro que mascara a chave.
3. `build_context`: memória (com dados iniciais na primeira vez), auditoria, aprovações, parada de emergência,
   política de caminhos, catálogo de ferramentas, provedor Gemini (se houver chave), assistente, executor de
   tarefas, voz (desligada por padrão).
4. Porta livre, token novo, servidor uvicorn em thread separada, espera até estar pronto.
5. Janela pywebview (ou apenas o servidor com `--no-window`). Se a janela falhar, o erro é mostrado e o LS encerra limpo.

**Encerramento** (fechar a janela, Ctrl+C ou "Sair" na bandeja): `AppContext.shutdown` cancela o pedido em andamento,
recusa aprovações pendentes, para o microfone e a fala, encerra o executor de ferramentas e fecha SQLite.
Depois o servidor é sinalizado para parar e a thread é aguardada por até 5 s.

## 5. Modelo de segurança

Regra central: **o modelo pede, o executor decide.** O Gemini só recebe a lista de ferramentas e devolve pedidos.
Nenhuma ação roda fora de `ToolExecutor.execute`.

| Camada | O que faz | Onde |
|---|---|---|
| Lista fechada | Só as ferramentas registradas em `builtin.py` existem; nomes desconhecidos viram `unknown_tool` | `tools/registry.py` |
| Argumentos tipados | Pydantic valida cada chamada antes de qualquer efeito | `tools/executor.py` |
| Risco declarado | `READ`, `REVERSIBLE` (automático), `CONFIRM` e `EXTERNAL` (aprovação), `BLOCKED` (nunca) | `security/permissions.py` |
| Aprovação | Pedido visível, expiração (padrão 120 s), recusa automática por tempo, cancelamento junto com a parada | `security/confirmations.py` |
| Caminhos | Resolução com links simbólicos; só pastas permitidas; áreas do sistema bloqueadas | `security/paths.py` |
| Exclusão reversível | "Excluir" move para a quarentena do LS; não há apagamento permanente de arquivos | `desktop/files.py` |
| Planos em duas etapas | Organizar e excluir primeiro geram um plano (leitura); a aplicação exige aprovação | `desktop/files.py` |
| Verificação | Abrir app, janela ou site só vira "sucesso" se for confirmado; senão, `unverified` | `desktop/apps.py`, `desktop/windows.py` |
| Limite de tempo | Cada ferramenta tem tempo máximo; estouro vira `timeout` | `tools/executor.py` |
| Cancelamento | Cooperativo: tokens em loops longos; a parada de emergência cancela tudo | `security/cancel.py`, `security/emergency.py` |
| Auditoria | Toda execução é registrada (inclusive recusas), com argumentos mascarados | `security/audit.py` |
| Memória | Recusa senhas, tokens e chaves; sensíveis ficam fora do contexto do modelo | `memory/store.py` |
| Conteúdo não é instrução | Resultados de ferramentas e documentos são marcados como dados no prompt | `ai/prompts.py` |
| Interface | Token por sessão, host restrito, sem chave no navegador, texto sempre com `textContent` | `ui/server.py`, `ui/static/app.js` |
| Logs | Filtro que mascara a chave configurada e qualquer padrão com cara de chave Google | `logging_setup.py` |

## 6. Contratos entre módulos

- **`ai/base.py`**: `AIProvider` (`generate`, `web_search`) e os tipos `Turn`, `ModelReply`, `ToolDeclaration`.
  Trocar de modelo significa implementar outro provedor, sem mudar o orquestrador.
- **`tools/base.py`**: `ToolSpec` (nome, descrição, modelo de argumentos, risco, tempo limite, descrição da ação)
  e `ToolOutcome` (status padronizado: `ok`, `unverified`, `failed`, `denied`, `cancelled`, `timeout`,
  `unavailable`, `invalid_args`, `unknown_tool`).
- **`voice/tts.py`**: `TTSEngine` (`speak`, `stop`, `list_voices`). `NullTTS` é a implementação sem voz.
- **`voice/listener.py`**: `Recognizer` no formato do Vosk; os testes usam reconhecedores falsos.
- **`events.py`**: `EventBus.emit(tipo, payload)`. Qualquer módulo pode publicar; só a interface assina.

## 7. Como adicionar uma habilidade

1. Crie a função em um módulo (por exemplo `desktop/…`) que devolva `ActionResult` ou levante `LSError`.
2. Declare argumentos com Pydantic (com `Field(description=…)`, que aparece para o modelo).
3. Registre em `tools/builtin.py` com nome, risco, tempo limite e, se for `CONFIRM`, uma função `describe`.
4. Escreva testes em `tests/` (o executor e a auditoria já são cobertos).

Se a ação tiver efeito externo (enviar, publicar, comprar), use `Risk.EXTERNAL`. A regra de aprovação é a mesma de `CONFIRM`.

## 8. Riscos técnicos e como estão tratados

| Risco | Tratamento | Situação |
|---|---|---|
| Ação aprovada por engano (tecla ou clique) | Foco inicial em Recusar; Aprovar desarmado por 1,5 s; reproduzido e corrigido durante os testes | Testado na interface |
| Modelo afirmar sucesso sem resultado | Status `unverified` e `failed` vão para o modelo e para a interface; a resposta é checada nos testes | Testado |
| Replay de eventos antigos reabrir aprovações | Marcador `replay_end` no WebSocket | Testado na interface |
| Limite de cota ou indisponibilidade da IA | Retentativas com espera, fallback de modelo, modo local e mensagem clara | Testado com 429 real |
| Falsos acionamentos da palavra | Gramática restrita, filtro de volume, cooldown, palavras configuráveis | Lógica testada; áudio real não |
| Latência de voz | Vosk offline; fala por SAPI sem rede | Não medido |
| Janela e apps no Windows | Código por ctypes e os.startfile; backends simulados nos testes | Não executado no Windows |
| Desempenho do núcleo na RTX 2050 | Canvas 2D; partículas limitadas pela intensidade | Não medido em hardware |
| Pesquisa com fontes depender de cota/recurso | Sem fonte, o LS admite em vez de inventar | Testado (quando a cota permite) |

## 9. Estado do plano de fases

| Fase | Entrega | Estado |
|---|---|---|
| 1. Núcleo funcional | Gemini, conversa, interface, memória local | **Implementada e testada** |
| 2. Voz | Ativação, reconhecimento, fala, indicadores | **Implementada**; áudio real não testado |
| 3. Controle do Windows | Apps, janelas, arquivos, permissões | **Implementada** (arquivos testados; janelas/apps por simulação). Teclado/mouse **pendentes** |
| 4. Núcleo holográfico | Estados reais, animação, intensidade | **Implementada** em canvas 2D; sem 3D |
| 5. Agente de tarefas | Planejamento, ferramentas, progresso, cancelamento | **Implementada** pelo laço de ferramentas e pelo TaskRunner; tarefas longas de ponta a ponta não testadas |
| 6. Visão e expansão | Captura sob demanda, análise pelo modelo, módulos | **Implementada** em partes; OCR dedicado não existe (o modelo analisa a imagem) |

Pendências explícitas: teclado e mouse, leitura de páginas abertas no navegador, envio de mensagens (fora do escopo
por risco), monitoramento contínuo de tela (desativado por padrão; não implementado) e criptografia em repouso da memória.
