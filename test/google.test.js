import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { buildRawEmail, createGoogleClient, GoogleNotConnectedError } from '../server/google.js';

const CALENDAR_URL = 'https://www.googleapis.com/calendar/v3/calendars/primary/events';
const TOKEN_URL = 'https://oauth2.googleapis.com/token';
const REVOKE_URL = 'https://oauth2.googleapis.com/revoke';

// fetch falso: cada rota responde { status, body } e tudo fica gravado em calls.
function fakeFetch(routes) {
  const calls = [];
  const fetchImpl = async (url, init = {}) => {
    calls.push({ url: String(url), init });
    const route = routes.find(([prefix]) => String(url).startsWith(prefix));
    if (!route) throw new Error(`rota inesperada: ${url}`);
    const { status = 200, body = {} } = route[1](String(url), init);
    return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
  };
  fetchImpl.calls = calls;
  return fetchImpl;
}

async function newClient(routes, { tokens } = {}) {
  const dataDir = await mkdtemp(join(tmpdir(), 'jarvis-google-'));
  if (tokens) await writeFile(join(dataDir, 'google-tokens.json'), JSON.stringify(tokens));
  const fetchImpl = fakeFetch(routes);
  const google = createGoogleClient({
    clientId: 'client-id',
    clientSecret: 'client-secret',
    redirectUri: 'http://localhost:3000/auth/google/callback',
    dataDir,
    fetchImpl,
  });
  await google.init();
  return { google, fetchImpl, dataDir };
}

test('buildRawEmail gera MIME decodificável e codifica o assunto em UTF-8', () => {
  const raw = buildRawEmail({ to: 'ana@example.com', subject: 'Reunião às 13h', body: 'Olá, Ana.\nAté já!' });
  const text = Buffer.from(raw, 'base64url').toString('utf8');
  const split = text.indexOf('\r\n\r\n');
  const head = text.slice(0, split);
  const body = text.slice(split + 4);

  assert.match(head, /^To: ana@example\.com$/m);
  const encodedSubject = head.match(/^Subject: =\?UTF-8\?B\?(.+)\?=$/m)[1];
  assert.equal(Buffer.from(encodedSubject, 'base64').toString('utf8'), 'Reunião às 13h');
  assert.equal(Buffer.from(body.replace(/\r\n/g, ''), 'base64').toString('utf8'), 'Olá, Ana.\nAté já!');
});

test('buildRawEmail não deixa o destinatário injetar cabeçalhos extras', () => {
  const raw = buildRawEmail({ to: 'ana@example.com\r\nBcc: spy@example.com', subject: 'Oi', body: 'Teste' });
  const head = Buffer.from(raw, 'base64url').toString('utf8').split('\r\n\r\n')[0];
  assert.doesNotMatch(head, /^Bcc:/m);
});

test('monta a URL de autorização com escopos, acesso offline e um state de uso único', async () => {
  const { google } = await newClient([]);
  const url = new URL(google.createAuthUrl());
  assert.equal(url.origin + url.pathname, 'https://accounts.google.com/o/oauth2/v2/auth');
  assert.equal(url.searchParams.get('client_id'), 'client-id');
  assert.equal(url.searchParams.get('access_type'), 'offline');
  assert.match(url.searchParams.get('scope'), /gmail\.compose/);
  assert.doesNotMatch(url.searchParams.get('scope'), /gmail\.send/);

  const state = url.searchParams.get('state');
  assert.equal(google.consumeState(state), true);
  assert.equal(google.consumeState(state), false, 'o mesmo state não pode ser usado duas vezes');
  assert.equal(google.consumeState('estado-inventado'), false);
});

test('troca o código por tokens, salva em arquivo privado e usa o access token', async () => {
  const { google, fetchImpl, dataDir } = await newClient([
    [TOKEN_URL, () => ({ body: { access_token: 'AT-1', refresh_token: 'RT-1', expires_in: 3600, scope: 'x' } })],
    [CALENDAR_URL, () => ({ body: { items: [{ id: 'e1', summary: 'Dentista', start: { dateTime: '2026-10-11T09:00:00-03:00' }, end: { dateTime: '2026-10-11T10:00:00-03:00' } }] } })],
  ]);

  assert.equal(google.isConnected(), false);
  await google.exchangeCode('codigo-123');
  assert.equal(google.isConnected(), true);

  const exchange = new URLSearchParams(fetchImpl.calls[0].init.body);
  assert.equal(exchange.get('grant_type'), 'authorization_code');
  assert.equal(exchange.get('code'), 'codigo-123');

  const events = await google.listCalendarEvents({ timeMin: '2026-10-11T03:00:00.000Z', timeMax: '2026-10-12T03:00:00.000Z' });
  assert.deepEqual(events[0], {
    id: 'e1',
    title: 'Dentista',
    start: '2026-10-11T09:00:00-03:00',
    end: '2026-10-11T10:00:00-03:00',
    location: '',
  });
  assert.equal(fetchImpl.calls.at(-1).init.headers.Authorization, 'Bearer AT-1');

  const saved = JSON.parse(await readFile(join(dataDir, 'google-tokens.json'), 'utf8'));
  assert.equal(saved.refresh_token, 'RT-1');
  if (process.platform !== 'win32') {
    assert.equal((await stat(join(dataDir, 'google-tokens.json'))).mode & 0o777, 0o600);
  }
});

