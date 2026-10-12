# Status dos testes e da implementação

Este documento separa três coisas: o que foi **implementado**, o que foi **testado de fato** (com a evidência
descrita) e o que **ainda depende de configuração ou de um Windows real**. Nada aqui é marcado como aprovado sem
ter sido executado.

Ambiente de testes: Linux (container), Python 3.13.16, Chromium headless (Playwright), API real do Gemini.
**Nenhum teste foi executado em Windows neste ambiente.** O alvo é Windows 10/11 com Python 3.11+.

## 1. Resumo

| Teste de aceitação | Status | Evidência principal |
|---|---|---|
| 1. Ativação ("LS") | ⚠️ Parcial | Lógica testada com reconhecedores falsos; microfone e Vosk reais **não testados** |
| 2. Conversação em português | ✅ Aprovado | API real + navegador: resposta coerente |
| 3. Voz e interrupção da fala | ❌ Não testado | Sem áudio no ambiente; implementação existe |
| 4. Abrir aplicativo e verificar | ⚠️ Parcial | Simulado; abertura real no Windows **não testada** |
| 5. Memória persiste após reinício | ✅ Aprovado | Reinício real do servidor; registros mantidos |
| 6. Listar documentos de uma pasta | ✅ Aprovado (Linux) | testes automatizados de listagem, pesquisa e leitura; pendente no Windows |
| 7. Confirmação antes de destruir | ✅ Aprovado | Testes + navegador (recusar, aprovar, Enter) |
| 8. Falha da API | ✅ Aprovado | 429 real; 503, 404, 403 e rede simulados |
| 9. Interface e minimizar | ❌ Não testado | pywebview/bandeja exigem Windows |
| 10. Cancelamento | ✅ Aprovado (automatizado) | Testes do executor, do orquestrador e API de emergência |

Legenda: ✅ aprovado com evidência · ⚠️ parcial · ❌ não testado.

## 2. Testes automatizados

Comando: `python -m pytest -o addopts=""`

- **109 passaram.** Os 4 testes "live" não entram na execução padrão (`-m 'not live'` no `pyproject.toml`).
- Lint: `ruff check --select F` sem erros no pacote nem nos testes.

Cobertura por área:

| Área | O que é verificado |
|---|---|
| Configuração | Precedência (padrão < settings.json < .env < ambiente), valores inválidos, chave nunca exposta |
| Segurança | Matriz de risco; caminhos fora das pastas, áreas do sistema e links simbólicos; aprovação aceita/recusada/expirada/cancelada; parada de emergência; auditoria com mascaramento |
| Memória | Categorias, datas, recusa de senhas, CPF como sensível, busca, contradições, correções, exclusão, persistência ao reabrir, histórico, dados iniciais aplicados uma vez, backup (mesclar e substituir) |
| Arquivos | Listagem, leitura, pesquisa sem acento, criação sem sobrescrever, mover/copiar/renomear sem sobrescrever, duplicados por hash, plano de organização em duas etapas, quarentena e restauração |
| Executor | Ferramenta inexistente, argumentos inválidos, risco BLOCKED, aprovação e recusa reais (de outra thread), timeout, exceção oculta do modelo, status `unverified`, emergência |
| Provedor Gemini | Parsing de texto e chamadas de função, partes com assinatura preservadas, 429 (uma repetição e depois aviso), 503 (três tentativas e fallback de modelo), 404 (próximo modelo), 403 (sem repetir), rede |
| Orquestrador | Resposta simples, ida e volta de resultados de ferramenta, negação sem afirmar sucesso, modo local com IA indisponível, cancelamento, limite de passos, imagem anexada, contexto sem itens sensíveis |
| Voz | Palavra inteira (não substring), cooldown, remoção do comando, gramática, silêncio nunca chega ao reconhecedor, fluxo espera→acordado→comando, botão sem palavra, tempo limite, cancelamento |
| Aplicativos e janelas | Busca no Menu Iniciar, alias verificado por PID, verificação negativa, ambiguidade pergunta em vez de chutar, minimizar/fechar verificados |
| Shell | Só http/https; `javascript:` e `file:` recusados; URL de pesquisa codificada |
| API e WebSocket | Token obrigatório, proteção de host (DNS rebinding), chat com 202 e modo local, CRUD de memória, recusa de segredos, configurações validadas, importação restrita, aprovação via API, WebSocket com token e eventos, parada de emergência |

