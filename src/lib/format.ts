const formatadorValor = new Intl.NumberFormat('pt-BR', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Ex.: 79.99 -> "79,99" */
export function formatarValor(valor: number): string {
  return formatadorValor.format(valor);
}

/** Ex.: 79.99 -> "R$ 79,99" */
export function formatarReais(valor: number): string {
  return `R$ ${formatarValor(valor)}`;
}
