import { randomBytes } from 'node:crypto';
import { mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

export const GOOGLE_SCOPES = [
  'https://www.googleapis.com/auth/calendar.events',
  'https://www.googleapis.com/auth/gmail.readonly',
  'https://www.googleapis.com/auth/gmail.compose',
  'https://www.googleapis.com/auth/drive.readonly',
];

const AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth';
const TOKEN_URL = 'https://oauth2.googleapis.com/token';
const REVOKE_URL = 'https://oauth2.googleapis.com/revoke';
const CALENDAR_API = 'https://www.googleapis.com/calendar/v3';
const GMAIL_API = 'https://gmail.googleapis.com/gmail/v1/users/me';
const DRIVE_API = 'https://www.googleapis.com/drive/v3';

const STATE_TTL_MS = 10 * 60_000;
const REFRESH_MARGIN_MS = 60_000;

export class GoogleNotConnectedError extends Error {
  constructor(message = 'O Google não está conectado. Peça ao usuário para clicar em "Conectar Google".') {
    super(message);
    this.name = 'GoogleNotConnectedError';
  }
}

function withQuery(base, pairs) {
  return `${base}?${new URLSearchParams(pairs)}`;
}

function encodeHeaderValue(value) {
  const clean = String(value).replace(/[\r\n]+/g, ' ');
  if (/^[\x00-\x7F]*$/.test(clean)) return clean;
  return `=?UTF-8?B?${Buffer.from(clean, 'utf8').toString('base64')}?=`;
}

// Monta uma mensagem RFC 2822 em texto simples e a devolve em base64url,
// que é o formato que a API do Gmail espera em message.raw.
export function buildRawEmail({ to, subject, body }) {
  const headers = [
    `To: ${String(to).replace(/[\r\n]+/g, ' ')}`,
    `Subject: ${encodeHeaderValue(subject)}`,
    'MIME-Version: 1.0',
    'Content-Type: text/plain; charset="UTF-8"',
    'Content-Transfer-Encoding: base64',
  ];
  const encodedBody = Buffer.from(body, 'utf8').toString('base64').replace(/.{1,76}/g, '$&\r\n');
  const message = `${headers.join('\r\n')}\r\n\r\n${encodedBody}`;
  return Buffer.from(message, 'utf8').toString('base64url');
}

export function createGoogleClient({ clientId, clientSecret, redirectUri, dataDir, fetchImpl = fetch }) {
  const tokenFile = join(dataDir, 'google-tokens.json');
  const pendingStates = new Map();
  let tokens = null;

  async function init() {
    try {
      tokens = JSON.parse(await readFile(tokenFile, 'utf8'));
    } catch (error) {
      if (error.code !== 'ENOENT') console.warn('Não consegui ler os tokens do Google:', error.message);
      tokens = null;
    }
  }

  async function saveTokens(next) {
    tokens = next;
    await mkdir(dataDir, { recursive: true });
    await writeFile(tokenFile, JSON.stringify(next, null, 2), { mode: 0o600 });
  }

  async function postToken(params) {
    const res = await fetchImpl(TOKEN_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ client_id: clientId, client_secret: clientSecret, ...params }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const error = new Error(`O Google recusou a requisição de token: ${data.error_description || data.error || res.status}`);
      error.oauthCode = data.error;
      throw error;
    }
    return data;
  }

  async function disconnect() {
    const refreshToken = tokens?.refresh_token;
    tokens = null;
    await rm(tokenFile, { force: true });
    if (refreshToken) {
      await fetchImpl(`${REVOKE_URL}?token=${encodeURIComponent(refreshToken)}`, { method: 'POST' }).catch(() => {});
    }
  }

  async function accessToken() {
    if (!tokens?.refresh_token) throw new GoogleNotConnectedError();
    if (tokens.access_token && tokens.expires_at - REFRESH_MARGIN_MS > Date.now()) return tokens.access_token;
    try {
      const data = await postToken({ grant_type: 'refresh_token', refresh_token: tokens.refresh_token });
      await saveTokens({ ...tokens, access_token: data.access_token, expires_at: Date.now() + data.expires_in * 1000 });
      return tokens.access_token;
    } catch (error) {
      if (error.oauthCode === 'invalid_grant') {
        await disconnect();
        throw new GoogleNotConnectedError('A conexão com o Google expirou. Peça ao usuário para conectar de novo.');
      }
      throw error;
    }
  }

  async function api(url, { method = 'GET', body } = {}) {
    const token = await accessToken();
    const res = await fetchImpl(url, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(`A API do Google respondeu ${res.status}: ${data.error?.message || 'erro sem detalhes'}`);
    return data;
  }

  return {
    init,
    isConfigured: () => Boolean(clientId && clientSecret),
    isConnected: () => Boolean(tokens?.refresh_token),
    disconnect,

    createAuthUrl() {
      const state = randomBytes(24).toString('base64url');
      pendingStates.set(state, Date.now() + STATE_TTL_MS);
      const params = new URLSearchParams({
        client_id: clientId,
        redirect_uri: redirectUri,
        response_type: 'code',
        scope: GOOGLE_SCOPES.join(' '),
        access_type: 'offline',
        prompt: 'consent',
        include_granted_scopes: 'true',
        state,
      });
      return `${AUTH_URL}?${params}`;
    },

    consumeState(state) {
      const expiresAt = pendingStates.get(state);
      pendingStates.delete(state);
      return expiresAt !== undefined && expiresAt > Date.now();
    },

    async exchangeCode(code) {
      const data = await postToken({ grant_type: 'authorization_code', code, redirect_uri: redirectUri });
      const refreshToken = data.refresh_token || tokens?.refresh_token;
      if (!refreshToken) {
        throw new Error('O Google não devolveu refresh token. Revogue o acesso do Jarvis em myaccount.google.com/permissions e conecte de novo.');
      }
      await saveTokens({
        refresh_token: refreshToken,
        access_token: data.access_token,
        expires_at: Date.now() + data.expires_in * 1000,
        scope: data.scope,
      });
    },

    async listCalendarEvents({ timeMin, timeMax, maxResults = 50 }) {
      const data = await api(withQuery(`${CALENDAR_API}/calendars/primary/events`, [
        ['timeMin', timeMin],
        ['timeMax', timeMax],
        ['singleEvents', 'true'],
        ['orderBy', 'startTime'],
        ['maxResults', String(maxResults)],
      ]));
      return (data.items || []).map((event) => ({
        id: event.id,
        title: event.summary || '(sem título)',
        start: event.start?.dateTime || event.start?.date,
        end: event.end?.dateTime || event.end?.date,
        location: event.location || '',
      }));
    },

    async createCalendarEvent({ title, start, end, timeZone, description, location }) {
      const event = await api(`${CALENDAR_API}/calendars/primary/events`, {
        method: 'POST',
        body: {
          summary: title,
          description,
          location,
          start: { dateTime: start, timeZone },
          end: { dateTime: end, timeZone },
        },
      });
      return {
        id: event.id,
        title: event.summary,
        start: event.start?.dateTime,
        end: event.end?.dateTime,
        link: event.htmlLink,
      };
    },

    async searchGmail({ query, maxResults = 5 }) {
      const list = await api(withQuery(`${GMAIL_API}/messages`, [
        ['q', query],
        ['maxResults', String(maxResults)],
      ]));
      const ids = (list.messages || []).map((message) => message.id);
      return Promise.all(ids.map(async (id) => {
        const message = await api(withQuery(`${GMAIL_API}/messages/${id}`, [
          ['format', 'metadata'],
          ['metadataHeaders', 'From'],
          ['metadataHeaders', 'Subject'],
          ['metadataHeaders', 'Date'],
        ]));
        const header = (name) => message.payload?.headers?.find((h) => h.name.toLowerCase() === name.toLowerCase())?.value || '';
        return {
          id,
          from: header('From'),
          subject: header('Subject'),
          date: header('Date'),
          snippet: message.snippet || '',
        };
      }));
    },

    async createGmailDraft({ to, subject, body }) {
      const draft = await api(`${GMAIL_API}/drafts`, {
        method: 'POST',
        body: { message: { raw: buildRawEmail({ to, subject, body }) } },
      });
      return { draftId: draft.id, to, subject };
    },

    async searchDrive({ query, maxResults = 10 }) {
      const escaped = query.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
      const data = await api(withQuery(`${DRIVE_API}/files`, [
        ['q', `name contains '${escaped}' and trashed = false`],
        ['pageSize', String(maxResults)],
        ['orderBy', 'modifiedTime desc'],
        ['fields', 'files(id,name,mimeType,modifiedTime,webViewLink)'],
      ]));
      return data.files || [];
    },
  };
}
