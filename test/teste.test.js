import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createTestAgent } from '../server/teste.js';

// 16:00 UTC de 11/10/2026 são 13:00 em São Paulo.
const clock = () => new Date('2026-10-11T16:00:00Z');
const agent = createTestAgent({ timeZone: 'America/Sao_Paulo', clock });
const ask = async (message) => (await agent.respond({ message })).reply;

test('responde as horas no fuso do usuário', async () => {
  assert.equal(await ask('Que horas são?'), 'Agora são 13:00.');
});

test('responde a data de hoje por extenso', async () => {
  const reply = await ask('Que dia é hoje?');
  assert.match(reply, /^Hoje é .*domingo, 11 de outubro de 2026\.$/);
});

test('reconhece cumprimentos com ou sem acento', async () => {
  assert.match(await ask('Olá, Jarvis'), /^Olá! Estou no modo de teste/);
  assert.match(await ask('oi'), /^Olá!/);
});

test('pedidos de agenda, e-mail e arquivos avisam que não funcionam no teste', async () => {
  assert.match(await ask('anote amanhã às 13 horas um serviço'), /precisam da chave da Anthropic/);
  assert.match(await ask('tem e-mail não lido?'), /precisam da chave da Anthropic/);
});

test('mensagens fora do roteiro recebem a explicação do modo de teste', async () => {
  assert.match(await ask('qual a capital da França?'), /^Ainda não sei responder isso no modo de teste/);
});

test('o modo de teste não usa ferramentas', async () => {
  const result = await agent.respond({ message: 'oi' });
  assert.deepEqual(result.toolsUsed, []);
});
