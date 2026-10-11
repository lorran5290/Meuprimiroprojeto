# ExNet Fiber — Landing page

Landing page oficial da ExNet Fiber (internet por fibra óptica, Rio de Janeiro).
Stack: React 18 + TypeScript + Vite + Tailwind CSS v4 + lucide-react.

## Rodar

```bash
npm install
npm run dev        # desenvolvimento
npm test           # testes de regras de negócio e dados
npm run build      # checagem de tipos + build de produção (dist/)
npm run preview    # serve o build
```

## Onde editar

| O que mudar | Arquivo |
| --- | --- |
| Planos, preços (normal e até o vencimento), velocidades e serviços por região | `src/data/regions.ts` |
| Catálogo de serviços (nomes e logotipos oficiais) | `src/data/services.ts` |
| Telefone, WhatsApp, Instagram, diferenciais, canais, aviso | `src/data/site.ts` |
| Valor do painel de desconto | `promocao.valor` em `src/data/regions.ts` |
| Tipos dos dados | `src/types.ts` |

Regras importantes:

- Cada região tem seus próprios planos. Não reutilize valores entre regiões.
- `maisEscolhido` só deve ser `true` quando a empresa confirmar o plano mais escolhido.
- `servicosConformeOferta` marca planos cujos serviços dependem da oferta cadastrada.
- Para exibir logotipo oficial de um serviço, coloque o arquivo em `public/assets/servicos/` e preencha `logo`. Sem arquivo, o nome aparece em texto.
- Para trocar o logo da marca, substitua `public/assets/exnet-fiber-logo.png` pelo arquivo original.

## Seleção de região

- Primeira visita: tela "Qual é a sua região?".
- A escolha fica salva no navegador e na URL (`?regiao=caju` ou `?regiao=nova-iguacu`), para que o link abra direto na região.
- "Trocar região" volta para a tela de seleção.
- Se uma região não tiver planos cadastrados, a página mostra uma mensagem e o contato comercial.
