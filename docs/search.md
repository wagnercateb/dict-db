# Pesquisa de metadados (regex)

A caixa **"Pesquisar metadados..."** do topo (`/search/?q=...`) faz uma busca
por **expressão regular**, sem diferenciar maiúsculas de minúsculas
(*case-insensitive*).

## Como funciona

1. A consulta é dividida em *tokens* separados por espaços.
2. Cada token é interpretado como uma expressão regular (`re` do Python).
3. Todos os tokens precisam casar (**AND**), **em qualquer ordem**.
4. Em cada modelo, o token pode casar em qualquer um dos campos pesquisados
   (**OR**):
   - **Tabelas/Views**: `name`, `schema`, `type`
   - **Campos**: `name`, `data_type`
   - **Comentários**: `comment`
5. A busca usa o lookup `__iregex` do Django, que no SQLite é implementado via
   `re.search` com `re.IGNORECASE`.

Tokens que **não** são expressões regulares válidas (por exemplo `([a`) caem
automaticamente para busca literal (`re.escape`), sem quebrar a página.

## Exemplos

| Consulta          | Casa com                              | Por quê                                   |
|-------------------|---------------------------------------|-------------------------------------------|
| `indi pp li._`    | `LIM_Indicador_PPA`                   | `li._` casa `lim_`, `indi` e `pp` em qualquer ordem |
| `indicador ppa`   | `LIM_Indicador_PPA`                   | tokens literais em qualquer ordem         |
| `Limites[0-9]`    | comentários contendo `Limites2`       | classe de caracteres                      |
| `\n{1}`           | comentários com quebra de linha       | quantificador                              |

Observação: os textos de comentários deste banco usam fim de linha do Windows
(`\r\n`). Para casar várias quebras de linha use, por exemplo,
`(?:\r\n){5}` — `\n{5}` não casa porque existe um `\r` entre os `\n`.

## Destaque dos resultados

O filtro de template `highlight` (`metadata_crawler/templatetags/highlight.py`)
usa exatamente os mesmos tokens como regex case-insensitive, de modo que o que
aparece destacado na lista de resultados corresponde ao que a busca casou.

## Limitação conhecida

Como a consulta é dividida por espaços (para permitir os termos "em qualquer
ordem"), uma expressão regular que contenha um espaço literal é partida em
tokens separados — por exemplo `a{1, 3}` ou `[a b]`. `{5}` e `{5,10}` (sem
espaço) funcionam normalmente.

## Implementação

- `metadata_crawler/utils.py`: `search_metadata()` e `_compile_token_patterns()`.
- `metadata_crawler/templatetags/highlight.py`: filtro `highlight`.
- `metadata_crawler/views.py`: `search_results()` (redireciona `?q=` para
  `/search/<query>/`).