Defeitos que os testes encontraram e que foram corrigidos:

- `normalize_url` aceitava `javascript:alert(1)` transformando em `https://javascript:alert(1)`.
- A palavra de ativação não casava quando havia vírgula ("ele esse,").
- O detector de segredos recusava "secreto" (casava com "secret").
- O roteador local não acionava a ferramenta de sistema com "estado do computador".

## 3. Testes de API real (Gemini)

Comando: `GEMINI_API_KEY=… python -m pytest -m live`

- **Execução com a API real, antes da cota esgotar:** 3 passaram, 1 pulou. Passaram: conversa em português
  (resposta com "Brasília"), chamada de função (`abrir_pasta` com o argumento correto) e chave inválida
  tratada como erro claro sem vazar a chave. Pulou: pesquisa com fontes, por cota.
- **Última execução (cota diária já esgotada):** 1 passou (chave inválida) e 3 foram pulados com o motivo
  "cota da API esgotada". Testes de cota **não reprovam** o código: um erro 429 é tratado como condição externa.

**Limite importante:** a chave usada nos testes está no plano gratuito, que informou **20 requisições por dia**
para o modelo. Os testes consumiram essa cota no mesmo dia. Por isso, o E2E com a IA real que inclui uma
aprovação gerada pelo próprio modelo **não pôde ser repetido** depois; a aprovação foi validada com um provedor
roteirizado (seção 4). Para repetir o teste completo, é preciso cota disponível (faturamento ativo ou renovação).

Observações reais do serviço, durante a validação:

- `gemini-2.5-flash`: **404**, descontinuado para novas chaves. Por isso o padrão é `gemini-3.5-flash`.
- `gemini-3.8-flash`: **503** (alta demanda). Por isso há retentativa e modelo de reserva.
- Pesquisa com Google Search e geração de texto: **429** (cota) em momentos de uso intenso. O LS informou o limite,
  não inventou resultados e passou para o modo local.
- Latência observada de uma conversa curta: cerca de 2,4 s.

## 4. Testes de interface no navegador (Chromium real)

Três rodadas com o servidor real e um servidor de teste com provedor roteirizado (para não depender de cota):

- **Conexão e estado:** pill "Conectado", "IA: gemini-3.5-flash", núcleo passando por *EM ESPERA → PROCESSANDO → CONCLUÍDO*.
- **Memória real:** a resposta sobre projetos veio dos dados do banco (ExNet Fiber e DOM CULINÁRIO).
- **Animação viva:** após *CONCLUÍDO*, o desenho do núcleo continua mudando (verificado comparando quadros).
- **Aprovação, caminho de recusa:** cartão e pop-up aparecem; "Recusar" registra `recusado pelo usuário`; nada é alterado;
  a resposta do LS diz isso.
- **Aprovação, caminho de aprovação:** "Aprovar" fica desabilitado nos primeiros 1,5 s e depois funciona.
  Como a memória já não existia, a ferramenta retornou `falhou` e o LS disse "Não executei a ação".
- **Layout:** sem rolagem horizontal em 390 px; campo de digitar visível em 1280×800 (medido: termina em 785 px).
- **Console:** o erro de JavaScript que parava o núcleo após *CONCLUÍDO* foi corrigido; o 404 de `favicon` também.

### Incidente de segurança encontrado e corrigido

Durante os testes, a auditoria registrou **uma aprovação que eu não tinha pedido** (`esquecer_memoria` → `aprovado`).
A investigação reproduziu o mecanismo: o modal abria com **foco em "Aprovar"**, e um Enter a mais aprovava a
exclusão. Correções:

1. Foco inicial em **"Recusar"** (o lado seguro).
2. **"Aprovar" desarmado por 1,5 s** após o pedido aparecer.
3. Pedidos que chegam no replay de reconexão **não abrem mais o modal**; o servidor envia `replay_end` e a lista de
   aprovações é reconstruída a partir do estado real.

Depois das correções, reproduzi o Enter com o modal aberto: foco em "Recusar", ação negada, nada aprovado.
Não consigo afirmar com certeza que o Enter foi exatamente a causa da aprovação original; o mecanismo está
reproduzido e corrigido.

