# ADR-005: Atomicidade e idempotência de reservas

## Contexto

O B2C pode reservar vários SKUs em uma única operação. Se apenas parte do pedido tiver estoque, nenhuma quantidade deve ser alterada; uma repetição com o mesmo `idempotency_key` também não pode duplicar a dedução.

## Alternativas

1. **Uma transação com locks por SKU (`SELECT FOR UPDATE`):** oferece all-or-nothing e segurança sob concorrência, com implementação direta.
2. **Lock otimista com retries:** reduz bloqueios longos, mas aumenta a complexidade e ainda exige uma tabela de operações idempotentes.
3. **Commit em duas fases:** modela bem sistemas distribuídos, mas é excessivo para uma operação local de inventário.

## Decisão

Escolhemos uma transação lógica única com validação de todos os SKUs antes de qualquer mutação e registro por `idempotency_key`. A implementação de produção deve mapear essa seção para uma transação SQL com `SELECT FOR UPDATE`; o adaptador atual mantém as mesmas garantias em memória para os testes. O evento `SKU_OUT_OF_STOCK` é produzido somente após uma reserva bem-sucedida que zera o estoque.

A escolha prioriza **correção sob concorrência** e **menor complexidade operacional**, preservando o invariante `active_quantity + reserved_quantity = on_hand`.
