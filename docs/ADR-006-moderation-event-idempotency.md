# ADR-006: Idempotência na aplicação de decisões de moderação

## Contexto

O serviço B2B recebe decisões de Moderation e precisa atualizar o produto exatamente uma vez. Reentregas do mesmo evento não podem gerar um segundo cascade `PRODUCT_BLOCKED` nem alterar novamente o estado do produto.

## Alternativas

Foram consideradas uma tabela `processed_events` indexada por `idempotency_key`, um campo `last_event_key` na entidade Product e um upsert condicional baseado na chave do evento. A tabela separada oferece histórico e permite deduplicação consistente entre entidades, enquanto o campo na Product é mais simples, mas limita a rastreabilidade.

## Decisão

Escolhemos o registro separado de chaves processadas. O adaptador atual usa um conjunto em memória para representar essa tabela; em produção, ele deve ser persistido com uma restrição única sobre `idempotency_key` dentro da mesma transação da mudança de status. A decisão `MODERATED` limpa os diagnósticos de bloqueio; `BLOCKED` com `hard_block=false` salva os relatórios e usa status `BLOCKED`; `hard_block=true` usa `HARD_BLOCKED`, que é terminal para ações do vendedor. Ambos os bloqueios emitem um único evento `PRODUCT_BLOCKED` para B2C.

A escolha prioriza **segurança contra race conditions** e **suporte operacional**, mantendo a lógica de deduplicação isolada da entidade de negócio.
