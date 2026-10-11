import { CANAIS_AO_VIVO } from '../data/site';

export function LiveChannels() {
  return (
    <section id="canais" aria-labelledby="titulo-canais" className="scroll-mt-20 py-12 sm:py-16">
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <div className="rounded-xl border border-gold/50 bg-navy-soft/60 p-5 sm:p-8">
          <h2 id="titulo-canais" className="text-center text-sm font-black uppercase tracking-[0.18em] text-gold sm:text-base">
            Canais ao vivo em planos selecionados com Watch
          </h2>

          <ul
            aria-label="Canais disponíveis em planos selecionados"
            className="mt-6 flex snap-x snap-mandatory gap-3 overflow-x-auto pb-2 [scrollbar-color:var(--color-gold)_transparent] sm:grid sm:grid-cols-4 sm:gap-4 sm:overflow-visible lg:grid-cols-7"
          >
            {CANAIS_AO_VIVO.map((canal) => (
              <li
                key={canal.nome}
                className="flex h-20 min-w-[150px] snap-start items-center justify-center rounded-lg border border-gold/40 bg-white px-4 text-center sm:min-w-0"
              >
                <span className="text-base font-black tracking-tight text-navy">{canal.nome}</span>
              </li>
            ))}
          </ul>

          <p className="mt-5 text-center text-xs text-muted">
            Disponibilidade conforme o plano contratado e as condições vigentes.
          </p>
        </div>
      </div>
    </section>
  );
}
