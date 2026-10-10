// Detecta o chamado "Jarvis" no começo da fala e separa o comando.
// Fica em módulo próprio para ser testado fora do navegador.
const WAKE_RE = /^\s*(?:(?:oi|ol[aá]|ok|ei|e a[ií])[\s,]+)?jarvis\b[\s,.!?:;-]*/i;

export function parseUtterance(transcript) {
  const text = String(transcript ?? '').trim();
  const match = text.match(WAKE_RE);
  if (!match) return { woke: false, command: text };
  return { woke: true, command: text.slice(match[0].length).trim() };
}
