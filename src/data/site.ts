import type { ServiceId } from '../types';

/** Dados oficiais de contato. Não adicione outros telefones ou perfis sem confirmação da empresa. */
export const CONTATO = {
  telefone: '(21) 2042-3744',
  whatsappUrl: 'https://wa.me/552120423744',
  instagramUsuario: '@exnet_fiber',
  instagramUrl: 'https://www.instagram.com/exnet_fiber/',
  cidade: 'Rio de Janeiro – RJ',
} as const;

export const DIFERENCIAIS = [
  { id: 'fibra', titulo: 'Fibra óptica', texto: 'Mais velocidade e estabilidade.', icone: 'cable' },
  { id: 'wifi', titulo: 'Wi-Fi', texto: 'Conexão para sua casa.', icone: 'wifi' },
  { id: 'atendimento', titulo: 'Atendimento local', texto: 'Suporte rápido e humanizado.', icone: 'headset' },
  { id: 'entretenimento', titulo: 'Entretenimento', texto: 'Mais conteúdo para você.', icone: 'clapperboard' },
] as const;

/** Canais ao vivo exibidos apenas em planos com Watch. A disponibilidade depende do plano e das condições vigentes. */
export const CANAIS_AO_VIVO: { nome: string; servico?: ServiceId }[] = [
  { nome: 'ESPN', servico: 'espn' },
  { nome: 'Premiere', servico: 'premiere' },
  { nome: 'SporTV', servico: 'sportv' },
  { nome: 'TNT' },
  { nome: 'Telecine', servico: 'telecine' },
  { nome: 'Warner Bros.' },
  { nome: 'Discovery' },
];

export const AVISO_DISPONIBILIDADE = 'Consulte disponibilidade e condições para o seu endereço.';
