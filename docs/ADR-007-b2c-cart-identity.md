# ADR-007: Identidade e merge da cesta B2C

## Contexto

A cesta deve funcionar para visitantes e compradores autenticados, sem aceitar `user_id` enviado pelo cliente. Os preços e a disponibilidade não são persistidos na cesta; são recalculados a cada leitura a partir dos dados atuais do B2B.

## Alternativas para identificar visitantes

Foram consideradas a identificação por `X-Session-Id`, cookie HTTP e um JWT temporário. O header `X-Session-Id` foi escolhido porque funciona de forma consistente em web e clientes móveis e torna explícita a fronteira da sessão. O identificador deve ser um UUID opaco; a proteção contra falsificação depende de sua imprevisibilidade, enquanto usuários autenticados são sempre identificados exclusivamente pelo claim `sub` do JWT.

## Decisão

A cesta armazena apenas `sku_id`, quantidade e identidade do proprietário. O endpoint GET enriquece cada item com o estado atual do B2B, calculando `unavailable_reason` sem persistir esse campo. No login, a cesta de visitante é mesclada com a cesta autenticada: itens conflitantes usam `MAX(guest_quantity, authenticated_quantity)`; itens exclusivos são transferidos para o usuário. Nenhuma reserva de inventário ocorre ao adicionar ou visualizar itens; a reserva permanece responsabilidade do checkout.
