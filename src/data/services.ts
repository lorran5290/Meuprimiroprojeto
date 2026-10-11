import type { Service, ServiceId } from '../types';

/**
 * Catálogo de serviços de entretenimento.
 * Para usar o logotipo oficial, coloque o arquivo em public/assets/servicos/ e preencha `logo`.
 */
export const SERVICOS: Record<ServiceId, Service> = {
  watch: { nome: 'Watch' },
  'watch-filmes': { nome: 'Watch Filmes' },
  'watch-sport': { nome: 'Watch Sport' },
  ubook: { nome: 'ubook' },
  globoplay: { nome: 'Globoplay com anúncios' },
  hbo: { nome: 'HBO' },
  telecine: { nome: 'Telecine' },
  premiere: { nome: 'Premiere' },
  sportv: { nome: 'SporTV' },
  espn: { nome: 'ESPN' },
};
