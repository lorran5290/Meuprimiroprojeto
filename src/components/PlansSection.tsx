import { MessageCircle, Tag } from 'lucide-react';
import { CONTATO } from '../data/site';
import { formatarValor, formatarReais } from '../lib/format';
import { linkWhatsApp, mensagemDoPlano } from '../lib/whatsapp';
import type { Plan, Region } from '../types';
import { ServiceBadge } from './ServiceBadge';

interface PlansSectionProps {
  regiao: Region;
}

export function PlansSection({ regiao }: PlansSectionProps) {
  return (
    <section id="planos" aria-labelledby="titulo-planos" className="scroll-mt-20 border-t border-gold/25 py-14 sm:py-20">
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-red">Região {regiao.nome}</p>
            <h2 id="titulo-planos" className="mt-2 text-3xl font-black uppercase tracking-tight sm:text-4xl">
              Planos para sua <span className="text-gold">região</span>
            </h2>
          </div>
          <p className="max-w-sm text-sm text-muted">
            Valores mensais. Os preços promocionais valem para pagamento até o vencimento.
          </p>
        </header>

        {regiao.planos.length === 0 ? (
          <RegionUnavailable regiao={regiao} />
        ) : (
          <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start">
            <div className="min-w-0">
              <PlanTable regiao={regiao} />
              <PlanCards regiao={regiao} />
            </div>
            <DiscountPanel regiao={regiao} />
          </div>
        )}
      </div>
    </section>
  );
}

