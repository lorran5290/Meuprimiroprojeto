import { MessageCircle, RefreshCcw } from 'lucide-react';
import { CONTATO } from '../data/site';
import type { Region } from '../types';
import { Logo } from './Logo';

interface SiteHeaderProps {
  regiao: Region;
  onTrocarRegiao: () => void;
}

const LINKS = [
  { href: '#planos', rotulo: 'Planos' },
  { href: '#diferenciais', rotulo: 'Diferenciais' },
  { href: '#canais', rotulo: 'Canais' },
  { href: '#contato', rotulo: 'Contato' },
] as const;

export function SiteHeader({ regiao, onTrocarRegiao }: SiteHeaderProps) {
  return (
    <header className="sticky top-0 z-40 border-b border-gold/30 bg-navy/95 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <a href="#topo" aria-label="ExNet Fiber, início" className="w-28 shrink-0 sm:w-32">
          <Logo />
        </a>

        <nav aria-label="Seções da página" className="hidden items-center gap-6 md:flex">
          {LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="text-sm font-semibold uppercase tracking-wide text-white/85 transition hover:text-gold"
            >
              {link.rotulo}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <span className="hidden rounded-full border border-gold/60 px-3 py-1 text-xs font-bold uppercase tracking-wider text-gold sm:inline-block">
            {regiao.nome}
          </span>
          <button
            type="button"
            onClick={onTrocarRegiao}
            className="inline-flex items-center gap-1.5 rounded-md border border-white/25 px-3 py-2 text-xs font-semibold text-white transition hover:border-gold hover:text-gold"
          >
            <RefreshCcw size={14} aria-hidden="true" />
            <span className="hidden sm:inline">Trocar região</span>
            <span className="sr-only sm:hidden">Trocar região</span>
          </button>
          <a
            href={CONTATO.whatsappUrl}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Falar com a filial pelo WhatsApp"
            className="inline-flex h-9 w-9 items-center justify-center rounded-md bg-red text-white transition hover:brightness-110"
          >
            <MessageCircle size={18} aria-hidden="true" />
          </a>
        </div>
      </div>
    </header>
  );
}
