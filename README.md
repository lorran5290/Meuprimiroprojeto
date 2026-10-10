# Jarvis

Assistente de voz pessoal. Você fala (ou digita) e ele responde em voz alta, usando o Claude como cérebro e a sua conta Google para ler e anotar compromissos, ler e-mails e encontrar arquivos.

Exemplos do que você pode dizer:

- "Jarvis, anote pra mim amanhã às 13 horas um serviço."
- "Jarvis, o que tenho na agenda na sexta?"
- "Jarvis, tem e-mail não lido da minha contratante?"
- "Jarvis, crie um rascunho para a Ana dizendo que chego às 10."
- "Jarvis, acha o contrato de locação no meu Drive."

## O que ele faz

| Ferramenta | O que faz |
| --- | --- |
| Google Agenda | Lista eventos de um período e cria novos eventos na agenda principal |
| Gmail | Pesquisa e-mails e cria **rascunhos**. Ele nunca envia e-mail sozinho. |
| Google Drive | Procura arquivos pelo nome (somente leitura) |

Não há ferramenta para apagar ou alterar eventos existentes, e não há envio de e-mail. Se quiser isso no futuro, é uma decisão separada.

## Requisitos

- Node.js 18.17 ou mais novo
- Chrome ou Edge para a voz (o reconhecimento de voz do Firefox não funciona)
- Uma chave da API da Anthropic
- Uma conta Google e um projeto no Google Cloud (passo a passo abaixo)

## Instalação

```bash
npm install
cp .env.example .env
# preencha ANTHROPIC_API_KEY e as credenciais do Google no .env
npm start
```

Abra http://localhost:3000 no Chrome ou no Edge e permita o uso do microfone.

## Conectar o Google

Esta etapa é feita uma vez.

1. Acesse https://console.cloud.google.com e crie um projeto (por exemplo, "Jarvis").
2. Em **APIs e serviços > Biblioteca**, ative estas três APIs: **Google Calendar API**, **Gmail API** e **Google Drive API**.
3. Em **APIs e serviços > Tela de permissão OAuth**:
   - Tipo de usuário: **Externo**.
   - Preencha o nome do app e o seu e-mail de suporte.
   - Em **Usuários de teste**, adicione o seu próprio e-mail Google.
   - Mantenha o app no modo **Teste**. Em modo de teste o Google mostra um aviso de "app não verificado", e isso é esperado para uso pessoal.
4. Em **APIs e serviços > Credenciais**, clique em **Criar credenciais > ID do cliente OAuth**:
   - Tipo de aplicativo: **Aplicativo da Web**.
   - Em **URIs de redirecionamento autorizados**, adicione exatamente: `http://localhost:3000/auth/google/callback`
5. Copie o **ID do cliente** e o **Segredo do cliente** para o arquivo `.env` (`GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET`).
6. Reinicie o servidor e clique em **Conectar Google** na tela do Jarvis.

Pontos de atenção:

- No modo de teste, o Google expira a autorização a cada 7 dias. Quando isso acontecer, o Jarvis avisa que a conexão expirou e basta clicar em **Conectar Google** de novo.
- Os escopos pedidos são: editar eventos da agenda, ler o Gmail, criar rascunhos no Gmail e ler o Drive. O Jarvis não tem permissão para enviar e-mail.
- Para revogar o acesso a qualquer momento, use o botão **Desconectar** ou acesse https://myaccount.google.com/permissions.

## Variáveis de ambiente

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | (vazio) | Obrigatória para o Jarvis responder |
| `JARVIS_MODEL` | `claude-sonnet-5-5` | Modelo usado nas respostas |
| `JARVIS_TIMEZONE` | `America/Sao_Paulo` | Fuso para "hoje", "amanhã" e horários dos eventos |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | (vazio) | Credenciais OAuth do Google |
| `GOOGLE_REDIRECT_URI` | `http://localhost:3000/auth/google/callback` | Precisa ser igual ao cadastrado no Google Cloud |
| `PORT` | `3000` | Porta do servidor |
| `JARVIS_DATA_DIR` | `data` | Onde ficam os tokens do Google (ignorado pelo git) |

## Como usar a voz

- **Botão do microfone**: toca uma vez para falar um comando. Ele escuta até você parar.
- **Escutar sempre**: deixa o microfone aberto. Só responde quando você começa a frase com "Jarvis". Depois de uma resposta, você pode continuar por cerca de 12 segundos sem repetir o nome.
- **Voz do Jarvis**: liga ou desliga a resposta falada. As respostas também aparecem escritas.
- Se você só disser "Jarvis", ele responde "Pois não?" e espera o comando.

Use fones de ouvido com a escuta sempre ligada. Sem fones, o microfone pode captar a voz do próprio Jarvis e tratá-la como um comando.

## Segurança

- A chave da Anthropic e os tokens do Google ficam só no servidor. O navegador nunca os recebe.
- Os tokens do Google ficam em `data/google-tokens.json`, com permissão de leitura apenas para o seu usuário. Essa pasta e o `.env` estão no `.gitignore`.
- **Este projeto foi feito para rodar no seu computador.** Não há tela de login. Quem alcançar o endereço do servidor consegue conversar com o Jarvis, e isso inclui ler os seus e-mails e a sua agenda enquanto a conta Google estiver conectada. Se for hospedar em algum lugar público, proteja o acesso antes (por exemplo, com uma autenticação na frente do servidor).

## Desenvolvimento

```bash
npm run dev     # reinicia sozinho ao mudar o código do servidor
npm test        # testes unitários e de integração (sem chamadas reais à Anthropic ou ao Google)
```

Estrutura:

```
server/
  index.js    inicialização (lê config, conecta tudo e sobe o servidor)
  app.js      rotas HTTP: /api/chat, /api/status e o fluxo OAuth do Google
  agent.js    loop com o Claude: envia a mensagem, executa as ferramentas e devolve a resposta
  tools.js    definição e validação das ferramentas que o Claude pode usar
  google.js   OAuth, renovação de token e chamadas à API do Google (Agenda, Gmail, Drive)
  time.js     conversão de horários entre fusos (inclusive horário de verão)
  config.js   variáveis de ambiente
public/
  index.html, styles.css   interface
  app.js                   microfone, fala, estados da tela e envio das mensagens
  wake.js                  detecção da palavra "Jarvis" no começo da fala
test/                      testes com node:test
```
