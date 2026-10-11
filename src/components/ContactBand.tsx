import { Instagram, MapPin, MessageCircle } from 'lucide-react';
import { CONTATO } from '../data/site';
import { linkWhatsApp } from '../lib/whatsapp';
import type { Region } from '../types';

interface ContactBandProps {
  regiao: Region;
}

export function ContactBand({ regiao }: ContactBandProps) {
  return (
    <section
      id="contato"
      aria-labelledby="titulo-contato"
      className="scroll-mt-20 relative overflow-hidden border-t border-gold/40 bg-gradient-to-r from-navy-deep via-navy to-red/80"
    >
      <div className="mx-auto grid max-w-7xl gap-8 px-4 py-12 sm:px-6 lg:grid-cols-[1fr_auto] lg:items-center lg:py-14">
        <div>
          <h2 id="titulo-contato" className="text-2xl font-black uppercase tracking-tight sm:text-3xl">
            Fale com a filial <span className="text-gold">pelo WhatsApp</span>
          </h2>
          <a
            href={CONTATO.whatsappUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-4 block text-3xl font-black tracking-tight text-white transition hover:text-gold sm:text-5xl"
          >
            {CONTATO.telefone}
          </a>

          <ul className="mt-6 flex flex-wrap gap-x-6 gap-y-3 text-sm font-semibold">
            <li className="flex items-center gap-2 text-white/90">
              <MapPin size={18} className="text-gold" aria-hidden="true" />
              {CONTATO.cidade}
            </li>
            <li>
              <a
                href={CONTATO.instagramUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 text-white/90 transition hover:text-gold"
              >
                <Instagram size={18} className="text-gold" aria-hidden="true" />
                {CONTATO.instagramUsuario}
              </a>
            </li>
          </ul>
        </div>

        <a
          href={linkWhatsApp(`Olá! Quero contratar um plano na região ${regiao.nome}.`)}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center justify-center gap-3 rounded-xl bg-gold px-8 py-5 text-base font-black uppercase tracking-wide text-navy shadow-lg transition hover:brightness-110 motion-reduce:transition-none"
        >
          <MessageCircle size={26} aria-hidden="true" />
          Chamar no WhatsApp
        </a>
      </div>
    </section>
  );
}
