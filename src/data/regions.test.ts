import { describe, expect, it } from 'vitest';
import { REGIOES } from './regions';
import { SERVICOS } from './services';

describe('dados das regiões', () => {
  it('cadastra Caju e Nova Iguaçu com identificadores únicos', () => {
    const ids = REGIOES.map((regiao) => regiao.id);
    expect(ids).toEqual(['caju', 'nova-iguacu']);
  });

  it('mantém os valores de Caju conforme o briefing', () => {
    const caju = REGIOES.find((regiao) => regiao.id === 'caju');
    expect(caju?.planos.map((plano) => [plano.velocidadeMega, plano.valorNormal, plano.valorAteVencimento])).toEqual([
      [400, 109.99, 99.99],
      [500, 119.99, 109.99],
      [600, 139.99, 129.99],
      [700, 179.99, 169.99],
      [800, 189.99, 179.99],
    ]);
  });

  it('mantém os valores de Nova Iguaçu conforme o briefing', () => {
    const nova = REGIOES.find((regiao) => regiao.id === 'nova-iguacu');
    expect(nova?.planos.map((plano) => [plano.velocidadeMega, plano.valorNormal, plano.valorAteVencimento])).toEqual([
      [300, 89.99, 79.99],
      [400, 109.99, 99.99],
      [500, 119.99, 109.99],
      [600, 139.99, 129.99],
      [700, 169.99, 159.99],
    ]);
  });

  it('garante que o valor promocional nunca supera o valor normal e que os IDs dos planos são únicos', () => {
    const todosIds = REGIOES.flatMap((regiao) => regiao.planos.map((plano) => plano.id));
    expect(new Set(todosIds).size).toBe(todosIds.length);
    for (const regiao of REGIOES) {
      for (const plano of regiao.planos) {
        expect(plano.valorAteVencimento).toBeLessThanOrEqual(plano.valorNormal);
      }
    }
  });

  it('usa apenas serviços cadastrados no catálogo', () => {
    for (const regiao of REGIOES) {
      for (const plano of regiao.planos) {
        for (const servico of plano.servicos) {
          expect(SERVICOS[servico]).toBeDefined();
        }
      }
    }
  });

  it('não marca nenhum plano como mais escolhido sem confirmação', () => {
    for (const regiao of REGIOES) {
      expect(regiao.planos.some((plano) => plano.maisEscolhido)).toBe(false);
    }
  });
});
