import { MessageCircle } from 'lucide-react';
import { CONTATO } from '../data/site';
import { linkWhatsApp } from '../lib/whatsapp';
import type { Region } from '../types';

interface HeroProps {
  regiao: Region;
}

export function Hero({ regiao }: HeroProps) {
  return (
    <section id="topo" aria-labelledby="titulo-hero" className="relative overflow-hidden">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_75%_40%,rgba(63,63,154,0.45),transparent_55%)]"
      />

      <div className="relative mx-auto grid max-w-7xl grid-cols-1 items-center gap-10 px-4 py-12 sm:px-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] lg:gap-14 lg:py-20">
        <div className="order-2 min-w-0 lg:order-1">
          <p className="inline-flex items-center gap-2 rounded-md border border-gold/60 bg-navy-deep/70 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-gold">
            Região selecionada: {regiao.nome}
          </p>

          <h1 id="titulo-hero" className="mt-6 text-4xl font-black leading-[1.05] tracking-tight sm:text-5xl lg:text-6xl">
            Internet que <span className="text-gold">conecta</span> o seu mundo.
          </h1>

          <p className="mt-6 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm font-bold uppercase tracking-wider sm:text-base">
            <span className="text-white">Fibra <span className="text-gold">100%</span></span>
            <span aria-hidden="true" className="h-4 w-px bg-white/30" />
            <span className="text-white">+ Atendimento <span className="text-gold">local</span></span>
          </p>

          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <a
              href="#planos"
              className="inline-flex items-center justify-center rounded-md bg-gold px-6 py-3 text-sm font-black uppercase tracking-wide text-navy transition hover:brightness-110 motion-reduce:transition-none"
            >
              Confira nossos planos
            </a>
            <a
              href={linkWhatsApp()}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-2 rounded-md border border-white/40 px-6 py-3 text-sm font-bold uppercase tracking-wide text-white transition hover:border-gold hover:text-gold"
            >
              <MessageCircle size={18} aria-hidden="true" />
              Falar com a filial
            </a>
          </div>

          <p className="mt-6 text-sm text-muted">{CONTATO.telefone} · {CONTATO.cidade}</p>
        </div>

        <div className="relative order-1 min-w-0 lg:order-2">
          <div aria-hidden="true" className="pointer-events-none absolute -inset-x-6 -inset-y-8 hidden sm:block">
            <svg viewBox="0 0 600 500" className="h-full w-full" fill="none" preserveAspectRatio="none">
              <path d="M10 430 C 160 330, 260 470, 420 360 S 560 150, 590 60" stroke="#e11d2a" strokeWidth="2" strokeLinecap="round" opacity="0.85" />
              <path d="M0 360 C 150 270, 280 420, 440 300 S 580 220, 600 170" stroke="#3f3f9a" strokeWidth="2.5" strokeLinecap="round" opacity="0.9" />
              <path d="M40 470 C 200 420, 330 480, 520 430" stroke="#f5a700" strokeWidth="1.2" strokeLinecap="round" opacity="0.6" />
            </svg>
          </div>
          <figure className="relative overflow-hidden rounded-2xl border border-gold/60 bg-navy-deep shadow-[0_20px_60px_-20px_rgba(0,0,0,0.8)]">
            <img
              src={regiao.imagem}
              alt={regiao.imagemAlt}
              width={regiao.id === 'caju' ? 504 : 643}
              height={regiao.id === 'caju' ? 700 : 470}
              fetchPriority="high"
              className="aspect-[4/5] w-full object-cover sm:aspect-[5/4] lg:aspect-[4/3]"
            />
          </figure>
        </div>
      </div>
    </section>
  );
}
