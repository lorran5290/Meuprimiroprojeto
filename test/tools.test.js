import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createTools } from '../server/tools.js';

const TZ = 'America/Sao_Paulo';

// Google falso: registra cada chamada em calls como { name, value }.
function fakeGoogle(overrides = {}) {
  const calls = [];
  const record = (name, value) => calls.push({ name, value });
  return {
    calls,
    isConfigured: () => true,
    isConnected: () => true,
    async listCalendarEvents(args) {
      record('listCalendarEvents', args);
      return [{ id: '1', title: 'Dentista' }];
    },
    async createCalendarEvent(args) {
      record('createCalendarEvent', args);
      return { id: 'evt', title: args.title, start: args.start, end: args.end };
    },
    async searchGmail(args) {
      record('searchGmail', args);
      return [];
    },
    async createGmailDraft(args) {
      record('createGmailDraft', args);
      return { draftId: 'd1', to: args.to, subject: args.subject };
    },
    async searchDrive(args) {
      record('searchDrive', args);
      return [];
    },
    ...overrides,
  };
}

function lastCall(google, name) {
  return google.calls.filter((call) => call.name === name).at(-1)?.value;
}

test('o conjunto de ferramentas não tem nenhuma forma de enviar e-mail', () => {
  const tools = createTools({ google: fakeGoogle(), timeZone: TZ });
  const names = tools.definitions.map((tool) => tool.name);
  assert.deepEqual(names.sort(), ['calendar_create_event', 'calendar_list_events', 'drive_search', 'gmail_create_draft', 'gmail_search']);
  assert.ok(!names.some((name) => /send/.test(name)));
});

test('criar evento sem horário de fim dura 60 minutos e usa o fuso do usuário', async () => {
  const google = fakeGoogle();
  const tools = createTools({ google, timeZone: TZ });

  const result = await tools.execute('calendar_create_event', { title: 'Serviço', start: '2026-10-11T13:00' });

  assert.deepEqual(lastCall(google, 'createCalendarEvent'), {
    title: 'Serviço',
    start: '2026-10-11T13:00:00',
    end: '2026-10-11T14:00:00',
    timeZone: TZ,
    description: undefined,
    location: undefined,
  });
  assert.equal(result.created, true);
});

test('criar evento rejeita horário em formato livre e fim antes do início', async () => {
  const tools = createTools({ google: fakeGoogle(), timeZone: TZ });
  await assert.rejects(tools.execute('calendar_create_event', { title: 'X', start: 'amanhã 13h' }), /AAAA-MM-DDTHH:MM/);
  await assert.rejects(
    tools.execute('calendar_create_event', { title: 'X', start: '2026-10-11T13:00', end: '2026-10-11T12:00' }),
    /depois de start/,
  );
  await assert.rejects(tools.execute('calendar_create_event', { start: '2026-10-11T13:00' }), /title é obrigatório/);
});

test('listar agenda converte o dia inteiro do fuso do usuário para UTC', async () => {
  const google = fakeGoogle();
  const tools = createTools({ google, timeZone: TZ });

  await tools.execute('calendar_list_events', { start_date: '2026-10-11', end_date: '2026-10-11' });

  assert.deepEqual(lastCall(google, 'listCalendarEvents'), {
    timeMin: '2026-10-11T03:00:00.000Z',
    timeMax: '2026-10-12T03:00:00.000Z',
  });
});

test('listar agenda rejeita datas inexistentes, intervalo invertido e janelas longas demais', async () => {
  const tools = createTools({ google: fakeGoogle(), timeZone: TZ });
  await assert.rejects(tools.execute('calendar_list_events', { start_date: '2026-02-30', end_date: '2026-03-01' }), /AAAA-MM-DD/);
  await assert.rejects(tools.execute('calendar_list_events', { start_date: '2026-10-12', end_date: '2026-10-11' }), /anterior/);
  await assert.rejects(tools.execute('calendar_list_events', { start_date: '2026-01-01', end_date: '2026-12-31' }), /62 dias/);
});

test('gmail_create_draft valida o destinatário e nunca envia', async () => {
  const google = fakeGoogle();
  const tools = createTools({ google, timeZone: TZ });

  await assert.rejects(
    tools.execute('gmail_create_draft', { to: 'não é email', subject: 'Oi', body: 'Tudo bem?' }),
    /endereço de e-mail válido/,
  );

  const result = await tools.execute('gmail_create_draft', { to: 'ana@example.com', subject: 'Oi', body: 'Tudo bem?' });
  assert.equal(result.draftId, 'd1');
  assert.match(result.note, /não foi enviado/);
  assert.equal(google.calls.length, 1);
});

test('limita a quantidade de resultados de busca', async () => {
  const google = fakeGoogle();
  const tools = createTools({ google, timeZone: TZ });

  await tools.execute('gmail_search', { query: 'is:unread', max_results: 500 });
  assert.equal(lastCall(google, 'searchGmail').maxResults, 10);

  await tools.execute('drive_search', { query: 'contrato' });
  assert.equal(lastCall(google, 'searchDrive').maxResults, 10);
});

test('execute recusa ferramentas desconhecidas e falta de credenciais', async () => {
  const tools = createTools({ google: fakeGoogle(), timeZone: TZ });
  await assert.rejects(tools.execute('gmail_send', {}), /Ferramenta desconhecida/);

  const unconfigured = createTools({ google: fakeGoogle({ isConfigured: () => false }), timeZone: TZ });
  await assert.rejects(unconfigured.execute('gmail_search', { query: 'x' }), /GOOGLE_CLIENT_ID/);
});
