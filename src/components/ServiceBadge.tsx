import { SERVICOS } from '../data/services';
import type { ServiceId } from '../types';

interface ServiceBadgeProps {
  id: ServiceId;
  tamanho?: 'sm' | 'md';
}

/** Mostra o logotipo oficial quando cadastrado; caso contrário, o nome do serviço em texto. */
export function ServiceBadge({ id, tamanho = 'md' }: ServiceBadgeProps) {
  const servico = SERVICOS[id];
  const estilo = tamanho === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs';

  if (servico.logo) {
    return <img src={servico.logo} alt={servico.nome} className="h-6 w-auto max-w-[96px] object-contain" />;
  }

  return (
    <span
      className={`inline-flex items-center whitespace-nowrap rounded-md border border-gold/60 bg-navy-deep font-semibold tracking-tight text-white ${estilo}`}
    >
      {servico.nome}
    </span>
  );
}
