import { test } from 'node:test';
import assert from 'node:assert/strict';
import { addDays, addMinutesToLocal, describeNow, isDate, isLocalDateTime, zonedTimeToDate } from '../server/time.js';

test('converte horário de São Paulo em UTC (UTC-3, sem horário de verão)', () => {
  assert.equal(zonedTimeToDate('2026-10-11T13:00:00', 'America/Sao_Paulo').toISOString(), '2026-10-11T16:00:00.000Z');
});

test('aceita horário sem segundos', () => {
  assert.equal(zonedTimeToDate('2026-10-11T13:00', 'America/Sao_Paulo').toISOString(), '2026-10-11T16:00:00.000Z');
});

test('respeita horário de verão de outro fuso (Lisboa muda de UTC+1 para UTC+0 em 25/10/2026)', () => {
  assert.equal(zonedTimeToDate('2026-10-11T13:00:00', 'Europe/Lisbon').toISOString(), '2026-10-11T12:00:00.000Z');
  assert.equal(zonedTimeToDate('2026-10-26T13:00:00', 'Europe/Lisbon').toISOString(), '2026-10-26T13:00:00.000Z');
});

test('soma minutos e dias sobre datas de parede sem depender do fuso do servidor', () => {
  assert.equal(addMinutesToLocal('2026-10-11T23:30:00', 60), '2026-10-12T00:30:00');
  assert.equal(addDays('2026-10-31', 1), '2026-11-01');
  assert.equal(addDays('2026-12-31', 1), '2027-01-01');
});

test('valida datas e horários e rejeita dias que não existem', () => {
  assert.equal(isDate('2026-02-28'), true);
  assert.equal(isDate('2026-02-30'), false);
  assert.equal(isDate('2026/02/28'), false);
  assert.equal(isLocalDateTime('2026-10-11T13:00'), true);
  assert.equal(isLocalDateTime('2026-10-11T13:00:00'), true);
  assert.equal(isLocalDateTime('2026-10-11T25:00'), false);
  assert.equal(isLocalDateTime('amanhã 13h'), false);
});

test('descreve o instante atual no fuso do usuário, incluindo a data de hoje', () => {
  // 20:00 UTC de 10/10/2026 são 17:00 em São Paulo, ainda no sábado.
  const text = describeNow(new Date('2026-10-10T20:00:00Z'), 'America/Sao_Paulo');
  assert.match(text, /sábado/);
  assert.match(text, /data de hoje: 2026-10-10/);
});
