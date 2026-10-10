import Anthropic from '@anthropic-ai/sdk';
import { createAgent } from './agent.js';
import { createApp } from './app.js';
import { config } from './config.js';
import { createGoogleClient } from './google.js';
import { createTestAgent } from './teste.js';
import { createTools } from './tools.js';

const google = createGoogleClient({
  clientId: config.google.clientId,
  clientSecret: config.google.clientSecret,
  redirectUri: config.google.redirectUri,
  dataDir: config.dataDir,
});
await google.init();

const anthropicConfigured = Boolean(config.anthropicApiKey);
const testMode = !anthropicConfigured && config.testMode;
const client = anthropicConfigured ? new Anthropic({ apiKey: config.anthropicApiKey }) : null;
const tools = createTools({ google, timeZone: config.timeZone });
const agent = anthropicConfigured
  ? createAgent({ client, model: config.model, tools, timeZone: config.timeZone })
  : createTestAgent({ timeZone: config.timeZone });

const app = createApp({ agent, google, anthropicConfigured, testMode, timeZone: config.timeZone });

app.listen(config.port, () => {
  console.log(`Jarvis no ar em http://localhost:${config.port}`);
  if (testMode) console.log('Modo de teste ativo: respostas prontas, sem chamar a API.');
  if (!anthropicConfigured && !testMode) console.warn('Aviso: ANTHROPIC_API_KEY não definida. O chat vai ficar indisponível.');
  if (!google.isConfigured()) console.warn('Aviso: credenciais do Google ausentes. Agenda, Gmail e Drive ficarão desligados.');
});
