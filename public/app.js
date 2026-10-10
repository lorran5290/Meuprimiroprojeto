import { parseUtterance } from './wake.js';

const WAKE_WINDOW_MS = 12_000;
const MAX_HISTORY = 20;
const TOOL_LABELS = {
  calendar_list_events: 'Google Agenda',
  calendar_create_event: 'evento criado na agenda',
  gmail_search: 'Gmail',
  gmail_create_draft: 'rascunho criado no Gmail',
  drive_search: 'Google Drive',
};

const el = {
  log: document.getElementById('log'),
  state: document.getElementById('state'),
  notice: document.getElementById('notice'),
  composer: document.getElementById('composer'),
  input: document.getElementById('input'),
  send: document.getElementById('send'),
  mic: document.getElementById('mic'),
  voice: document.getElementById('voice'),
  alwaysOn: document.getElementById('always-on'),
  google: document.getElementById('google-status'),
  googleAction: document.getElementById('google-action'),
};

const RecognitionImpl = window.SpeechRecognition || window.webkitSpeechRecognition || null;
const synth = 'speechSynthesis' in window ? window.speechSynthesis : null;

const conversation = [];
let busy = false;
let voiceOn = true;
let alwaysOn = false;
let listening = false;
let speaking = false;
let speakId = 0;
let currentUtterance = null;
let recognizer = null;
let recognizerRunning = false;
let wakeUntil = 0;
let interimText = '';
let ptVoice = null;

function notify(text, tone = 'info') {
  el.notice.textContent = text;
  el.notice.dataset.tone = tone;
  el.notice.hidden = !text;
}

function addMessage(role, text, meta = '') {
  const node = document.createElement('div');
  node.className = `msg ${role}`;
  const body = document.createElement('p');
  body.textContent = text;
  node.append(body);
  if (meta) {
    const small = document.createElement('span');
    small.className = 'meta';
    small.textContent = meta;
    node.append(small);
  }
  el.log.append(node);
  node.scrollIntoView({ block: 'end', behavior: 'smooth' });
  return node;
}

function describeTools(toolsUsed = []) {
  const labels = [...new Set(toolsUsed.map((name) => TOOL_LABELS[name]).filter(Boolean))];
  return labels.length ? `Usou: ${labels.join(', ')}` : '';
}

function refreshState() {
  let state = 'idle';
  let label = 'Pronto';
  if (busy) {
    state = 'thinking';
    label = 'Pensando…';
  } else if (speaking) {
    state = 'speaking';
    label = 'Falando…';
  } else if (listening) {
    state = 'listening';
    if (interimText) label = `Ouvindo: "${interimText.slice(0, 60)}"`;
    else label = alwaysOn ? 'Escutando. Diga "Jarvis"…' : 'Ouvindo…';
  }
  document.body.dataset.state = state;
  el.state.textContent = label;
  el.mic.classList.toggle('active', listening);
  el.mic.setAttribute('aria-pressed', String(listening));
  el.alwaysOn.checked = alwaysOn;
  el.voice.checked = voiceOn;
  el.send.disabled = busy;
}

// ---------- Voz de saída ----------

function pickVoice() {
  const voices = synth ? synth.getVoices() : [];
  ptVoice = voices.find((voice) => voice.lang === 'pt-BR') || voices.find((voice) => voice.lang.startsWith('pt')) || null;
}

function speak(text) {
  if (!voiceOn || !synth || !text) return;
  const id = ++speakId;
  synth.cancel();

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'pt-BR';
  if (ptVoice) utterance.voice = ptVoice;
  utterance.rate = 1.05;
  utterance.pitch = 0.95;
  // Guarda a referência: alguns navegadores interrompem a fala se o objeto for coletado.
  currentUtterance = utterance;

  let finished = false;
  const finish = () => {
    if (finished || id !== speakId) return;
    finished = true;
    clearTimeout(safety);
    speaking = false;
    if (listening && alwaysOn) {
      wakeUntil = Date.now() + WAKE_WINDOW_MS;
      recognizer = createRecognizer();
      startRecognizer();
    }
    refreshState();
  };
  // Alguns navegadores não disparam onend; este prazo evita travar a escuta.
  const safety = setTimeout(finish, Math.max(8000, text.length * 120));
  utterance.onend = finish;
  utterance.onerror = finish;

  // Pausa o microfone enquanto o Jarvis fala, para não ouvir a própria voz.
  resetRecognizer();
  speaking = true;
  refreshState();
  synth.speak(utterance);
}

