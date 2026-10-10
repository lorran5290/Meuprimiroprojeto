import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseUtterance } from '../public/wake.js';

test('separa o comando quando a fala começa com "Jarvis"', () => {
  assert.deepEqual(parseUtterance('Jarvis, anote pra mim amanhã às 13h'), {
    woke: true,
    command: 'anote pra mim amanhã às 13h',
  });
});

test('aceita saudação antes do nome e pontuação em qualquer caixa', () => {
  assert.deepEqual(parseUtterance('Ei, JARVIS! Que horas são?'), { woke: true, command: 'Que horas são?' });
  assert.deepEqual(parseUtterance('Olá Jarvis quanto é 2 mais 2'), { woke: true, command: 'quanto é 2 mais 2' });
});

test('"Jarvis" sozinho acorda o assistente sem comando', () => {
  assert.deepEqual(parseUtterance('Jarvis.'), { woke: true, command: '' });
});

test('menção ao nome no meio da frase não conta como chamado', () => {
  assert.deepEqual(parseUtterance('Eu falei com o Jarvis ontem'), {
    woke: false,
    command: 'Eu falei com o Jarvis ontem',
  });
});
