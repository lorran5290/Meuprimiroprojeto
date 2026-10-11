export type RegionId = 'caju' | 'nova-iguacu';

export type ServiceId =
  | 'watch'
  | 'watch-filmes'
  | 'watch-sport'
  | 'ubook'
  | 'globoplay'
  | 'hbo'
  | 'telecine'
  | 'premiere'
  | 'sportv'
  | 'espn';

export interface Service {
  nome: string;
  /** Caminho do logotipo oficial (ex.: /assets/servicos/espn.svg). Sem arquivo, exibe-se o nome em texto. */
  logo?: string;
}

export interface Plan {
  id: string;
  nome: string;
  velocidadeMega: number;
  valorNormal: number;
  valorAteVencimento: number;
  servicos: ServiceId[];
  /** Marque como true somente quando o cadastro comercial indicar que os serviços variam conforme a oferta. */
  servicosConformeOferta?: boolean;
  /** Marque como true somente quando a empresa confirmar o plano mais escolhido. */
  maisEscolhido?: boolean;
}

export interface Promocao {
  ativa: boolean;
  /** Valor em reais do desconto de referência, exibido no painel. */
  valor: number;
  /** Serviços exibidos no painel. Só use quando as condições valerem para os planos listados. */
  servicos: ServiceId[];
}

export interface Region {
  id: RegionId;
  nome: string;
  imagem: string;
  imagemAlt: string;
  planos: Plan[];
  promocao: Promocao;
}
