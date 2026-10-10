import express from 'express';
import { fileURLToPath } from 'node:url';

const MAX_MESSAGE_CHARS = 4000;
const MAX_HISTORY = 20;

const publicDir = fileURLToPath(new URL('../public', import.meta.url));

// Mantém só mensagens válidas e começa sempre por uma fala do usuário,
// como a API da Anthropic espera.
export function sanitizeHistory(raw) {
  if (!Array.isArray(raw)) return [];
  const clean = raw
    .filter((item) => item && (item.role === 'user' || item.role === 'assistant') && typeof item.content === 'string')
    .map((item) => ({ role: item.role, content: item.content.slice(0, MAX_MESSAGE_CHARS) }))
    .slice(-MAX_HISTORY);
  const firstUser = clean.findIndex((item) => item.role === 'user');
  return firstUser === -1 ? [] : clean.slice(firstUser);
}

export function createApp({ agent, google, anthropicConfigured, timeZone }) {
  const app = express();
  app.disable('x-powered-by');
  // Cabe o histórico inteiro: até 20 mensagens de 4000 caracteres.
  app.use(express.json({ limit: '256kb' }));
  app.use(express.static(publicDir));

  app.get('/api/status', (req, res) => {
    res.json({
      anthropicConfigured,
      timeZone,
      google: {
        configured: google.isConfigured(),
        connected: google.isConnected(),
      },
    });
  });

  app.post('/api/chat', async (req, res) => {
    const message = typeof req.body?.message === 'string' ? req.body.message.trim() : '';
    if (!message) {
      res.status(400).json({ error: 'Mensagem vazia.' });
      return;
    }
    if (message.length > MAX_MESSAGE_CHARS) {
      res.status(400).json({ error: `Mensagem muito longa (máximo ${MAX_MESSAGE_CHARS} caracteres).` });
      return;
    }
    if (!anthropicConfigured) {
      res.status(503).json({ error: 'A ANTHROPIC_API_KEY não está configurada no servidor.' });
      return;
    }

    try {
      const result = await agent.respond({
        history: sanitizeHistory(req.body.history),
        message,
      });
      res.json(result);
    } catch (error) {
      console.error('Falha ao consultar o modelo:', error);
      res.status(500).json({ error: 'Não consegui falar com o modelo agora. Tente de novo.' });
    }
  });

  app.get('/auth/google', (req, res) => {
    if (!google.isConfigured()) {
      res.status(503).type('text').send('Configure GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET no .env. Veja o README.');
      return;
    }
    res.redirect(google.createAuthUrl());
  });

  app.get('/auth/google/callback', async (req, res) => {
    const { code, state, error } = req.query;
    if (error || typeof code !== 'string' || typeof state !== 'string' || !google.consumeState(state)) {
      res.redirect('/?google=error');
      return;
    }
    try {
      await google.exchangeCode(code);
      res.redirect('/?google=connected');
    } catch (exchangeError) {
      console.error('Falha ao conectar o Google:', exchangeError.message);
      res.redirect('/?google=error');
    }
  });

  app.post('/auth/google/disconnect', async (req, res) => {
    await google.disconnect();
    res.json({ connected: false });
  });

  return app;
}