test('renova o access token expirado com o refresh token antes de chamar a API', async () => {
  const { google, fetchImpl } = await newClient([
    [TOKEN_URL, () => ({ body: { access_token: 'AT-NOVO', expires_in: 3600 } })],
    [CALENDAR_URL, () => ({ body: { items: [] } })],
  ], { tokens: { refresh_token: 'RT-1', access_token: 'AT-VELHO', expires_at: Date.now() - 1000 } });

  await google.listCalendarEvents({ timeMin: 'a', timeMax: 'b' });

  const refresh = new URLSearchParams(fetchImpl.calls[0].init.body);
  assert.equal(refresh.get('grant_type'), 'refresh_token');
  assert.equal(refresh.get('refresh_token'), 'RT-1');
  assert.equal(fetchImpl.calls.at(-1).init.headers.Authorization, 'Bearer AT-NOVO');
});

test('quando o refresh token é revogado, desconecta e pede nova conexão', async () => {
  const { google, dataDir } = await newClient([
    [TOKEN_URL, () => ({ status: 400, body: { error: 'invalid_grant', error_description: 'Token has been expired or revoked.' } })],
  ], { tokens: { refresh_token: 'RT-1', access_token: 'AT-VELHO', expires_at: Date.now() - 1000 } });

  await assert.rejects(
    google.listCalendarEvents({ timeMin: 'a', timeMax: 'b' }),
    (error) => error instanceof GoogleNotConnectedError && /conectar de novo/.test(error.message),
  );
  assert.equal(google.isConnected(), false);
  await assert.rejects(stat(join(dataDir, 'google-tokens.json')), { code: 'ENOENT' });
});

test('sem conexão, as chamadas falham com GoogleNotConnectedError', async () => {
  const { google } = await newClient([]);
  await assert.rejects(google.searchGmail({ query: 'is:unread' }), GoogleNotConnectedError);
});

test('createCalendarEvent envia horário local com o fuso informado', async () => {
  const { google, fetchImpl } = await newClient([
    [TOKEN_URL, () => ({ body: { access_token: 'AT', expires_in: 3600, refresh_token: 'RT' } })],
    [CALENDAR_URL, () => ({ body: { id: 'evt-1', summary: 'Serviço', start: { dateTime: '2026-10-11T13:00:00' }, end: { dateTime: '2026-10-11T14:00:00' }, htmlLink: 'https://calendar.google.com/x' } })],
  ]);
  await google.exchangeCode('c');

  const created = await google.createCalendarEvent({
    title: 'Serviço',
    start: '2026-10-11T13:00:00',
    end: '2026-10-11T14:00:00',
    timeZone: 'America/Sao_Paulo',
  });

  const sent = JSON.parse(fetchImpl.calls.at(-1).init.body);
  assert.equal(sent.summary, 'Serviço');
  assert.deepEqual(sent.start, { dateTime: '2026-10-11T13:00:00', timeZone: 'America/Sao_Paulo' });
  assert.equal(created.id, 'evt-1');
});

test('searchDrive escapa aspas simples na consulta', async () => {
  const { google, fetchImpl } = await newClient([
    [TOKEN_URL, () => ({ body: { access_token: 'AT', expires_in: 3600, refresh_token: 'RT' } })],
    ['https://www.googleapis.com/drive/v3/files', () => ({ body: { files: [] } })],
  ]);
  await google.exchangeCode('c');
  await google.searchDrive({ query: "O'Neil" });

  const q = new URL(fetchImpl.calls.at(-1).url).searchParams.get('q');
  assert.equal(q, "name contains 'O\\'Neil' and trashed = false");
});

test('disconnect revoga o token no Google e apaga o arquivo local', async () => {
  const { google, fetchImpl } = await newClient([
    [TOKEN_URL, () => ({ body: { access_token: 'AT', expires_in: 3600, refresh_token: 'RT' } })],
    [REVOKE_URL, () => ({ body: {} })],
  ]);
  await google.exchangeCode('c');
  await google.disconnect();

  assert.equal(google.isConnected(), false);
  assert.ok(fetchImpl.calls.some((call) => call.url.startsWith(REVOKE_URL)));
});
