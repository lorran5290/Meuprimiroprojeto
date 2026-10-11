import { useCallback, useState } from 'react';
import { PARAMETRO_REGIAO, encontrarRegiao, resolverRegiaoInicial, salvarRegiao } from '../lib/region';
import type { RegionId } from '../types';

function atualizarURL(id: RegionId | null): void {
  try {
    const url = new URL(window.location.href);
    if (id) url.searchParams.set(PARAMETRO_REGIAO, id);
    else url.searchParams.delete(PARAMETRO_REGIAO);
    window.history.replaceState(null, '', url);
  } catch {
    // URL não atualizável (ex.: ambiente sem History API): a seleção segue em memória.
  }
}

export function useRegiao() {
  const [regiaoId, setRegiaoId] = useState<RegionId | null>(() =>
    resolverRegiaoInicial(window.location.search),
  );

  const selecionar = useCallback((id: RegionId) => {
    setRegiaoId(id);
    salvarRegiao(id);
    atualizarURL(id);
  }, []);

  const trocar = useCallback(() => {
    setRegiaoId(null);
    salvarRegiao(null);
    atualizarURL(null);
  }, []);

  return { regiao: encontrarRegiao(regiaoId) ?? null, selecionar, trocar };
}