function stopSpeaking() {
  if (!speaking) return;
  speakId += 1;
  speaking = false;
  synth?.cancel();
  // Sem onend para retomar a escuta, religamos aqui.
  if (listening && alwaysOn) {
    resetRecognizer();
    recognizer = createRecognizer();
    startRecognizer();
  }
  refreshState();
}

// ---------- Voz de entrada ----------

function createRecognizer() {
  const rec = new RecognitionImpl();
  rec.lang = 'pt-BR';
  rec.interimResults = true;
  rec.continuous = alwaysOn;
  rec.maxAlternatives = 1;

  rec.onstart = () => {
    if (recognizer !== rec) return;
    recognizerRunning = true;
    refreshState();
  };

  rec.onresult = (event) => {
    if (speaking || recognizer !== rec) return;
    let interim = '';
    let finalText = '';
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const result = event.results[i];
      if (result.isFinal) finalText += result[0].transcript;
      else interim += result[0].transcript;
    }
    interimText = interim.trim();
    if (finalText.trim()) {
      interimText = '';
      if (!alwaysOn) stopListening();
      handleTranscript(finalText.trim());
    }
    refreshState();
  };

  rec.onerror = (event) => {
    if (recognizer !== rec) return;
    if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
      notify('O navegador bloqueou o microfone. Libere a permissão do microfone e tente de novo.', 'error');
      stopListening();
      return;
    }
    if (event.error !== 'no-speech' && event.error !== 'aborted') {
      notify(`Erro no reconhecimento de voz: ${event.error}.`, 'error');
    }
  };

  rec.onend = () => {
    if (recognizer !== rec) return;
    recognizerRunning = false;
    if (!alwaysOn) {
      listening = false;
    } else if (listening && !speaking) {
      setTimeout(() => {
        if (recognizer === rec) startRecognizer();
      }, 300);
    }
    refreshState();
  };

  return rec;
}

function startRecognizer() {
  if (!recognizer || recognizerRunning || speaking) return;
  try {
    recognizer.start();
  } catch {
    // Já estava em execução; nada a fazer.
  }
}

function resetRecognizer() {
  const old = recognizer;
  recognizer = null;
  recognizerRunning = false;
  if (!old) return;
  old.onstart = null;
  old.onresult = null;
  old.onerror = null;
  old.onend = null;
  try {
    old.abort();
  } catch {
    // Já encerrado.
  }
}

function startListening() {
  if (!RecognitionImpl) {
    notify('Este navegador não tem reconhecimento de voz. Use o Chrome ou o Edge.', 'error');
    return;
  }
  stopSpeaking();
  resetRecognizer();
  listening = true;
  recognizer = createRecognizer();
  startRecognizer();
  refreshState();
}

function stopListening() {
  listening = false;
  alwaysOn = false;
  interimText = '';
  resetRecognizer();
  refreshState();
}

function enableAlwaysOn() {
  alwaysOn = true;
  wakeUntil = 0;
  notify('Escuta contínua ligada. Diga "Jarvis" para me chamar. Use fones para evitar que eu ouça a minha própria voz.', 'info');
  startListening();
}

function handleTranscript(transcript) {
  if (busy) return;
  const { woke, command } = parseUtterance(transcript);
  // Na escuta contínua, ignora conversa de fundo que não começa com "Jarvis".
  if (alwaysOn && !woke && Date.now() > wakeUntil) return;
  if (woke) wakeUntil = Date.now() + WAKE_WINDOW_MS;
  const text = woke ? command : transcript;
  if (!text) {
    speak('Pois não?');
    return;
  }
  send(text);
}

// ---------- Conversa ----------

