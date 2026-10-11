import { REGIOES } from '../data/regions';
import type { Region, RegionId } from '../types';

export const CHAVE_REGIAO = 'exnet-fiber:regiao';
export const PARAMETRO_REGIAO = 'regiao';

type ArmazenamentoLeitura = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

export function encontrarRegiao(id: string | null | undefined): Region | undefined {
  return REGIOES.find((regiao) => regiao.id === id);
}

/** Lê a região salva. Retorna null se o navegador bloquear o armazenamento. */
export function lerRegiaoSalva(armazenamento: ArmazenamentoLeitura | undefined = obterLocalStorage()): string | null {
  try {
    return armazenamento?.getItem(CHAVE_REGIAO) ?? null;
  } catch {
    return null;
  }
}

export function salvarRegiao(id: RegionId | null, armazenamento: ArmazenamentoLeitura | undefined = obterLocalStorage()): void {
  try {
    if (id) armazenamento?.setItem(CHAVE_REGIAO, id);
    else armazenamento?.removeItem(CHAVE_REGIAO);
  } catch {
    // Armazenamento indisponível: a seleção continua válida apenas nesta navegação.
  }
}

/** Prioridade: parâmetro ?regiao= na URL, depois a região salva. */
export function resolverRegiaoInicial(
  busca: string,
  armazenamento: ArmazenamentoLeitura | undefined = obterLocalStorage(),
): RegionId | null {
  const candidatos = [new URLSearchParams(busca).get(PARAMETRO_REGIAO), lerRegiaoSalva(armazenamento)];
  for (const candidato of candidatos) {
    const regiao = encontrarRegiao(candidato);
    if (regiao) return regiao.id;
  }
  return null;
}

function obterLocalStorage(): ArmazenamentoLeitura | undefined {
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
}
