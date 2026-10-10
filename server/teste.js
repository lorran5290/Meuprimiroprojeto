// Modo de teste: responde sem chamar a API da Anthropic, com respostas prontas.
// Serve para testar voz, palavra "Jarvis" e a janela sem gastar créditos.

const HELP = 'No modo de teste eu sei responder que horas são, que dia é hoje e cumprimentos. Para conversar de verdade, configure a chave da Anthropic.';

function normalize(text) {
  return text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

export function createTestAgent({ timeZone, clock = () => new Date() }) {
  const timeFormat = new Intl.DateTimeFormat('pt-BR', { timeZone, hour: '2-digit', minute: '2-digit' });
  const dateFormat = new Intl.DateTimeFormat('pt-BR', {
    timeZone,
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });

  function replyTo(message) {
    const text = normalize(message);
    if (/\b(agenda|anot\w*|marc\w*|e-?mail|gmail|drive|arquivo|contrato)\b/.test(text)) {
      return 'Agenda, Gmail e Drive precisam da chave da Anthropic e da conta Google conectada. No modo de teste eles não funcionam.';
    }
    if (/\bajuda\b/.test(text)) return HELP;
    if (/\bhoras?\b/.test(text)) return `Agora são ${timeFormat.format(clock())}.`;
    if (/\b(que dia|data|hoje)\b/.test(text)) return `Hoje é ${dateFormat.format(clock())}.`;
    if (/\b(oi|ola|bom dia|boa tarde|boa noite)\b/.test(text)) {
      return 'Olá! Estou no modo de teste. Pergunte que horas são, que dia é hoje, ou diga ajuda.';
    }
    if (/\bobrigad[oa]\b/.test(text)) return 'De nada!';
    return `Ainda não sei responder isso no modo de teste. ${HELP}`;
  }

  return {
    async respond({ message }) {
      return { reply: replyTo(message), toolsUsed: [] };
    },
  };
}
