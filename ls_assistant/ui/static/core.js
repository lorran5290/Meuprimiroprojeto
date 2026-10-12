/* Núcleo holográfico do LS (canvas 2D, leve o bastante para notebooks como a RTX 2050).
 * O núcleo não inventa estado: quem decide o que aparece é a camada de app.js,
 * a partir de eventos reais do backend. */
(function () {
  "use strict";

  const COLORS = {
    cyan: "56, 189, 248",
    blue: "59, 130, 246",
    gold: "245, 199, 107",
    green: "52, 211, 153",
    red: "248, 113, 113",
    amber: "251, 191, 36",
  };

  // Como cada estado se parece na tela.
  const PROFILES = {
    standby:   { color: "cyan",  spin: 0.15, pulse: 0.04, particles: 0.6, speed: 0.4, waves: false, alpha: 0.7 },
    listening: { color: "cyan",  spin: 0.9,  pulse: 0.10, particles: 0.9, speed: 1.0, waves: true,  alpha: 1.0 },
    processing:{ color: "blue",  spin: 1.8,  pulse: 0.06, particles: 1.0, speed: 2.0, waves: false, alpha: 1.0 },
    executing: { color: "gold",  spin: 1.0,  pulse: 0.05, particles: 0.8, speed: 1.2, waves: false, alpha: 1.0, progress: true },
    speaking:  { color: "cyan",  spin: 0.6,  pulse: 0.16, particles: 0.9, speed: 0.9, waves: true,  alpha: 1.0 },
    done:      { color: "green", spin: 2.6,  pulse: 0.12, particles: 1.2, speed: 2.5, waves: false, alpha: 1.0 },
    error:     { color: "red",   spin: 0.2,  pulse: 0.02, particles: 0.4, speed: 0.3, waves: false, alpha: 0.9, flicker: true },
    cancelled: { color: "amber", spin: 0.3,  pulse: 0.03, particles: 0.5, speed: 0.5, waves: false, alpha: 0.9 },
    off:       { color: "blue",  spin: 0.05, pulse: 0.0,  particles: 0.2, speed: 0.2, waves: false, alpha: 0.35 },
  };

  class ReactorCore {
    constructor(canvas, options = {}) {
      this.canvas = canvas;
      this.ctx = canvas.getContext("2d");
      this.state = "standby";
      this.intensity = clamp(options.intensity ?? 1, 0, 1);
      this.progress = 0;
      this.reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      this.particles = [];
      this.waves = [];
      this.t0 = performance.now();
      this.last = this.t0;
      this.running = false;
      this.angle = 0;
      this.level = 0; // amplitude suavizada (0..1)
      this._resize();
      this._resizeObserver = new ResizeObserver(() => this._resize());
      this._resizeObserver.observe(canvas.parentElement);
      document.addEventListener("visibilitychange", () => { this.last = performance.now(); });
    }

    setState(state) {
      if (!PROFILES[state]) return;
      if (state !== this.state) {
        this.state = state;
        if (PROFILES[state].waves) this.waves.length = 0;
      }
    }

    setIntensity(value) { this.intensity = clamp(value, 0, 1); }

    setProgress(fraction) { this.progress = clamp(fraction, 0, 1); }

    start() {
      if (this.running) return;
      this.running = true;
      const frame = (now) => {
        if (!this.running) return;
        try {
          this._draw(now);
        } catch (err) {
          // Um erro de desenho não pode matar o laço: registra e tenta o próximo quadro.
          console.error("Falha ao desenhar o núcleo", err);
        }
        requestAnimationFrame(frame);
      };
      requestAnimationFrame(frame);
    }

    stop() { this.running = false; this._resizeObserver.disconnect(); }

    _resize() {
      const rect = this.canvas.parentElement.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const size = Math.max(180, Math.floor(Math.min(rect.width, rect.height)));
      this.size = size;
      this.canvas.width = Math.floor(size * dpr);
      this.canvas.height = Math.floor(size * dpr);
      this.canvas.style.width = size + "px";
      this.canvas.style.height = size + "px";
      this.dpr = dpr;
      this._seedParticles();
    }

    _seedParticles() {
      const count = Math.round(70 * this.intensity) + 10;
      this.particles = Array.from({ length: count }, () => ({
        a: Math.random() * Math.PI * 2,
        r: 1.25 + Math.random() * 0.7,
        s: (Math.random() * 0.6 + 0.4) * (Math.random() < 0.5 ? -1 : 1),
        size: 0.8 + Math.random() * 1.6,
      }));
    }

    _draw(now) {
      const dt = Math.min(0.05, (now - this.last) / 1000);
      this.last = now;
      const t = (now - this.t0) / 1000;
      const profile = PROFILES[this.state];
      const motion = this.reduceMotion ? 0.15 : 1;
      const k = this.intensity * motion;
      const ctx = this.ctx;
      const w = this.canvas.width, h = this.canvas.height;
      const cx = w / 2, cy = h / 2;
      const R = (Math.min(w, h) / 2) * 0.36;
      const rgb = COLORS[profile.color];

      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, w, h);
      ctx.globalCompositeOperation = "lighter";

      // Amplitude: pulsação lenta em espera, reativa em escuta/fala.
      const target = this._amplitude(t, profile);
      this.level += (target - this.level) * Math.min(1, dt * 10);

      // Brilho de fundo
      const glowR = R * (2.2 + this.level * 0.5);
      const glow = ctx.createRadialGradient(cx, cy, R * 0.2, cx, cy, glowR);
      glow.addColorStop(0, `rgba(${rgb}, ${0.22 * profile.alpha * k + 0.04})`);
      glow.addColorStop(1, `rgba(${rgb}, 0)`);
      ctx.fillStyle = glow;
      ctx.beginPath(); ctx.arc(cx, cy, glowR, 0, Math.PI * 2); ctx.fill();

      // Ondas de energia (escuta e fala)
      if (profile.waves && k > 0.05) this._drawWaves(ctx, cx, cy, R, rgb, dt, k, profile);

      // Núcleo: disco com pulsação
      const coreR = R * (0.55 + this.level * profile.pulse * 2.4);
      const core = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreR);
      core.addColorStop(0, `rgba(255, 255, 255, ${0.55 * profile.alpha * k + 0.1})`);
      core.addColorStop(0.5, `rgba(${rgb}, ${0.55 * profile.alpha * k + 0.08})`);
      core.addColorStop(1, `rgba(${rgb}, 0)`);
      ctx.fillStyle = core;
      ctx.beginPath(); ctx.arc(cx, cy, coreR, 0, Math.PI * 2); ctx.fill();

      // Anéis giratórios com segmentos
      this.angle += dt * profile.spin * profile.speed * motion;
      const rings = [
        { r: R * 0.85, w: 2.0, seg: 5, dir: 1, mult: 1.0 },
        { r: R * 1.05, w: 1.2, seg: 9, dir: -1, mult: 0.6 },
        { r: R * 1.25, w: 3.0, seg: 3, dir: 1, mult: 0.35 },
        { r: R * 1.5, w: 0.8, seg: 16, dir: -1, mult: 0.25 },
      ];
      for (const ring of rings) {
        const start = this.angle * ring.dir * ring.mult;
        const arc = (Math.PI * 2) / ring.seg;
        ctx.lineWidth = ring.w * this.dpr;
        for (let i = 0; i < ring.seg; i++) {
          ctx.strokeStyle = `rgba(${rgb}, ${(0.35 + 0.4 * ring.mult) * profile.alpha * k})`;
          ctx.beginPath();
          ctx.arc(cx, cy, ring.r, start + i * arc, start + i * arc + arc * 0.62);
          ctx.stroke();
        }
      }

      // Arco de progresso (execução de tarefa)
      if (profile.progress) {
        const fraction = this.progress || 0.15 + 0.1 * Math.sin(t * 2);
        ctx.lineWidth = 4 * this.dpr;
        ctx.strokeStyle = `rgba(${COLORS.gold}, ${0.9 * k})`;
        ctx.beginPath();
        ctx.arc(cx, cy, R * 1.7, -Math.PI / 2, -Math.PI / 2 + fraction * Math.PI * 2);
        ctx.stroke();
      }

      // Partículas em órbita
      // Perfis com particles > 1 (ex.: 'done') não podem passar do tamanho do array.
      const pCount = Math.min(this.particles.length, Math.round(this.particles.length * profile.particles));
      for (let i = 0; i < pCount; i++) {
        const p = this.particles[i];
        p.a += dt * p.s * profile.speed * motion;
        const r = R * p.r;
        const x = cx + Math.cos(p.a) * r, y = cy + Math.sin(p.a) * r * 0.9;
        ctx.fillStyle = `rgba(${rgb}, ${0.7 * profile.alpha * k})`;
        ctx.beginPath(); ctx.arc(x, y, p.size * this.dpr, 0, Math.PI * 2); ctx.fill();
      }

      // Marcas de HUD ao redor
      ctx.globalCompositeOperation = "source-over";
      ctx.strokeStyle = `rgba(${rgb}, ${0.35 * k})`;
      ctx.lineWidth = 1 * this.dpr;
      for (let i = 0; i < 48; i++) {
        const a = (i / 48) * Math.PI * 2 + this.angle * 0.05;
        const inner = R * 1.78, outer = R * (i % 4 === 0 ? 1.9 : 1.84);
        ctx.beginPath();
        ctx.moveTo(cx + Math.cos(a) * inner, cy + Math.sin(a) * inner);
        ctx.lineTo(cx + Math.cos(a) * outer, cy + Math.sin(a) * outer);
        ctx.stroke();
      }
    }

    _amplitude(t, profile) {
      if (this.state === "speaking") {
        // Sem medição de áudio do SAPI: envelope aproximado para dar sensação de fala.
        return 0.45 + 0.35 * Math.abs(Math.sin(t * 9) * Math.sin(t * 3.1 + 1)) + Math.random() * 0.1;
      }
      if (this.state === "listening") {
        return 0.35 + Math.random() * 0.5;
      }
      if (profile.flicker) return 0.4 + 0.3 * (Math.sin(t * 18) > 0 ? 1 : 0);
      return 0.45 + Math.sin(t * 1.4) * 0.25 * profile.pulse * 6 + Math.sin(t * 0.37) * 0.05;
    }

    _drawWaves(ctx, cx, cy, R, rgb, dt, k, profile) {
      if (this.waves.length < 4 && Math.random() < dt * 2.5 * profile.speed) {
        this.waves.push({ r: R * 0.9, a: 0.6 });
      }
      for (const wave of this.waves) {
        wave.r += dt * R * 1.3 * profile.speed;
        wave.a -= dt * 0.45;
        ctx.strokeStyle = `rgba(${rgb}, ${Math.max(0, wave.a) * k})`;
        ctx.lineWidth = 1.5 * this.dpr;
        ctx.beginPath(); ctx.arc(cx, cy, wave.r, 0, Math.PI * 2); ctx.stroke();
      }
      this.waves = this.waves.filter((wave) => wave.a > 0 && wave.r < R * 2.2);
    }
  }

  function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }

  window.LSCore = { ReactorCore, PROFILES };
})();
