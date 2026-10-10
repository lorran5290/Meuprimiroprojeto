import { describeNow } from './time.js';

const MAX_TOKENS = 1024;
const FALLBACK_REPLY = 'Desculpe, não consegui concluir isso agora. Pode tentar de novo?';
const EMPTY_REPLY = 'Não tenho uma resposta para isso.';

export function buildSystemPrompt({ now, timeZone }) {
  return [
    'Você é o Jarvis, assistente pessoal do usuário, inspirado no Jarvis dos filmes do Homem de Ferro.',
    'Você conversa por voz: tudo o que você escrever será lido em voz alta.',
    '',
    'Estilo:',
    '- Responda em português do Brasil, de forma curta, natural e cordial.',
    '- Nada de markdown, listas com símbolos, emojis, tabelas ou URLs.',
    '- Quando listar compromissos ou e-mails, fale em frases corridas (ex.: "Amanhã você tem dentista às 9 horas e reunião às 14 horas").',
    '',
    `Agora são ${describeNow(now, timeZone)}. Fuso do usuário: ${timeZone}.`,
    'Use essa referência para interpretar "hoje", "amanhã", "depois de amanhã", dias da semana e horários.',
    '',
    'Ferramentas e cuidados:',
    '- Use as ferramentas do Google para ler agenda, e-mails e arquivos reais. Nunca invente compromissos, e-mails ou arquivos.',
    '- Ao criar um evento, confirme na resposta o título, o dia e o horário. Se faltar a data ou a hora, pergunte antes de criar.',
    '- Você nunca envia e-mails. Você só cria rascunhos, e deve dizer que o usuário precisa revisar e enviar.',
    '- Se uma ferramenta falhar porque o Google não está conectado, diga isso e oriente o usuário a clicar em "Conectar Google".',
  ].join('\n');
}

function textOf(content) {
  return content
    .filter((block) => block.type === 'text')
    .map((block) => block.text)
    .join('')
    .trim();
}

export function createAgent({ client, model, tools, timeZone, maxSteps = 6, clock = () => new Date() }) {
  return {
    async respond({ history = [], message }) {
      const messages = [...history, { role: 'user', content: message }];
      const toolsUsed = [];

      for (let step = 0; step < maxSteps; step += 1) {
        const response = await client.messages.create({
          model,
          max_tokens: MAX_TOKENS,
          system: buildSystemPrompt({ now: clock(), timeZone }),
          tools: tools.definitions,
          messages,
        });
        messages.push({ role: 'assistant', content: response.content });

        if (response.stop_reason !== 'tool_use') {
          return { reply: textOf(response.content) || EMPTY_REPLY, toolsUsed };
        }

        const results = [];
        for (const block of response.content) {
          if (block.type !== 'tool_use') continue;
          toolsUsed.push(block.name);
          try {
            const output = await tools.execute(block.name, block.input);
            results.push({ type: 'tool_result', tool_use_id: block.id, content: JSON.stringify(output) });
          } catch (error) {
            results.push({ type: 'tool_result', tool_use_id: block.id, content: error.message, is_error: true });
          }
        }
        messages.push({ role: 'user', content: results });
      }

      return { reply: FALLBACK_REPLY, toolsUsed };
    },
  };
}