## 5. Teste de aceitação a teste de aceitação

### Teste 1 — Ativação ("LS") — ⚠️ Parcial
- **Testado:** palavra inteira, cooldown, remoção do comando, silêncio ignorado, fluxo completo e tempo limite, com reconhecedores falsos.
- **Não testado:** microfone real, modelo Vosk real, latência, falsos acionamentos em ambiente real.
- **Para concluir:** instalar `requirements-voice.txt`, baixar um modelo pt-BR, rodar e dizer "LS" em voz alta.

### Teste 2 — Conversação em português — ✅ Aprovado
- API real: resposta coerente em português (teste live e navegador).

### Teste 3 — Voz e interrupção — ❌ Não testado
- Implementado: fala por System.Speech do Windows; interrupção encerra o processo de fala; o botão **Calar** e a
  parada de emergência chamam essa interrupção.
- **Não testado:** áudio de saída e a interrupção audível. Dependência: Windows com voz pt-BR instalada.

### Teste 4 — Abrir aplicativo e verificar — ⚠️ Parcial
- **Testado por simulação:** alias (`calculadora`) verificado por PID; app que não permanece aberto vira
  `nao_verificado`; atalho do Menu Iniciar verificado por processo novo.
- **Não testado:** abertura real de um programa no Windows.

### Teste 5 — Memória persiste após reinício — ✅ Aprovado
- Evidência: a exclusão de uma memória feita numa execução permaneceu depois de o servidor ser encerrado e iniciado de novo
  (contagem de 8 itens mantida). Testes automatizados também reabrem o banco.

### Teste 6 — Listar documentos de uma pasta — ✅ Aprovado no Linux
- Listagem, pesquisa e leitura verificadas com arquivos reais em pasta temporária.
- **Pendente:** execução no Windows (acentos, caminhos e permissões podem diferir).

### Teste 7 — Confirmação antes de operação destrutiva — ✅ Aprovado
- Automatizado: aprovação, recusa e expiração não executam a ação.
- Navegador real: recusa por clique, aprovação após o intervalo e Enter com o modal aberto (ver seção 4).

### Teste 8 — Falha da API — ✅ Aprovado
- **Natural:** 429 real; o LS disse o motivo, passou ao modo local e a interface seguiu funcionando.
- **Simulado:** 503 (retentativas e modelo de reserva), 404 (próximo modelo), 403 (sem repetir), falha de rede
  (repete e informa), e chave inválida (erro claro, sem vazar a chave).

### Teste 9 — Interface e minimizar — ❌ Não testado
- Implementado: minimizar a janela a oculta quando a bandeja está disponível; o núcleo segue rodando, inclusive a escuta.
- **Não testado:** pywebview, WebView2 e pystray exigem Windows.

### Teste 10 — Cancelamento — ✅ Aprovado (automatizado)
- Cancelamento antes da chamada ao modelo; durante a espera por aprovação; parada de emergência cancela tarefas,
  recusa aprovações, cala a fala e bloqueia novos pedidos até "Liberar" (testado pela API).
- **Limite:** o cancelamento é cooperativo. Uma ferramenta já em execução no sistema pode terminar; o LS só informa
  sucesso quando o resultado chega.

## 6. O que não foi feito (e por quê)

- **Teclado e mouse:** digitar em outros programas, atalhos e cliques não estão implementados. É a pendência mais
  importante da Fase 3.
- **Ler páginas abertas no navegador:** o LS abre o navegador, mas não lê a página. A pesquisa com fontes existe.
- **Envio de mensagens e compras:** não existem ferramentas de risco externo; nada é enviado para fora.
- **Monitoramento contínuo de tela:** não existe, por decisão de privacidade.
- **Criptografia em repouso da memória:** não implementada; a proteção depende da conta do Windows.
- **Testes em Windows e em Python 3.11/3.12:** não executados aqui.
- **Três dependências opcionais de voz** (`vosk`, `sounddevice`) não foram instaladas neste ambiente, então o
  código de integração com elas não foi executado.

## 7. Como reproduzir

```bat
REM Automatizados (sem chamar a API)
scripts\testar.bat

REM API real (gasta cota)
set GEMINI_API_KEY=sua_chave
.venv\Scripts\python.exe -m pytest -m live

REM Aplicativo
scripts\iniciar_ls.bat
```
