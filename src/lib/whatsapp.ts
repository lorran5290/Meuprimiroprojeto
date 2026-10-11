import { CONTATO } from '../data/site';
import type { Plan, Region } from '../types';

/** Link do WhatsApp comercial. Sem mensagem, abre a conversa com o número informado. */
export function linkWhatsApp(mensagem?: string): string {
  if (!mensagem) return CONTATO.whatsappUrl;
  return `${CONTATO.whatsappUrl}?text=${encodeURIComponent(mensagem)}`;
}

export function mensagemDoPlano(regiao: Region, plano: Plan): string {
  return `Olá! Tenho interesse no ${plano.nome} (${plano.velocidadeMega} Mega) da região ${regiao.nome}.`;
}
