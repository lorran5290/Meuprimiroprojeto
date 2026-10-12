/* Cliente do LS: liga a interface aos eventos reais do núcleo.
 * Regras: todo texto vindo do modelo ou de arquivos entra com textContent (nunca innerHTML).
 * O estado mostrado no núcleo vem do backend; a animação não inventa conclusões. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const TOKEN = new URLSearchParams(location.hash.slice(1)).get("t") || "";
  history.replaceState(null, "", location.pathname);

  const STATE_LABELS = {
    standby: "EM ESPERA", listening: "ESCUTANDO", processing: "PROCESSANDO", executing: "EXECUTANDO TAREFA",
    speaking: "FALANDO", done: "CONCLUÍDO", error: "ERRO", cancelled: "CANCELADO",
  };
  const STATUS_LABELS = {
    ok: "concluído", unverified: "não confirmado", failed: "falhou", denied: "recusado", cancelled: "cancelado",
    timeout: "tempo esgotado", invalid_args: "argumentos inválidos", unknown_tool: "ferramenta desconhecida",
    unavailable: "indisponível",
  };
  const RISK_LABELS = { leitura: "leitura", reversivel: "reversível", confirmacao: "exige aprovação", externo: "ação externa", bloqueado: "bloqueado" };

  const ui = {
    serverState: "standby", flash: null, flashTimer: null, errorTimer: null,
    busy: false, emergency: false, mic: false, listening: false, wakeTimer: null, speaking: false,
    toolsDone: 0, currentTool: "", intensity: 1, voiceStatus: {}, aiOn: false,
    memorySearchTimer: null, sysTimer: null, memoryCategories: {}, settingsOriginal: null,
    live: false,
  };

  // Utilidades --------------------------------------------------------------
  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }
  function when(ts) {
    const d = typeof ts === "number" ? new Date(ts * 1000) : new Date(ts);
    return isNaN(d) ? "" : d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }
  function toast(message, kind) {
    const box = $("toast");
    box.textContent = message;
    box.dataset.kind = kind || "";
    box.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { box.hidden = true; }, 3800);
  }
  async function api(method, path, body) {
    const opts = { method, headers: { "X-LS-Token": TOKEN } };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(path, opts);
    let data = null;
    try { data = await res.json(); } catch (_) { data = null; }
    if (!res.ok) {
      const detail = data && data.detail;
      const err = new Error(typeof detail === "string" ? detail : `Erro ${res.status}`);
      err.status = res.status;
      throw err;
    }
    return data;
  }
  function pill(id, text, tone) {
    const node = $(id);
    node.textContent = text;
    node.className = "pill" + (tone ? " " + tone : "");
  }

  // Núcleo ----------------------------------------------------------------
  const core = new LSCore.ReactorCore($("core"), { intensity: 1 });
  core.start();

  function computeDisplay() {
    if (ui.emergency) return "cancelled";
    if (ui.serverState === "error") return "error";
    if (ui.flash) return ui.flash;
    if (ui.serverState === "executing") return "executing";
    if (ui.serverState === "processing") return "processing";
    if (ui.speaking) return "speaking";
    if (ui.listening) return "listening";
    return "standby";
  }
  function applyDisplay() {
    const shown = computeDisplay();
    core.setState(shown === "listening" ? "listening" : shown);
    document.body.dataset.state = shown;
    $("core-label").textContent = shown === "listening" ? "ESCUTANDO" : STATE_LABELS[shown] || "EM ESPERA";
    $("core-detail").textContent = shown === "executing" && ui.currentTool ? "Ferramenta: " + ui.currentTool : "";
  }
  function flashState(state, ms) {
    ui.flash = state;
    applyDisplay();
    clearTimeout(ui.flashTimer);
    ui.flashTimer = setTimeout(() => { ui.flash = null; applyDisplay(); }, ms);
  }

  // Eventos vindos do backend -------------------------------------------------
  const handlers = {
    hello() {
      clearLiveLists();
      pill("pill-conn", "Conectado", "ok");
      // Até o replay_end, os eventos são histórico: não abrem modal de aprovação.
      ui.live = false;
      refreshConfirmations().catch(() => {});
    },
    replay_end() {
      ui.live = true;
      refreshConfirmations().catch(() => {});
    },
    state(e) {
      const s = e.payload.state;
      if (s === "processing") { ui.serverState = "processing"; ui.toolsDone = 0; ui.flash = null; }
      else if (s === "executing") { ui.serverState = "executing"; ui.currentTool = e.payload.tool || ""; }
      else if (s === "done") { ui.serverState = "standby"; flashState("done", 1600); }
      else if (s === "cancelled") { ui.serverState = "standby"; flashState("cancelled", 1800); }
      else if (s === "error") {
        ui.serverState = "error";
        clearTimeout(ui.errorTimer);
        ui.errorTimer = setTimeout(() => { ui.serverState = "standby"; applyDisplay(); }, 3000);
      }
      else if (s === "standby") { ui.serverState = "standby"; }
      applyDisplay();
    },
    task(e) {
      if (e.payload.phase === "start") { ui.busy = true; }
      if (e.payload.phase === "end") { ui.busy = false; }
      refreshComposer();
    },
    message(e) { addBubble(e.payload); },
    tool(e) {
      const p = e.payload;
      if (p.phase === "start") {
        addActivity("run", `▶ ${p.title}`, `Risco: ${RISK_LABELS[p.risk] || p.risk}`);
        ui.currentTool = p.title;
        return;
      }
      ui.toolsDone += 1;
      core.setProgress(Math.min(0.95, 0.25 + 0.15 * ui.toolsDone));
      const tone = p.status === "ok" ? "ok" : p.status === "unverified" ? "warn" : "bad";
      const approval = p.approval ? ` · aprovação: ${p.approval}` : "";
      addActivity(tone, `${p.tool}: ${STATUS_LABELS[p.status] || p.status}`, `${p.message}${approval}`);
    },
    confirmation(e) {
      const p = e.payload;
      if (p.action === "requested") {
        renderConfirmation(p);
        if (ui.live && !$("confirm-dialog").open) openConfirm(p);
        addActivity("warn", `Aprovação solicitada: ${p.title}`, p.description);
      } else {
        removeConfirmation(p.id);
        addActivity(p.action === "approved" ? "ok" : "bad",
          p.action === "approved" ? "Ação aprovada" : "Ação não aprovada", p.reason || "");
      }
    },
    voice(e) {
      const p = e.payload;
      switch (p.event) {
        case "mic":
          ui.mic = !!p.on; setMicButton(); break;
        case "state":
          ui.listening = p.state === "acordado" || p.state === "ouvindo";
          if (p.state === "erro") toast("Problema no microfone. Veja a aba Atividade.", "bad");
          applyDisplay(); break;
        case "wake":
          ui.listening = true; applyDisplay();
          clearTimeout(ui.wakeTimer);
          ui.wakeTimer = setTimeout(() => { ui.listening = false; applyDisplay(); }, 2500);
          addActivity("ok", "Palavra de ativação reconhecida", "LS está ouvindo.");
          break;
        case "speaking":
          ui.speaking = !!p.on; applyDisplay(); break;
        case "command":
          addActivity("run", "Comando por voz", p.text); break;
        case "error":
          addActivity("bad", "Voz", p.message); toast(p.message, "bad"); break;
        default: break;
      }
    },
    emergency(e) {
      ui.emergency = !!e.payload.active;
      $("emergency-banner").hidden = !ui.emergency;
      applyDisplay();
    },
  };

  function dispatch(event) {
    const fn = handlers[event.type];
    if (fn) fn(event);
  }

  // Conversa, atividade e aprovações ----------------------------------------------
  function addBubble(p) {
    const role = p.role === "usuario" ? "user" : p.role === "sistema" ? "sistema" : "ls";
    const bubble = el("div", "bubble " + role);
    bubble.appendChild(el("span", "", p.text));
    if (p.source === "voz") bubble.appendChild(el("span", "meta", "por voz"));
    if (p.actions && p.actions.length) {
      const chips = el("div", "chips");
      for (const a of p.actions) {
        const tone = a.status === "ok" ? "ok" : a.status === "unverified" ? "warn" : "bad";
        chips.appendChild(el("span", "chip " + tone, `${a.tool}: ${STATUS_LABELS[a.status] || a.status}`));
      }
      bubble.appendChild(chips);
    }
    if (p.mode === "local") bubble.appendChild(el("span", "meta", "modo local (sem IA)"));
    if (p.model) bubble.appendChild(el("span", "meta", p.model));
    const box = $("transcript");
    box.appendChild(bubble);
    box.scrollTop = box.scrollHeight;
  }

  function addActivity(tone, title, detail) {
    const list = $("activity");
    const item = el("li", tone);
    item.appendChild(el("span", "when", when(Date.now() / 1000)));
    item.appendChild(el("strong", "", title));
    if (detail) item.appendChild(el("span", "", detail));
    list.insertBefore(item, list.firstChild);
    while (list.children.length > 120) list.removeChild(list.lastChild);
  }

  function renderConfirmation(p) {
    const box = $("confirmations");
    if (box.querySelector(`[data-id="${CSS.escape(p.id)}"]`)) return;
    if (box.querySelector(".muted")) box.textContent = "";
    const card = el("div", "confirm-card");
    card.dataset.id = p.id;
    card.appendChild(el("strong", "", p.title));
    card.appendChild(el("span", "", p.description));
    card.appendChild(el("span", "muted", `Risco: ${RISK_LABELS[p.risk] || p.risk} · expira às ${when(p.expires_at)}`));
    const actions = el("div", "actions");
    const yes = el("button", "primary", "Aprovar");
    const no = el("button", "danger", "Recusar");
    armApprove(yes);
    yes.addEventListener("click", () => answer(p.id, true));
    no.addEventListener("click", () => answer(p.id, false));
    actions.append(no, yes);
    card.appendChild(actions);
    box.appendChild(card);
  }
  function removeConfirmation(id) {
    const card = $("confirmations").querySelector(`[data-id="${CSS.escape(id)}"]`);
    if (card) card.remove();
    if (!$("confirmations").children.length) $("confirmations").appendChild(el("p", "muted", "Nada aguardando sua decisão."));
    if ($("confirm-dialog").open && $("confirm-dialog").dataset.id === id) $("confirm-dialog").close();
  }
  // Aprovar só fica disponível após um pequeno intervalo: evita aprovação por um Enter ou clique
  // que já estava em curso. O foco inicial vai para "Recusar", que é o lado seguro.
  const ARM_DELAY_MS = 1500;
  function armApprove(button) {
    button.disabled = true;
    setTimeout(() => { button.disabled = false; }, ARM_DELAY_MS);
  }
  function openConfirm(p) {
    const dialog = $("confirm-dialog");
    dialog.dataset.id = p.id;
    $("confirm-title").textContent = "Confirmação necessária";
    $("confirm-desc").textContent = p.description;
    $("confirm-meta").textContent = `${p.title} · risco: ${RISK_LABELS[p.risk] || p.risk}`;
    armApprove($("confirm-yes"));
    dialog.showModal();
    $("confirm-no").focus();
  }
  async function refreshConfirmations() {
    const pending = await api("GET", "/api/confirmacoes");
    const box = $("confirmations");
    box.textContent = "";
    if (!pending.length) box.appendChild(el("p", "muted", "Nada aguardando sua decisão."));
    for (const p of pending) renderConfirmation(p);
  }
  async function answer(id, approved) {
    try {
      await api("POST", `/api/confirmacoes/${encodeURIComponent(id)}`, { aprovado: approved });
    } catch (err) {
      toast(err.message, "bad");
    }
    removeConfirmation(id);
  }
  $("confirm-yes").addEventListener("click", () => { const id = $("confirm-dialog").dataset.id; $("confirm-dialog").close(); answer(id, true); });
  $("confirm-no").addEventListener("click", () => { const id = $("confirm-dialog").dataset.id; $("confirm-dialog").close(); answer(id, false); });

  function clearLiveLists() {
    $("transcript").textContent = "";
    $("activity").textContent = "";
    ui.busy = false;
    refreshComposer();
  }

  // Composer -----------------------------------------------------------------------
  function refreshComposer() {
    $("btn-cancel").hidden = !ui.busy;
    $("btn-send").disabled = false;
    $("btn-send").title = ui.busy ? "Ainda processando o pedido anterior" : "Enviar";
  }
  $("composer").addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = $("input");
    const text = input.value.trim();
    if (!text) return;
    try {
      await api("POST", "/api/chat", { texto: text });
      input.value = "";
    } catch (err) {
      toast(err.message, "bad");
    }
  });
  $("btn-cancel").addEventListener("click", async () => {
    try { await api("POST", "/api/cancelar"); toast("Cancelamento solicitado.", "warn"); }
    catch (err) { toast(err.message, "bad"); }
  });
  function setMicButton() {
    const btn = $("btn-mic");
    btn.setAttribute("aria-pressed", String(ui.mic));
    btn.title = ui.mic ? "Microfone ligado (clique para desligar)" : "Microfone desligado (clique para ligar)";
    pill("pill-mic", ui.mic ? "Microfone: ligado" : "Microfone: desligado", ui.mic ? "ok" : "");
  }
  $("btn-mic").addEventListener("click", async () => {
    try {
      const status = await api("POST", "/api/microfone", { ligado: !ui.mic });
      ui.mic = status.microfone === "ligado";
      setMicButton();
    } catch (err) { toast(err.message, "bad"); }
  });
  $("btn-talk").addEventListener("click", async () => {
    try { await api("POST", "/api/falar"); toast("Pode falar.", ""); }
    catch (err) { toast(err.message, "bad"); }
  });
  $("btn-stop-speech").addEventListener("click", async () => {
    try { await api("POST", "/api/fala/parar"); } catch (err) { toast(err.message, "bad"); }
  });
  $("btn-emergency").addEventListener("click", async () => {
    try {
      const res = await api("POST", "/api/emergencia");
      ui.emergency = true;
      $("emergency-banner").hidden = false;
      applyDisplay();
      toast(`Parada ativada: ${res.tasks_cancelled} tarefa(s) canceladas, ${res.approvals_denied} aprovação(ões) recusada(s).`, "bad");
    } catch (err) { toast(err.message, "bad"); }
  });
  $("btn-release").addEventListener("click", async () => {
    try {
      await api("POST", "/api/emergencia/liberar");
      ui.emergency = false;
      $("emergency-banner").hidden = true;
      applyDisplay();
      toast("Parada liberada.", "ok");
    } catch (err) { toast(err.message, "bad"); }
  });
  $("btn-fullscreen").addEventListener("click", () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else if (document.documentElement.requestFullscreen) document.documentElement.requestFullscreen().catch(() => toast("Tela cheia indisponível.", "warn"));
  });

  // Abas ---------------------------------------------------------------------------
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => selectTab(tab.dataset.tab));
  });
  function selectTab(name) {
    document.querySelectorAll(".tab").forEach((t) => {
      const on = t.dataset.tab === name;
      t.classList.toggle("active", on);
      t.setAttribute("aria-selected", String(on));
    });
    for (const panel of ["memory", "system", "history"]) $("tab-" + panel).hidden = panel !== name;
    clearInterval(ui.sysTimer);
    if (name === "memory") loadMemories();
    if (name === "system") { loadSystem(); ui.sysTimer = setInterval(loadSystem, 4000); }
    if (name === "history") { loadHistory(); loadAudit(); }
  }

  // Memória --------------------------------------------------------------------------
  async function loadCategories() {
    ui.memoryCategories = await api("GET", "/api/memorias/categorias");
    const filter = $("mem-category");
    const formSel = $("mem-cat-form");
    filter.textContent = ""; formSel.textContent = "";
    filter.appendChild(new Option("Todas", ""));
    for (const [key, label] of Object.entries(ui.memoryCategories)) {
      filter.appendChild(new Option(label, key));
      formSel.appendChild(new Option(label, key));
    }
  }
  async function loadMemories() {
    try {
      const q = encodeURIComponent($("mem-search").value.trim());
      const cat = encodeURIComponent($("mem-category").value);
      const items = await api("GET", `/api/memorias?consulta=${q}&categoria=${cat}`);
      const list = $("mem-list");
      list.textContent = "";
      if (!items.length) list.appendChild(el("p", "muted", "Nenhuma memória encontrada."));
      for (const m of items) list.appendChild(memoryItem(m));
      loadConflicts();
    } catch (err) { toast(err.message, "bad"); }
  }
  function memoryItem(m) {
    const card = el("button", "mem-item");
    card.type = "button";
    const head = el("div", "head");
    head.appendChild(el("span", "", `#${m.id} · ${m.category_label}`));
    const tags = el("span");
    if (m.sensitive) tags.appendChild(el("span", "tag sens", "sensível"));
    if (m.source === "seed") tags.appendChild(el("span", "tag", "inicial"));
    head.appendChild(tags);
    card.appendChild(head);
    if (m.key) card.appendChild(el("div", "title", m.key));
    card.appendChild(el("div", "body", m.content));
    card.addEventListener("click", () => fillMemoryForm(m));
    return card;
  }
  function fillMemoryForm(m) {
    $("mem-id").value = m.id;
    $("mem-cat-form").value = m.category;
    $("mem-key").value = m.key || "";
    $("mem-content").value = m.sensitive ? "" : m.content;
    $("mem-sensitive").checked = !!m.sensitive;
    $("mem-editor-title").textContent = `Editar memória #${m.id}`;
    $("mem-delete").hidden = false;
    $("mem-editor-box").open = true;
    if (m.sensitive) toast("Item sensível: o conteúdo fica oculto. Digite a nova versão para substituí-lo.", "warn");
  }
  function resetMemoryForm() {
    $("mem-form").reset();
    $("mem-id").value = "";
    $("mem-editor-title").textContent = "Nova memória";
    $("mem-delete").hidden = true;
  }
  $("mem-reset").addEventListener("click", resetMemoryForm);
  $("mem-search").addEventListener("input", () => {
    clearTimeout(ui.memorySearchTimer);
    ui.memorySearchTimer = setTimeout(loadMemories, 250);
  });
  $("mem-category").addEventListener("change", loadMemories);
  $("mem-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const id = $("mem-id").value;
    const body = {
      conteudo: $("mem-content").value.trim(),
      categoria: $("mem-cat-form").value,
      chave: $("mem-key").value.trim(),
      sensivel: $("mem-sensitive").checked,
    };
    try {
      if (id) {
        await api("PATCH", `/api/memorias/${id}`, body);
        toast("Memória atualizada.", "ok");
      } else {
        const res = await api("POST", "/api/memorias", body);
        toast(res.conflitos.length ? "Salva. Atenção: há informação diferente para o mesmo assunto." : "Memória salva.",
          res.conflitos.length ? "warn" : "ok");
      }
      resetMemoryForm();
      loadMemories();
    } catch (err) { toast(err.message, "bad"); }
  });
  $("mem-delete").addEventListener("click", async () => {
    const id = $("mem-id").value;
    if (!id || !window.confirm(`Apagar a memória #${id}? Isso não pode ser desfeito.`)) return;
    try {
      await api("DELETE", `/api/memorias/${id}`);
      toast("Memória apagada.", "ok");
      resetMemoryForm();
      loadMemories();
    } catch (err) { toast(err.message, "bad"); }
  });
  async function loadConflicts() {
    const items = await api("GET", "/api/memorias/conflitos");
    const box = $("conflicts-box");
    const list = $("conflicts");
    list.textContent = "";
    box.hidden = !items.length;
    for (const c of items) {
      const row = el("div", "activity");
      row.appendChild(el("strong", "", `Assunto: ${c.chave}`));
      for (const v of c.versoes) row.appendChild(el("span", "", `#${v.id}: ${v.content}`));
      list.appendChild(row);
    }
  }
  $("btn-backup").addEventListener("click", async () => {
    try { const r = await api("POST", "/api/memorias/backup"); toast(`Backup salvo: ${r.path}`, "ok"); }
    catch (err) { toast(err.message, "bad"); }
  });
  $("btn-import").addEventListener("click", async () => {
    const caminho = $("import-path").value.trim();
    if (!caminho) { toast("Informe o caminho do arquivo de backup.", "warn"); return; }
    try {
      const r = await api("POST", "/api/memorias/importar", { caminho, modo: $("import-mode").value });
      toast(`Importação: ${r.added} adicionada(s), ${r.skipped} ignorada(s).`, "ok");
      loadMemories();
    } catch (err) { toast(err.message, "bad"); }
  });

  // Sistema ----------------------------------------------------------------------------
  function meter(label, percent, suffix) {
    const wrap = el("div", "meter");
    const head = el("div", "label");
    head.appendChild(el("span", "", label));
    head.appendChild(el("span", "", suffix || `${percent.toFixed(0)}%`));
    const bar = el("div", "bar");
    const fill = el("div", "fill" + (percent >= 85 ? " hot" : ""));
    fill.style.width = Math.max(0, Math.min(100, percent)) + "%";
    bar.appendChild(fill);
    wrap.append(head, bar);
    return wrap;
  }
  async function loadSystem() {
    try {
      const s = await api("GET", "/api/sistema");
      const box = $("sys");
      box.textContent = "";
      box.appendChild(meter("CPU", s.cpu.uso_percent));
      box.appendChild(meter("Memória", s.memoria.uso_percent, `${s.memoria.usada_gb} / ${s.memoria.total_gb} GB`));
      for (const d of s.discos) box.appendChild(meter(`Disco ${d.unidade}`, d.uso_percent, `${d.livre_gb} GB livres`));
      const dl = el("dl", "kv");
      const rows = [
        ["Processos", s.processos],
        ["Rede (enviado / recebido)", `${s.rede.enviado_mb} / ${s.rede.recebido_mb} MB`],
        ["Bateria", s.bateria ? `${s.bateria.percentual}%${s.bateria.conectada ? " (na tomada)" : ""}` : "não aplicável"],
        ["Temperatura", s.temperatura.disponivel
          ? Object.entries(s.temperatura.celsius).slice(0, 3).map(([k, v]) => `${k} ${v}°C`).join(" · ")
          : s.temperatura.motivo],
        ["Ligado desde", s.ligado_desde],
      ];
      for (const [k, v] of rows) { dl.appendChild(el("dt", "", k)); dl.appendChild(el("dd", "", v)); }
      box.appendChild(dl);
    } catch (err) { toast(err.message, "bad"); }
  }

  // Histórico e auditoria -------------------------------------------------------------
  async function loadHistory() {
    const items = await api("GET", "/api/historico");
    const list = $("history");
    list.textContent = "";
    for (const m of items.slice().reverse()) {
      const li = el("li", m.role === "usuario" ? "run" : "ok");
      li.appendChild(el("span", "when", when(m.created_at)));
      li.appendChild(el("span", "", `${m.role === "usuario" ? "Você" : "LS"}: ${m.text}`));
      list.appendChild(li);
    }
    if (!items.length) list.appendChild(el("li", "", "Sem histórico salvo."));
  }
  async function loadAudit() {
    const items = await api("GET", "/api/auditoria?limite=100");
    const list = $("audit");
    list.textContent = "";
    for (const a of items) {
      const tone = a.status === "ok" ? "ok" : a.status === "unverified" ? "warn" : "bad";
      const li = el("li", tone);
      li.appendChild(el("span", "when", `${when(a.ts)} · ${a.source}`));
      li.appendChild(el("strong", "", `${a.tool} — ${STATUS_LABELS[a.status] || a.status}`));
      li.appendChild(el("span", "", a.message));
      if (a.approval) li.appendChild(el("span", "muted", `aprovação: ${a.approval}`));
      const del = el("button", "ghost", "Apagar registro");
      del.addEventListener("click", async () => {
        try { await api("DELETE", `/api/auditoria/${a.id}`); loadAudit(); }
        catch (err) { toast(err.message, "bad"); }
      });
      li.appendChild(del);
      list.appendChild(li);
    }
    if (!items.length) list.appendChild(el("li", "", "Nenhuma ação registrada."));
  }
  $("btn-clear-history").addEventListener("click", async () => {
    if (!window.confirm("Apagar todo o histórico de conversas?")) return;
    await api("DELETE", "/api/historico"); loadHistory();
  });
  $("btn-clear-audit").addEventListener("click", async () => {
    if (!window.confirm("Apagar todos os registros de auditoria?")) return;
    await api("DELETE", "/api/auditoria"); loadAudit();
  });

  // Configurações --------------------------------------------------------------------------
  const settingsDialog = $("settings");
  $("btn-settings").addEventListener("click", openSettings);
  $("set-close").addEventListener("click", () => settingsDialog.close());
  $("set-intensity").addEventListener("input", (e) => { ui.intensity = Number(e.target.value); core.setIntensity(ui.intensity); });
  async function openSettings() {
    try {
      const [cfg, voices] = await Promise.all([api("GET", "/api/configuracoes"), api("GET", "/api/vozes")]);
      ui.settingsOriginal = cfg;
      $("set-model").value = cfg.gemini_model;
      $("set-intensity").value = cfg.effects_intensity;
      $("set-tts").checked = cfg.tts_enabled;
      $("set-rate").value = cfg.tts_rate;
      $("set-volume").value = cfg.tts_volume;
      $("set-wake").checked = cfg.wake_word_enabled;
      $("set-history").checked = cfg.keep_history;
      $("set-autostart").checked = cfg.autostart;
      const select = $("set-voice");
      select.textContent = "";
      select.appendChild(new Option("Padrão do Windows", ""));
      for (const v of voices) select.appendChild(new Option(`${v.nome} (${v.idioma})`, v.nome));
      select.value = cfg.tts_voice || "";
      $("set-note").textContent = cfg.gemini_api_key_configured
        ? "Chave Gemini configurada no .env. Alterações valem na hora."
        : "Sem GEMINI_API_KEY: o LS funciona só em modo local. Veja o README.";
      settingsDialog.showModal();
    } catch (err) { toast(err.message, "bad"); }
  }
  $("set-save").addEventListener("click", async () => {
    const orig = ui.settingsOriginal || {};
    const next = {
      gemini_model: $("set-model").value.trim(),
      effects_intensity: Number($("set-intensity").value),
      tts_enabled: $("set-tts").checked,
      tts_voice: $("set-voice").value || null,
      tts_rate: Number($("set-rate").value),
      tts_volume: Number($("set-volume").value),
      wake_word_enabled: $("set-wake").checked,
      keep_history: $("set-history").checked,
      autostart: $("set-autostart").checked,
    };
    const changes = {};
    for (const [k, v] of Object.entries(next)) {
      if (JSON.stringify(orig[k]) !== JSON.stringify(v)) changes[k] = v;
    }
    if (!Object.keys(changes).length) { settingsDialog.close(); return; }
    try {
      const saved = await api("PATCH", "/api/configuracoes", { valores: changes });
      ui.intensity = saved.effects_intensity;
      core.setIntensity(ui.intensity);
      settingsDialog.close();
      toast("Configurações salvas.", "ok");
      loadStatus();
    } catch (err) { toast(err.message, "bad"); }
  });

  // Status e catálogo -------------------------------------------------------------------
  async function loadStatus() {
    try {
      const s = await api("GET", "/api/status");
      ui.aiOn = s.ia.ativa;
      ui.voiceStatus = s.voz;
      ui.mic = s.voz.microfone === "ligado";
      ui.emergency = s.emergencia;
      $("emergency-banner").hidden = !ui.emergency;
      setMicButton();
      pill("pill-ia", s.ia.ativa ? `IA: ${s.ia.modelo}` : "IA: modo local", s.ia.ativa ? "ok" : "warn");
      if (!s.voz.fala_disponivel) $("btn-stop-speech").title = "Fala indisponível neste sistema";
      applyDisplay();
    } catch (err) { pill("pill-ia", "IA: sem resposta", "bad"); }
  }
  async function loadCatalog() {
    const tools = await api("GET", "/api/catalogo");
    const list = $("tools");
    list.textContent = "";
    for (const t of tools) {
      const li = el("li");
      li.appendChild(el("span", "", t.title));
      li.appendChild(el("span", "risk " + t.risk, RISK_LABELS[t.risk] || t.risk));
      list.appendChild(li);
    }
  }

  // Tempo real --------------------------------------------------------------------------
  let socket = null;
  let backoff = 1000;
  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(TOKEN)}`);
    socket.onopen = () => { backoff = 1000; pill("pill-conn", "Conectando…", ""); };
    socket.onmessage = (msg) => {
      try { dispatch(JSON.parse(msg.data)); }
      catch (err) { console.error("Evento inválido", err); }
    };
    socket.onclose = (ev) => {
      if (ev.code === 1008) { pill("pill-conn", "Sessão inválida", "bad"); return; }
      pill("pill-conn", "Reconectando…", "warn");
      setTimeout(connect, backoff);
      backoff = Math.min(8000, backoff * 2);
    };
  }

  // Inicialização -----------------------------------------------------------------------
  function boot() {
    const splash = $("boot");
    setTimeout(() => splash.classList.add("done"), 900);
    setTimeout(() => splash.remove(), 1600);
    if (!TOKEN) {
      pill("pill-conn", "Abra o LS pela janela ou pelo endereço completo com #t=", "bad");
      return;
    }
    loadCategories().catch(() => {});
    loadCatalog().catch(() => {});
    loadStatus();
    setInterval(loadStatus, 15000);
    loadMemories();
    connect();
    applyDisplay();
    refreshComposer();
  }
  boot();
})();
