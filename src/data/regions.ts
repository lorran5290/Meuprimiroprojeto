import type { Region } from '../types';

/**
 * Planos por região. Cada região tem seus próprios valores: não misture dados entre elas.
 * Valores em reais, mensais. Para alterar um preço, edite apenas este arquivo.
 */
export const REGIOES: Region[] = [
  {
    id: 'caju',
    nome: 'Caju',
    imagem: '/assets/hero-caju.jpg',
    imagemAlt: 'Técnico de internet instalando fibra óptica em uma rua residencial do Rio de Janeiro',
    planos: [
      {
        id: 'caju-basico',
        nome: 'Plano Básico',
        velocidadeMega: 400,
        valorNormal: 109.99,
        valorAteVencimento: 99.99,
        servicos: ['ubook', 'watch'],
      },
      {
        id: 'caju-bronze',
        nome: 'Plano Bronze',
        velocidadeMega: 500,
        valorNormal: 119.99,
        valorAteVencimento: 109.99,
        servicos: ['ubook', 'watch'],
      },
      {
        id: 'caju-prata',
        nome: 'Plano Prata',
        velocidadeMega: 600,
        valorNormal: 139.99,
        valorAteVencimento: 129.99,
        servicos: ['globoplay', 'ubook', 'watch'],
      },
      {
        id: 'caju-ouro',
        nome: 'Plano Ouro',
        velocidadeMega: 700,
        valorNormal: 179.99,
        valorAteVencimento: 169.99,
        servicos: ['globoplay', 'ubook', 'watch', 'hbo'],
        servicosConformeOferta: true,
      },
      {
        id: 'caju-platina',
        nome: 'Plano Platina',
        velocidadeMega: 800,
        valorNormal: 189.99,
        valorAteVencimento: 179.99,
        servicos: ['globoplay', 'ubook', 'watch', 'telecine', 'premiere', 'sportv', 'espn'],
        servicosConformeOferta: true,
      },
    ],
    promocao: {
      ativa: true,
      valor: 9.99,
      servicos: ['watch', 'globoplay', 'ubook'],
    },
  },
  {
    id: 'nova-iguacu',
    nome: 'Nova Iguaçu',
    imagem: '/assets/hero-nova-iguacu.jpg',
    imagemAlt: 'Família brasileira usando notebook, tablet e smartphone em casa',
    planos: [
      {
        id: 'ni-essencial',
        nome: 'Plano Essencial',
        velocidadeMega: 300,
        valorNormal: 89.99,
        valorAteVencimento: 79.99,
        servicos: ['watch', 'ubook'],
      },
      {
        id: 'ni-bronze',
        nome: 'Plano Bronze',
        velocidadeMega: 400,
        valorNormal: 109.99,
        valorAteVencimento: 99.99,
        servicos: ['watch', 'globoplay', 'ubook'],
      },
      {
        id: 'ni-prata',
        nome: 'Plano Prata',
        velocidadeMega: 500,
        valorNormal: 119.99,
        valorAteVencimento: 109.99,
        servicos: ['ubook', 'watch', 'watch-filmes', 'hbo', 'telecine'],
        servicosConformeOferta: true,
      },
      {
        id: 'ni-ouro',
        nome: 'Plano Ouro',
        velocidadeMega: 600,
        valorNormal: 139.99,
        valorAteVencimento: 129.99,
        servicos: ['ubook', 'watch', 'watch-sport', 'telecine', 'premiere'],
        servicosConformeOferta: true,
      },
      {
        id: 'ni-platina',
        nome: 'Plano Platina',
        velocidadeMega: 700,
        valorNormal: 169.99,
        valorAteVencimento: 159.99,
        servicos: ['ubook', 'watch', 'globoplay', 'watch-sport', 'premiere', 'sportv', 'espn'],
        servicosConformeOferta: true,
      },
    ],
    promocao: {
      ativa: true,
      valor: 9.99,
      servicos: ['watch', 'globoplay', 'ubook'],
    },
  },
];
