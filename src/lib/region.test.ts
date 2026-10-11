import { describe, expect, it } from 'vitest';
import { CHAVE_REGIAO, lerRegiaoSalva, resolverRegiaoInicial, salvarRegiao } from './region';

function armazenamentoFalso(inicial: Record<string, string> = {}) {
  const dados = new Map(Object.entries(inicial));
  return {
    getItem: (chave: string) => dados.get(chave) ?? null,
    setItem: (chave: string, valor: string) => void dados.set(chave, valor),
    removeItem: (chave: string) => void dados.delete(chave),
  };
}

describe('resolverRegiaoInicial', () => {
  it('retorna null quando não há região na URL nem salva', () => {
    expect(resolverRegiaoInicial('', armazenamentoFalso())).toBeNull();
  });

  it('prioriza o parâmetro ?regiao= da URL', () => {
    const armazenamento = armazenamentoFalso({ [CHAVE_REGIAO]: 'caju' });
    expect(resolverRegiaoInicial('?regiao=nova-iguacu', armazenamento)).toBe('nova-iguacu');
  });

  it('usa a região salva quando a URL não traz uma válida', () => {
    const armazenamento = armazenamentoFalso({ [CHAVE_REGIAO]: 'caju' });
    expect(resolverRegiaoInicial('?regiao=inexistente', armazenamento)).toBe('caju');
  });

  it('ignora valores salvos que não correspondem a uma região cadastrada', () => {
    expect(resolverRegiaoInicial('', armazenamentoFalso({ [CHAVE_REGIAO]: 'zona-sul' }))).toBeNull();
  });
});

describe('persistência da região', () => {
  it('salva e remove a região', () => {
    const armazenamento = armazenamentoFalso();
    salvarRegiao('caju', armazenamento);
    expect(lerRegiaoSalva(armazenamento)).toBe('caju');
    salvarRegiao(null, armazenamento);
    expect(lerRegiaoSalva(armazenamento)).toBeNull();
  });

  it('não lança erro quando o armazenamento falha', () => {
    const bloqueado = {
      getItem: () => {
        throw new Error('bloqueado');
      },
      setItem: () => {
        throw new Error('bloqueado');
      },
      removeItem: () => {
        throw new Error('bloqueado');
      },
    };
    expect(lerRegiaoSalva(bloqueado)).toBeNull();
    expect(() => salvarRegiao('caju', bloqueado)).not.toThrow();
  });
});
