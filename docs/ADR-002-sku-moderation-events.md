# ADR-002: Entrega do evento CREATED à Moderation

## Contexto

O primeiro SKU de um produto em estado `CREATED` deve mudar o produto para `ON_MODERATION` e enviar um evento `CREATED` para Moderation com `X-Service-Key` e `idempotency_key`.

## Alternativas

1. **POST síncrono no handler:** simples para a primeira iteração e permite detectar imediatamente uma falha da Moderation, mas aumenta a latência e pode falhar a criação do SKU se o serviço remoto estiver indisponível.
2. **Outbox pattern:** grava o evento junto com a alteração do produto e permite reenvio confiável, mas exige armazenamento persistente, worker e mais infraestrutura.
3. **Fire-and-forget:** mantém o endpoint rápido, porém pode perder o evento e dificulta confirmar a entrega.

## Decisão

Escolhemos o **POST síncrono** na primeira iteração. O serviço registra o evento, envia-o para `{MODERATION_URL}/api/v1/events/product` quando `MODERATION_URL` está configurada e inclui o cabeçalho `X-Service-Key`. A escolha minimiza a complexidade inicial e torna a indisponibilidade da Moderation observável imediatamente; numa versão com alta exigência de resiliência, a evolução natural será o outbox pattern.

O `idempotency_key` é sempre gerado por evento e o segundo SKU não muda o status nem envia um novo evento, conforme o cenário exigido nesta tarefa.