function PlanTable({ regiao }: { regiao: Region }) {
  return (
    <div className="hidden overflow-hidden rounded-xl border border-gold/60 md:block">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-left">
          <caption className="sr-only">Planos de internet da região {regiao.nome}</caption>
          <thead>
            <tr className="bg-gold text-navy">
              <th scope="col" className="px-4 py-3 text-xs font-black uppercase tracking-wide">Plano</th>
              <th scope="col" className="px-4 py-3 text-xs font-black uppercase tracking-wide">Velocidade</th>
              <th scope="col" className="px-4 py-3 text-xs font-black uppercase tracking-wide">Valor normal</th>
              <th scope="col" className="px-4 py-3 text-xs font-black uppercase tracking-wide">Até o vencimento</th>
              <th scope="col" className="px-4 py-3 text-xs font-black uppercase tracking-wide">Serviços inclusos</th>
            </tr>
          </thead>
          <tbody>
            {regiao.planos.map((plano) => (
              <tr
                key={plano.id}
                className={`border-t border-gold/30 align-middle ${plano.maisEscolhido ? 'bg-gold/10' : 'bg-navy-soft/60'}`}
              >
                <th scope="row" className="px-4 py-4 align-middle">
                  <span className="block text-base font-black uppercase tracking-tight">{plano.nome}</span>
                  {plano.maisEscolhido && (
                    <span className="mt-1 inline-block rounded bg-gold px-2 py-0.5 text-[10px] font-black uppercase text-navy">
                      Mais escolhido
                    </span>
                  )}
                  <a
                    href={linkWhatsApp(mensagemDoPlano(regiao, plano))}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-3 inline-flex items-center gap-1.5 rounded-md bg-red px-3 py-1.5 text-xs font-bold uppercase tracking-wide text-white transition hover:brightness-110"
                  >
                    <MessageCircle size={14} aria-hidden="true" />
                    Quero este plano
                  </a>
                </th>
                <td className="px-4 py-4">
                  <Velocidade mega={plano.velocidadeMega} />
                </td>
                <td className="px-4 py-4">
                  <Preco valor={plano.valorNormal} />
                </td>
                <td className="px-4 py-4">
                  <Preco valor={plano.valorAteVencimento} promocional />
                </td>
                <td className="px-4 py-4">
                  <ServicosInclusos plano={plano} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PlanCards({ regiao }: { regiao: Region }) {
  return (
    <ul className="grid gap-4 md:hidden">
      {regiao.planos.map((plano) => (
        <li
          key={plano.id}
          className={`rounded-xl border p-5 ${plano.maisEscolhido ? 'border-gold bg-gold/10' : 'border-gold/50 bg-navy-soft/60'}`}
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-lg font-black uppercase tracking-tight">{plano.nome}</h3>
              <Velocidade mega={plano.velocidadeMega} />
            </div>
            {plano.maisEscolhido && (
              <span className="rounded bg-gold px-2 py-0.5 text-[10px] font-black uppercase text-navy">Mais escolhido</span>
            )}
          </div>

          <dl className="mt-4 grid grid-cols-2 gap-3">
            <div className="rounded-lg border border-white/15 p-3">
              <dt className="text-[11px] font-bold uppercase tracking-wide text-muted">Valor normal</dt>
              <dd className="mt-1"><Preco valor={plano.valorNormal} /></dd>
            </div>
            <div className="rounded-lg border border-gold/60 p-3">
              <dt className="text-[11px] font-bold uppercase tracking-wide text-gold">Até o vencimento</dt>
              <dd className="mt-1"><Preco valor={plano.valorAteVencimento} promocional /></dd>
            </div>
          </dl>

          <div className="mt-4">
            <p className="text-[11px] font-bold uppercase tracking-wide text-muted">Serviços inclusos</p>
            <div className="mt-2"><ServicosInclusos plano={plano} /></div>
          </div>

          <a
            href={linkWhatsApp(mensagemDoPlano(regiao, plano))}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-5 flex w-full items-center justify-center gap-2 rounded-md bg-red px-4 py-3 text-sm font-bold uppercase tracking-wide text-white transition hover:brightness-110"
          >
            <MessageCircle size={16} aria-hidden="true" />
            Quero este plano
          </a>
        </li>
      ))}
    </ul>
  );
}

function Velocidade({ mega }: { mega: number }) {
  return (
    <p className="text-sm font-bold text-white">
      <span className="text-2xl font-black text-gold">{mega}</span>{' '}
      <span className="text-xs uppercase tracking-wide text-muted">Mega</span>
    </p>
  );
}

function Preco({ valor, promocional = false }: { valor: number; promocional?: boolean }) {
  const [inteiro, centavos] = formatarValor(valor).split(',');
  return (
    <p className={`whitespace-nowrap font-bold ${promocional ? 'text-gold' : 'text-white'}`}>
      <span className="text-xs font-semibold uppercase">R$</span>{' '}
      <span className={`font-black ${promocional ? 'text-2xl sm:text-3xl' : 'text-xl sm:text-2xl'}`}>{inteiro}</span>
      <span className="text-sm font-bold">,{centavos}</span>
      <span className="text-xs font-medium text-muted">/mês</span>
    </p>
  );
}

function ServicosInclusos({ plano }: { plano: Plan }) {
  if (plano.servicos.length === 0) {
    return <p className="text-sm text-muted">Consulte os serviços incluídos.</p>;
  }
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-1.5">
        {plano.servicos.map((servico) => (
          <ServiceBadge key={servico} id={servico} tamanho="sm" />
        ))}
      </div>
      {plano.servicosConformeOferta && (
        <p className="text-[11px] text-muted">Conforme a oferta cadastrada.</p>
      )}
    </div>
  );
}

function DiscountPanel({ regiao }: { regiao: Region }) {
  const { promocao } = regiao;
  if (!promocao.ativa) return null;

  return (
    <aside
      aria-labelledby="titulo-desconto"
      className="relative overflow-hidden rounded-xl border-2 border-gold bg-navy-deep p-6 shadow-[0_0_0_4px_rgba(10,15,35,1)]"
    >
      <span aria-hidden="true" className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-red via-gold to-indigo" />
      <div className="flex items-center gap-3">
        <span className="flex h-12 w-12 items-center justify-center rounded-lg bg-gold text-navy">
          <Tag size={24} aria-hidden="true" />
        </span>
        <p id="titulo-desconto" className="text-4xl font-black leading-none tracking-tight">
          <span className="text-sm font-bold text-muted">R$</span>{' '}
          <span className="text-gold">{formatarValor(promocao.valor)}</span>
        </p>
      </div>
      <p className="mt-3 text-lg font-black uppercase tracking-wide">de desconto</p>
      <span className="mt-3 inline-block rounded bg-red px-3 py-1 text-xs font-bold uppercase tracking-wide text-white">
        Pagando até o vencimento
      </span>

      <p className="mt-5 text-sm text-muted">Planos selecionados com:</p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {promocao.servicos.map((servico) => (
          <ServiceBadge key={servico} id={servico} tamanho="sm" />
        ))}
      </div>
      <p className="mt-4 text-sm text-muted">e conteúdos de entretenimento.</p>

      <a
        href={linkWhatsApp(`Olá! Quero saber mais sobre o desconto de ${formatarReais(promocao.valor)} na região ${regiao.nome}.`)}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-6 flex w-full items-center justify-center gap-2 rounded-md border border-gold px-4 py-3 text-sm font-bold uppercase tracking-wide text-gold transition hover:bg-gold hover:text-navy"
      >
        <MessageCircle size={16} aria-hidden="true" />
        Consultar condições
      </a>
    </aside>
  );
}

function RegionUnavailable({ regiao }: { regiao: Region }) {
  return (
    <div role="status" className="mt-8 rounded-xl border border-gold/60 bg-navy-soft p-6 sm:p-8">
      <h3 className="text-xl font-black uppercase tracking-tight">Planos indisponíveis para {regiao.nome}</h3>
      <p className="mt-2 max-w-2xl text-sm text-muted">
        Não há planos cadastrados para esta região no momento. Fale com a filial comercial para consultar a disponibilidade do seu endereço.
      </p>
      <a
        href={linkWhatsApp(`Olá! Quero consultar planos na região ${regiao.nome}.`)}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-5 inline-flex items-center gap-2 rounded-md bg-red px-5 py-3 text-sm font-bold uppercase tracking-wide text-white transition hover:brightness-110"
      >
        <MessageCircle size={16} aria-hidden="true" />
        Falar com a filial · {CONTATO.telefone}
      </a>
    </div>
  );
}
