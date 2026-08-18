# ADR-004: Modo de catálogo B2C

## Contexto

O B2C precisa consultar produtos de qualquer vendedor, mas somente os produtos visíveis e em estoque. O payload público não pode conter `cost_price` nem `reserved_quantity`, que pertencem ao seller cabinet.

## Alternativas

1. **Dois URLs separados:** separa claramente os contratos, mas duplica rotas e pode criar divergência de filtros.
2. **Um URL com lógica por header:** preserva o endpoint canónico e permite identificar o cliente por `X-Service-Key`, mas exige uma separação rigorosa dos schemas.
3. **Dois views com router comum:** oferece isolamento de código, porém acrescenta estrutura para apenas dois modos.

## Decisão

Escolhemos um único URL `GET /api/v1/products` com autorização obrigatória por `X-Service-Key` e um schema público dedicado. O catálogo inclui somente produtos `MODERATED`, não deletados e com pelo menos um SKU com `active_quantity > 0`; no modo batch, IDs invisíveis são simplesmente omitidos. A resposta pública nunca serializa `cost_price` ou `reserved_quantity`.

A decisão reduz o risco de vazamento porque o modelo B2C não possui os campos sensíveis e facilita a adição de novos filtros de catálogo sem duplicar a rota. Bearer JWT não é aceito neste modo.
