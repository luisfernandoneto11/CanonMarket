# ADR-011: Cancellation and asynchronous unreserve retry

## Contexto

A cancelamento de pedido deve libertar o stock reservado. Nesta iteração, apenas pedidos em `CREATED` ou `PAID` podem ser cancelados; pedidos em `ASSEMBLING`, `DELIVERING`, `DELIVERED`, `CANCELLED` ou `CANCEL_PENDING` devolvem `409 CANCEL_NOT_ALLOWED`. Se o B2B não responder ou o `unreserve` falhar, a intenção do comprador é aceite imediatamente e o pedido passa para `CANCEL_PENDING`, evitando que o cliente fique dependente da disponibilidade momentânea do B2B.

## Alternativas

Foram consideradas uma task Celery com exponential backoff, um management command executado por cron/Task Scheduler e Django Q. Celery fornece retries e observabilidade robustos, mas exige broker, worker e configuração adicional; Django Q também acrescenta infraestrutura e acoplamento ao framework. O cron/Task Scheduler é mais simples de configurar e, se o scheduler for persistente, volta a executar após o reinício do serviço.

## Decisão

O MVP implementa `ProductStore.retry_pending_cancellations()` como scaffold executável por um job externo. A rota de cancelamento regista a falha e deixa o pedido em `CANCEL_PENDING`; o job tenta novamente o `unreserve` e altera o estado para `CANCELLED` apenas depois de sucesso. Em produção, a mesma função deve ser chamada por um management command agendado no Windows Task Scheduler ou cron em Linux, com backoff e logs; a persistência do pedido e dos itens é obrigatória para garantir a retomada após reinício.

## Consequências

O comprador recebe uma resposta bem-sucedida mesmo quando o B2B está temporariamente indisponível, sem libertar stock de forma incorreta. A implementação atual não cria um worker residente nem uma fila durável, portanto a garantia de execução após reinício depende do agendador externo na próxima etapa de infraestrutura. A proteção IDOR usa exclusivamente `sub`/`user_id` do JWT e devolve `404 ORDER_NOT_FOUND` para pedidos de outro utilizador.