async function send(text) {
  busy = true;
  stopSpeaking();
  interimText = '';
  addMessage('user', text);
  const pending = addMessage('assistant', '…');
  refreshState();

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history: conversation }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || 'Não consegui falar com o Jarvis.');

    pending.remove();
    addMessage('assistant', data.reply, describeTools(data.toolsUsed));
    conversation.push({ role: 'user', content: text }, { role: 'assistant', content: data.reply });
    if (conversation.length > MAX_HISTORY) conversation.splice(0, conversation.length - MAX_HISTORY);
    speak(data.reply);
  } catch (error) {
    pending.remove();
    addMessage('error', error.message);
    speak('Desculpe, não consegui concluir isso.');
  } finally {
    busy = false;
    refreshState();
  }
}

// ---------- Google ----------

function renderGoogle(google) {
  if (!google.configured) {
    el.google.textContent = 'Google: sem credenciais';
    el.googleAction.hidden = true;
    return;
  }
  el.googleAction.hidden = false;
  el.google.textContent = google.connected ? 'Google: conectado' : 'Google: desconectado';
  el.googleAction.textContent = google.connected ? 'Desconectar' : 'Conectar Google';
  el.googleAction.dataset.action = google.connected ? 'disconnect' : 'connect';
}

async function loadStatus() {
  try {
    const res = await fetch('/api/status');
    const status = await res.json();
    renderGoogle(status.google);
    if (status.testMode) {
      notify('Modo de teste: respostas prontas e sem custo. Para perguntas de verdade, configure a chave da Anthropic.', 'info');
    } else if (!status.anthropicConfigured) {
      notify('Falta a ANTHROPIC_API_KEY no servidor. Veja o README.', 'error');
    }
  } catch {
    el.google.textContent = 'Google: indisponível';
    notify('Não consegui falar com o servidor do Jarvis.', 'error');
  }
}

async function onGoogleAction() {
  if (el.googleAction.dataset.action === 'connect') {
    window.location.href = '/auth/google';
    return;
  }
  el.googleAction.disabled = true;
  try {
    await fetch('/auth/google/disconnect', { method: 'POST' });
    notify('Conta do Google desconectada.', 'info');
  } catch {
    notify('Não consegui desconectar agora.', 'error');
  } finally {
    el.googleAction.disabled = false;
    await loadStatus();
  }
}

function readGoogleResult() {
  const result = new URLSearchParams(window.location.search).get('google');
  if (!result) return;
  if (result === 'connected') notify('Google conectado. Agenda, Gmail e Drive já estão disponíveis.', 'ok');
  else notify('Não consegui conectar ao Google. Tente de novo.', 'error');
  window.history.replaceState(null, '', '/');
}

// ---------- Inicialização ----------

function bindEvents() {
  el.composer.addEventListener('submit', (event) => {
    event.preventDefault();
    const text = el.input.value.trim();
    if (!text || busy) return;
    el.input.value = '';
    send(text);
  });
  el.mic.addEventListener('click', () => (listening ? stopListening() : startListening()));
  el.voice.addEventListener('change', () => {
    voiceOn = el.voice.checked;
    if (!voiceOn) stopSpeaking();
  });
  el.alwaysOn.addEventListener('change', () => {
    if (el.alwaysOn.checked) enableAlwaysOn();
    else stopListening();
  });
  el.googleAction.addEventListener('click', onGoogleAction);
}

function init() {
  if (!RecognitionImpl) {
    el.mic.disabled = true;
    el.alwaysOn.disabled = true;
    notify('Reconhecimento de voz indisponível neste navegador. Use o Chrome ou o Edge, ou digite a mensagem.', 'info');
  }
  if (synth) {
    pickVoice();
    synth.addEventListener('voiceschanged', pickVoice);
  } else {
    voiceOn = false;
    el.voice.checked = false;
    el.voice.disabled = true;
  }
  bindEvents();
  readGoogleResult();
  loadStatus();
  addMessage('assistant', 'Jarvis online. Como posso ajudar?');
  refreshState();
}

init();
