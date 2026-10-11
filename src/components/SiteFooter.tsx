import { CONTATO, AVISO_DISPONIBILIDADE } from '../data/site';
import type { Region } from '../types';
import { Logo } from './Logo';

interface SiteFooterProps {
  regiao: Region;
  onTrocarRegiao: () => void;
}

export function SiteFooter({ regiao, onTrocarRegiao }: SiteFooterProps) {
  return (
    <footer className="bg-navy-deep py-8">
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 sm:px-6 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-4">
          <div className="w-24 shrink-0">
            <Logo />
          </div>
          <div className="text-sm">
            <p className="font-bold uppercase tracking-wide">
              Região: <span className="text-gold">{regiao.nome}</span>
            </p>
            <button
              type="button"
              onClick={onTrocarRegiao}
              className="mt-1 text-xs font-semibold text-muted underline-offset-4 hover:text-gold hover:underline"
            >
              Trocar região
            </button>
          </div>
        </div>

        <nav aria-label="Links do rodapé" className="flex flex-wrap gap-x-6 gap-y-2 text-sm font-semibold">
          <a href="#planos" className="text-white/85 hover:text-gold">Consultar planos</a>
          <a href="#contato" className="text-white/85 hover:text-gold">Contato</a>
          <a
            href={CONTATO.instagramUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-white/85 hover:text-gold"
          >
            Instagram {CONTATO.instagramUsuario}
          </a>
        </nav>
      </div>

      <p className="mx-auto mt-6 max-w-7xl px-4 text-xs text-muted sm:px-6">
        *{AVISO_DISPONIBILIDADE}
      </p>
    </footer>
  );
}
