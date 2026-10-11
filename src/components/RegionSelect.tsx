import { ChevronRight, MapPin, MessageCircle } from 'lucide-react';
import { REGIOES } from '../data/regions';
import { CONTATO } from '../data/site';
import type { RegionId } from '../types';
import { Logo } from './Logo';

interface RegionSelectProps {
  onSelecionar: (id: RegionId) => void;
}

export function RegionSelect({ onSelecionar }: RegionSelectProps) {
  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-4 py-12">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(63,63,154,0.35),transparent_45%),radial-gradient(circle_at_85%_80%,rgba(225,29,42,0.22),transparent_40%)]"
      />
      <div className="relative z-10 flex w-full max-w-3xl flex-col items-center text-center">
        <div className="w-44 sm:w-56">
          <Logo />
        </div>

        <h1 className="mt-10 text-3xl font-black uppercase tracking-tight sm:text-4xl">Qual é a sua região?</h1>
        <p className="mt-3 max-w-xl text-base text-muted">
          Selecione sua região para consultar os planos disponíveis para o seu endereço.
        </p>

        <div className="mt-10 grid w-full gap-5 sm:grid-cols-2">
          {REGIOES.map((regiao) => (
            <button
              key={regiao.id}
              type="button"
              onClick={() => onSelecionar(regiao.id)}
              className="group relative flex flex-col items-start overflow-hidden rounded-2xl border border-gold/70 bg-navy-soft p-7 text-left shadow-[0_0_0_1px_rgba(225,29,42,0.25)] transition duration-300 ease-out hover:scale-[1.02] hover:border-gold hover:brightness-110 motion-reduce:transition-none motion-reduce:hover:scale-100"
            >
              <span aria-hidden="true" className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-red via-gold to-indigo" />
              <span className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-gold">
                <MapPin size={16} aria-hidden="true" />
                Região
              </span>
              <span className="mt-3 text-3xl font-black uppercase tracking-tight">{regiao.nome}</span>
              <span className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-white/80 group-hover:text-gold">
                Ver planos e preços
                <ChevronRight size={16} aria-hidden="true" />
              </span>
            </button>
          ))}
        </div>

        <p className="mt-10 text-sm text-muted">
          Não encontrou sua região?{' '}
          <a
            href={CONTATO.whatsappUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 font-semibold text-gold underline-offset-4 hover:underline"
          >
            <MessageCircle size={14} aria-hidden="true" />
            Fale com a filial pelo WhatsApp
          </a>
        </p>
      </div>
    </div>
  );
}
