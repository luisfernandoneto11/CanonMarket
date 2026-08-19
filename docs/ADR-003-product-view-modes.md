# ADR-003: Modos de acesso ao GET de produto

## Contexto

`GET /api/v1/products/{id}` é usado pelo seller cabinet e também por chamadas inter-serviços da Moderation. O seller deve ver apenas os próprios produtos, enquanto Moderation precisa consultar qualquer produto para construir diffs. O payload seller inclui campos sensíveis como `cost_price` e `reserved_quantity`, que não devem ser expostos acidentalmente em um modo B2C.

## Alternativas

1. **Um view com `if` por header de autenticação:** concentra a lógica, mas mistura regras de segurança e aumenta o risco de vazamento de campos.
2. **Dois views diferentes:** torna os modos explícitos, porém duplica rota, serialização e manutenção.
3. **Um view com uma dependência de contexto de acesso:** mantém um único endpoint e centraliza a decisão de autenticação/ownership antes de devolver o schema seller.

## Decisão

Escolhemos um único endpoint com dependências de acesso explícitas: Bearer JWT para seller e `X-Service-Key` para Moderation. O seller que consulta produto de outro vendedor recebe `404`, ocultando a existência do recurso; Moderation pode consultar qualquer produto com a chave válida. O schema retornado é o seller payload, e um futuro endpoint B2C deverá usar um schema separado sem `cost_price` e `reserved_quantity`.

A decisão prioriza **legibilidade** e reduz o **risco de vazamento**, porque a validação de modo ocorre antes da resposta e os schemas de cada contexto podem evoluir separadamente.
