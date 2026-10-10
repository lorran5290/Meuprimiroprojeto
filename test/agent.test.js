import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildSystemPrompt, createAgent } from '../server/agent.js';

// Cliente falso da Anthropic: devolve respostas roteirizadas e grava cada requisição.
function scriptedClient(responses) {
  const requests = [];
  return {
    requests,
    messages: {
      async create(params) {
        requests.push(structuredClone(params));
        const next = responses.shift();
        if (!next) throw new Error('sem resposta roteirizada');
        return next;
      },
    },
  };
}

const CLOCK = () => new Date('2026-10-10T20:00:00Z');
const textTurn = (text) => ({ stop_reason: 'end_turn', content: [{ type: 'text', text }] });
const toolTurn = (...uses) => ({
  stop_reason: 'tool_use',
  content: uses.map((use) => ({ type: 'tool_use', id: use.id, name: use.name, input: use.input })),
});

function fakeTools(execute = async (name, input) => ({ name, input, events: [] })) {
  return { definitions: [{ name: 'calendar_list_events' }], execute };
}

test('responde direto quando o modelo não precisa de ferramentas', async () => {
  const client = scriptedClient([textTurn('Olá, senhor.')]);
  const agent = createAgent({ client, model: 'modelo-teste', tools: fakeTools(), timeZone: 'America/Sao_Paulo', clock: CLOCK });

  const result = await agent.respond({ message: 'Oi, Jarvis' });

  assert.deepEqual(result, { reply: 'Olá, senhor.', toolsUsed: [] });
  assert.equal(client.requests[0].model, 'modelo-teste');
  assert.deepEqual(client.requests[0].messages, [{ role: 'user', content: 'Oi, Jarvis' }]);
  assert.match(client.requests[0].system, /data de hoje: 2026-10-10/);
});

test('executa a ferramenta pedida, devolve o resultado ao modelo e responde com o texto final', async () => {
  const client = scriptedClient([
    toolTurn({ id: 'tu-1', name: 'calendar_list_events', input: { start_date: '2026-10-11', end_date: '2026-10-11' } }),
    textTurn('Amanhã você tem dentista às 9 horas.'),
  ]);
  const executed = [];
  const tools = fakeTools(async (name, input) => {
    executed.push({ name, input });
    return { events: [{ title: 'Dentista' }] };
  });
  const agent = createAgent({ client, model: 'm', tools, timeZone: 'America/Sao_Paulo', clock: CLOCK });

  const result = await agent.respond({ message: 'O que tenho amanhã?' });

  assert.equal(result.reply, 'Amanhã você tem dentista às 9 horas.');
  assert.deepEqual(result.toolsUsed, ['calendar_list_events']);
  assert.deepEqual(executed, [{ name: 'calendar_list_events', input: { start_date: '2026-10-11', end_date: '2026-10-11' } }]);

  const followUp = client.requests[1].messages.at(-1);
  assert.equal(followUp.role, 'user');
  assert.equal(followUp.content[0].type, 'tool_result');
  assert.equal(followUp.content[0].tool_use_id, 'tu-1');
  assert.equal(followUp.content[0].content, JSON.stringify({ events: [{ title: 'Dentista' }] }));
});

test('erro de ferramenta volta ao modelo como is_error, sem derrubar a conversa', async () => {
  const client = scriptedClient([
    toolTurn({ id: 'tu-9', name: 'gmail_search', input: { query: 'is:unread' } }),
    textTurn('O Google ainda não está conectado. Clique em Conectar Google.'),
  ]);
  const tools = fakeTools(async () => {
    throw new Error('O Google não está conectado.');
  });
  const agent = createAgent({ client, model: 'm', tools, timeZone: 'America/Sao_Paulo', clock: CLOCK });

  const result = await agent.respond({ message: 'Tem e-mail não lido?' });

  const toolResult = client.requests[1].messages.at(-1).content[0];
  assert.equal(toolResult.is_error, true);
  assert.equal(toolResult.content, 'O Google não está conectado.');
  assert.match(result.reply, /Conectar Google/);
});

test('inclui o histórico antes da nova mensagem', async () => {
  const client = scriptedClient([textTurn('Certo.')]);
  const agent = createAgent({ client, model: 'm', tools: fakeTools(), timeZone: 'America/Sao_Paulo', clock: CLOCK });

  await agent.respond({
    history: [
      { role: 'user', content: 'Primeira pergunta' },
      { role: 'assistant', content: 'Primeira resposta' },
    ],
    message: 'Segunda pergunta',
  });

  assert.deepEqual(client.requests[0].messages.map((m) => m.content), [
    'Primeira pergunta',
    'Primeira resposta',
    'Segunda pergunta',
  ]);
});

test('para depois de maxSteps e devolve uma resposta de segurança', async () => {
  const endless = Array.from({ length: 5 }, (_, i) => toolTurn({ id: `tu-${i}`, name: 'calendar_list_events', input: {} }));
  const client = scriptedClient(endless);
  const agent = createAgent({ client, model: 'm', tools: fakeTools(), timeZone: 'America/Sao_Paulo', maxSteps: 2, clock: CLOCK });

  const result = await agent.respond({ message: 'loop' });

  assert.equal(client.requests.length, 2);
  assert.match(result.reply, /não consegui concluir/);
  assert.equal(result.toolsUsed.length, 2);
});

test('o prompt do sistema proíbe envio de e-mail e pede formato falado', () => {
  const prompt = buildSystemPrompt({ now: CLOCK(), timeZone: 'America/Sao_Paulo' });
  assert.match(prompt, /Você nunca envia e-mails/);
  assert.match(prompt, /Nada de markdown/);
  assert.match(prompt, /America\/Sao_Paulo/);
});
