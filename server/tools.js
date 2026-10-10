import { GoogleNotConnectedError } from './google.js';
import {
  addDays,
  addMinutesToLocal,
  isDate,
  isLocalDateTime,
  normalizeLocalDateTime,
  zonedTimeToDate,
} from './time.js';

const MAX_RANGE_DAYS = 62;
const EMAIL_RE = /^[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+$/;

const definitions = [
  {
    name: 'calendar_list_events',
    description: 'Lista os eventos da agenda principal do Google Agenda do usuário entre duas datas (inclusive). Use para responder o que está marcado.',
    input_schema: {
      type: 'object',
      properties: {
        start_date: { type: 'string', description: 'Primeiro dia, no formato AAAA-MM-DD.' },
        end_date: { type: 'string', description: 'Último dia incluído, no formato AAAA-MM-DD.' },
      },
      required: ['start_date', 'end_date'],
    },
  },
  {
    name: 'calendar_create_event',
    description: 'Cria um evento na agenda principal do Google Agenda. Use somente quando o usuário pedir para anotar, marcar ou agendar algo.',
    input_schema: {
      type: 'object',
      properties: {
        title: { type: 'string', description: 'Título do evento.' },
        start: { type: 'string', description: 'Início no horário local do usuário, formato AAAA-MM-DDTHH:MM (ex.: 2026-10-11T13:00).' },
        end: { type: 'string', description: 'Fim no horário local, formato AAAA-MM-DDTHH:MM. Se omitido, o evento dura 60 minutos.' },
        description: { type: 'string', description: 'Detalhes opcionais.' },
        location: { type: 'string', description: 'Local opcional.' },
      },
      required: ['title', 'start'],
    },
  },
  {
    name: 'gmail_search',
    description: 'Pesquisa e-mails no Gmail usando a sintaxe de busca do Gmail (ex.: from:fulano, is:unread, newer_than:2d, subject:fatura).',
    input_schema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Termos de busca no formato do Gmail.' },
        max_results: { type: 'integer', minimum: 1, maximum: 10, description: 'Quantidade máxima de resultados (padrão 5).' },
      },
      required: ['query'],
    },
  },
  {
    name: 'gmail_create_draft',
    description: 'Cria um RASCUNHO de e-mail no Gmail. Nunca envia o e-mail: o usuário revisa e envia por conta própria.',
    input_schema: {
      type: 'object',
      properties: {
        to: { type: 'string', description: 'Endereço de e-mail do destinatário.' },
        subject: { type: 'string', description: 'Assunto.' },
        body: { type: 'string', description: 'Texto do e-mail, em texto simples.' },
      },
      required: ['to', 'subject', 'body'],
    },
  },
  {
    name: 'drive_search',
    description: 'Procura arquivos pelo nome no Google Drive do usuário.',
    input_schema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Parte do nome do arquivo.' },
        max_results: { type: 'integer', minimum: 1, maximum: 20, description: 'Quantidade máxima de resultados (padrão 10).' },
      },
      required: ['query'],
    },
  },
];

function clampInt(value, fallback, min, max) {
  const number = Math.trunc(Number(value));
  if (!Number.isFinite(number)) return fallback;
  return Math.min(max, Math.max(min, number));
}

function requireText(value, name) {
  if (typeof value !== 'string' || !value.trim()) throw new Error(`${name} é obrigatório.`);
  return value.trim();
}

function requireDate(value, name) {
  if (!isDate(value)) throw new Error(`${name} deve estar no formato AAAA-MM-DD.`);
  return value;
}

export function createTools({ google, timeZone }) {
  const handlers = {
    async calendar_list_events({ start_date, end_date }) {
      requireDate(start_date, 'start_date');
      requireDate(end_date, 'end_date');
      if (end_date < start_date) throw new Error('end_date é anterior a start_date.');
      const days = (Date.parse(`${end_date}T00:00:00Z`) - Date.parse(`${start_date}T00:00:00Z`)) / 86_400_000 + 1;
      if (days > MAX_RANGE_DAYS) throw new Error(`O intervalo máximo é de ${MAX_RANGE_DAYS} dias.`);

      const timeMin = zonedTimeToDate(`${start_date}T00:00:00`, timeZone).toISOString();
      const timeMax = zonedTimeToDate(`${addDays(end_date, 1)}T00:00:00`, timeZone).toISOString();
      const events = await google.listCalendarEvents({ timeMin, timeMax });
      return { timeZone, count: events.length, events };
    },

    async calendar_create_event({ title, start, end, description, location }) {
      const cleanTitle = requireText(title, 'title');
      if (!isLocalDateTime(start)) throw new Error('start deve estar no formato AAAA-MM-DDTHH:MM.');
      const startLocal = normalizeLocalDateTime(start);
      const endLocal = end ? normalizeLocalDateTime(end) : addMinutesToLocal(startLocal, 60);
      if (!isLocalDateTime(endLocal)) throw new Error('end deve estar no formato AAAA-MM-DDTHH:MM.');
      if (Date.parse(`${endLocal}Z`) <= Date.parse(`${startLocal}Z`)) throw new Error('end precisa ser depois de start.');

      const event = await google.createCalendarEvent({
        title: cleanTitle,
        start: startLocal,
        end: endLocal,
        timeZone,
        description: typeof description === 'string' ? description : undefined,
        location: typeof location === 'string' ? location : undefined,
      });
      return { created: true, ...event };
    },

    async gmail_search({ query, max_results }) {
      const messages = await google.searchGmail({
        query: requireText(query, 'query'),
        maxResults: clampInt(max_results, 5, 1, 10),
      });
      return { count: messages.length, messages };
    },

    async gmail_create_draft({ to, subject, body }) {
      const recipient = requireText(to, 'to');
      if (!EMAIL_RE.test(recipient)) throw new Error('to não parece um endereço de e-mail válido.');
      const draft = await google.createGmailDraft({
        to: recipient,
        subject: requireText(subject, 'subject'),
        body: requireText(body, 'body'),
      });
      return { ...draft, note: 'Rascunho salvo no Gmail. O e-mail não foi enviado.' };
    },

    async drive_search({ query, max_results }) {
      const files = await google.searchDrive({
        query: requireText(query, 'query'),
        maxResults: clampInt(max_results, 10, 1, 20),
      });
      return { count: files.length, files };
    },
  };

  return {
    definitions,

    async execute(name, input) {
      const handler = handlers[name];
      if (!handler) throw new Error(`Ferramenta desconhecida: ${name}`);
      if (!google.isConfigured()) {
        throw new GoogleNotConnectedError('As credenciais do Google não estão configuradas no servidor (GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET).');
      }
      return handler(input && typeof input === 'object' ? input : {});
    },
  };
}
