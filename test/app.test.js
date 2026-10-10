import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { createApp, sanitizeHistory } from '../server/app.js';

function fakeAgent(behavior) {
  const calls = [];
  return {
    calls,
    async respond(args) {
      calls.push(args);
      return behavior(args);
    },
  };
}

function fakeGoogle(overrides = {}) {
  return {
    isConfigured: () => true,
    isConnected: () => false,
    createAuthUrl: () => 'https://accounts.google.com/o/oauth2/v2/auth?state=abc',
    consumeState: (state) => state === 'abc',
    exchangeCode: async () => {},
    disconnect: async () => {},
    ...overrides,
  };
}

function startServer(options) {
  const app = createApp(options);
  return new Promise((resolve) => {
    const server = app.listen(0, '127.0.0.1', () => resolve(server));
  });
}

const json = (body) => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

test('sanitizeHistory descarta lixo, corta o tamanho e começa por uma fala do usuário', () => {
  const clean = sanitizeHistory([
    { role: 'assistant', content: 'sobra de uma conversa anterior' },
    { role: 'user', content: 'oi' },
    { role: 'system', content: 'tentativa de injetar papel' },
    { role: 'assistant', content: 'olá' },
    { role: 'user', content: 42 },
  ]);
  assert.deepEqual(clean, [
    { role: 'user', content: 'oi' },
    { role: 'assistant', content: 'olá' },
  ]);

  const long = Array.from({ length: 30 }, (_, i) => ({ role: i % 2 ? 'assistant' : 'user', content: `m${i}` }));
  assert.equal(sanitizeHistory(long).length, 20);
  assert.deepEqual(sanitizeHistory('não é lista'), []);
});

test('rotas da API: status, validação e resposta do agente', async (t) => {
  const agent = fakeAgent(({ message }) => ({ reply: `eco: ${message}`, toolsUsed: ['gmail_search'] }));
  const server = await startServer({ agent, google: fakeGoogle(), anthropicConfigured: true, timeZone: 'America/Sao_Paulo' });
  t.after(() => server.close());
  const base = `http://127.0.0.1:${server.address().port}`;

  const status = await (await fetch(`${base}/api/status`)).json();
  assert.deepEqual(status, {
    anthropicConfigured: true,
    timeZone: 'America/Sao_Paulo',
    google: { configured: true, connected: false },
  });

  assert.equal((await fetch(`${base}/api/chat`, json({ message: '   ' }))).status, 400);
  assert.equal((await fetch(`${base}/api/chat`, json({ message: 'x'.repeat(4001) }))).status, 400);

  const ok = await fetch(`${base}/api/chat`, json({
    message: '  Jarvis, anote isso  ',
    history: [{ role: 'user', content: 'antes' }, { role: 'assistant', content: 'certo' }],
  }));
  assert.equal(ok.status, 200);
  assert.deepEqual(await ok.json(), { reply: 'eco: Jarvis, anote isso', toolsUsed: ['gmail_search'] });
  assert.equal(agent.calls[0].message, 'Jarvis, anote isso');
  assert.equal(agent.calls[0].history.length, 2);
});

test('sem ANTHROPIC_API_KEY o chat responde 503 com aviso claro', async (t) => {
  const server = await startServer({ agent: fakeAgent(() => ({})), google: fakeGoogle(), anthropicConfigured: false, timeZone: 'America/Sao_Paulo' });
  t.after(() => server.close());
  const res = await fetch(`http://127.0.0.1:${server.address().port}/api/chat`, json({ message: 'oi' }));
  assert.equal(res.status, 503);
  assert.match((await res.json()).error, /ANTHROPIC_API_KEY/);
});

test('falha do modelo vira 500 sem vazar detalhes internos', async (t) => {
  const agent = fakeAgent(() => {
    throw new Error('chave secreta sk-123 vazou aqui');
  });
  const server = await startServer({ agent, google: fakeGoogle(), anthropicConfigured: true, timeZone: 'America/Sao_Paulo' });
  t.after(() => server.close());
  const res = await fetch(`http://127.0.0.1:${server.address().port}/api/chat`, json({ message: 'oi' }));
  assert.equal(res.status, 500);
  assert.doesNotMatch(JSON.stringify(await res.json()), /sk-123/);
});

test('fluxo do Google: redireciona para o consentimento e valida o state no retorno', async (t) => {
  let exchanged = null;
  const google = fakeGoogle({
    isConfigured: () => true,
    exchangeCode: async (code) => {
      exchanged = code;
    },
  });
  const server = await startServer({ agent: fakeAgent(() => ({})), google, anthropicConfigured: true, timeZone: 'America/Sao_Paulo' });
  t.after(() => server.close());
  const base = `http://127.0.0.1:${server.address().port}`;
  const noFollow = { redirect: 'manual' };

  const start = await fetch(`${base}/auth/google`, noFollow);
  assert.equal(start.status, 302);
  assert.match(start.headers.get('location'), /^https:\/\/accounts\.google\.com/);

  const badState = await fetch(`${base}/auth/google/callback?code=x&state=errado`, noFollow);
  assert.equal(badState.headers.get('location'), '/?google=error');
  assert.equal(exchanged, null);

  const good = await fetch(`${base}/auth/google/callback?code=codigo-1&state=abc`, noFollow);
  assert.equal(good.headers.get('location'), '/?google=connected');
  assert.equal(exchanged, 'codigo-1');

  const denied = await fetch(`${base}/auth/google/callback?error=access_denied&state=abc`, noFollow);
  assert.equal(denied.headers.get('location'), '/?google=error');
});

test('/auth/google responde 503 quando o cliente OAuth não foi configurado', async (t) => {
  const google = fakeGoogle({ isConfigured: () => false });
  const server = await startServer({ agent: fakeAgent(() => ({})), google, anthropicConfigured: true, timeZone: 'America/Sao_Paulo' });
  t.after(() => server.close());
  const res = await fetch(`http://127.0.0.1:${server.address().port}/auth/google`, { redirect: 'manual' });
  assert.equal(res.status, 503);
  assert.match(await res.text(), /GOOGLE_CLIENT_ID/);
});

test('serve a página do Jarvis na raiz', async (t) => {
  const server = await startServer({ agent: fakeAgent(() => ({})), google: fakeGoogle(), anthropicConfigured: true, timeZone: 'America/Sao_Paulo' });
  t.after(() => server.close());
  const res = await fetch(`http://127.0.0.1:${server.address().port}/`);
  assert.equal(res.status, 200);
  const html = await res.text();
  assert.match(html, /<title>Jarvis<\/title>/);
  assert.match(html, /src="\/app\.js"/);
});
