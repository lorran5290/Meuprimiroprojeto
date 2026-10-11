import { Cable, Clapperboard, Headset, Wifi, type LucideIcon } from 'lucide-react';
import { DIFERENCIAIS } from '../data/site';

const ICONES: Record<(typeof DIFERENCIAIS)[number]['icone'], LucideIcon> = {
  cable: Cable,
  wifi: Wifi,
  headset: Headset,
  clapperboard: Clapperboard,
};

const CORES = ['text-red', 'text-gold', 'text-indigo', 'text-gold'] as const;

export function Differentials() {
  return (
    <section
      id="diferenciais"
      aria-labelledby="titulo-diferenciais"
      className="scroll-mt-20 border-y border-gold/40 bg-navy-deep/80"
    >
      <h2 id="titulo-diferenciais" className="sr-only">
        Diferenciais da ExNet Fiber
      </h2>
      <ul className="mx-auto grid max-w-7xl grid-cols-2 gap-y-8 px-4 py-10 sm:px-6 lg:grid-cols-4 lg:gap-y-0 lg:py-12">
        {DIFERENCIAIS.map((item, indice) => {
          const Icone = ICONES[item.icone];
          return (
            <li
              key={item.id}
              className={`flex flex-col gap-3 px-3 sm:flex-row sm:items-center sm:gap-4 lg:px-8 ${
                indice > 0 ? 'lg:border-l lg:border-gold/30' : ''
              }`}
            >
              <span className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full border border-current/40 ${CORES[indice]}`}>
                <Icone size={24} strokeWidth={1.75} aria-hidden="true" />
              </span>
              <div>
                <p className="text-sm font-black uppercase tracking-wide sm:text-base">{item.titulo}</p>
                <p className="mt-1 text-sm text-muted">{item.texto}</p>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
