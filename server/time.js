// Conversão entre horários "de parede" (sem fuso) e instantes reais.
// Os horários que o modelo manda são sempre locais ao fuso do usuário.

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const DATE_TIME_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/;

// Date.parse aceita 2026-02-30 e devolve 2 de março, então conferimos o dia de volta.
export function isDate(value) {
  if (typeof value !== 'string' || !DATE_RE.test(value)) return false;
  const parsed = Date.parse(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed) && new Date(parsed).toISOString().slice(0, 10) === value;
}

export function isLocalDateTime(value) {
  if (typeof value !== 'string' || !DATE_TIME_RE.test(value)) return false;
  const normalized = normalizeLocalDateTime(value);
  const parsed = Date.parse(`${normalized}Z`);
  return !Number.isNaN(parsed) && new Date(parsed).toISOString().slice(0, 10) === normalized.slice(0, 10);
}

// Normaliza "AAAA-MM-DDTHH:MM" para "AAAA-MM-DDTHH:MM:SS".
export function normalizeLocalDateTime(value) {
  return value.length === 16 ? `${value}:00` : value;
}

// Diferença (em ms) entre o relógio do fuso e UTC naquele instante.
function offsetMs(utcMs, timeZone) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone,
    hourCycle: 'h23',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).formatToParts(new Date(utcMs));
  const map = Object.fromEntries(parts.map((p) => [p.type, p.value]));
  const asUtc = Date.UTC(+map.year, +map.month - 1, +map.day, +map.hour, +map.minute, +map.second);
  return asUtc - Math.floor(utcMs / 1000) * 1000;
}

// Converte "AAAA-MM-DDTHH:MM:SS" no fuso informado para um Date real.
export function zonedTimeToDate(naive, timeZone) {
  const asUtc = Date.parse(`${normalizeLocalDateTime(naive)}Z`);
  const first = asUtc - offsetMs(asUtc, timeZone);
  return new Date(asUtc - offsetMs(first, timeZone));
}

// Soma minutos a um horário de parede, sem depender do fuso do servidor.
export function addMinutesToLocal(naive, minutes) {
  const shifted = Date.parse(`${normalizeLocalDateTime(naive)}Z`) + minutes * 60_000;
  return new Date(shifted).toISOString().slice(0, 19);
}

// Soma dias a uma data AAAA-MM-DD.
export function addDays(date, days) {
  return new Date(Date.parse(`${date}T00:00:00Z`) + days * 86_400_000).toISOString().slice(0, 10);
}

// Descreve "agora" para o prompt do sistema, no fuso do usuário.
export function describeNow(date, timeZone) {
  const isoDate = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date);
  const human = new Intl.DateTimeFormat('pt-BR', {
    timeZone,
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
  return `${human} (data de hoje: ${isoDate})`;
}
