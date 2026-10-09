# Linhagem de views e modificadores DML

Este documento descreve a extração de **dependências de views** e de
**modificadores DML** (quem escreve nas tabelas) executada durante o
rastreamento de uma conexão MSSQL.

## 1. Visão geral

Ao rastrear uma conexão (`/connection/<id>/crawl/`), além dos metadados de
tabelas/colunas, o `DatabaseCrawler` atualiza dois artefatos JSON na raiz do
projeto:

| Arquivo          | Conteúdo                                                        |
|------------------|-----------------------------------------------------------------|
| `lineage.json`   | Para cada view, as tabelas/views de que ela depende (`sources`).|
| `modifiers.json` | Para cada tabela, os comandos DML que a afetam e onde ocorrem.  |

A lógica é compartilhada entre o crawler Django e o script standalone
`outros/dependencias/extract.py`, e vive em `metadata_crawler/lineage.py`
(módulo puro, sem dependências do Django).

## 2. `lineage.json`

Formato (lista de objetos):

```json
[
  {
    "object": "desig_cadastro.dbo.vw_if_congl",
    "sources": ["desig_cadastro.dbo.cad_unicad", "..."],
    "status": "success"
  }
]
```

- `object` e `sources` usam a forma `banco.esquema.nome`.
- Registros existentes são **atualizados/inseridos**, nunca apagados
  (merge incremental por `object`).

## 3. `modifiers.json`

Agrupado por tabela alvo:

```json
[
  {
    "table": "reprebh.dbo.cosif_contas_finais",
    "modifiers": [
      {
        "command": "INSERT",
        "routine": "reprebh.dbo.Atualiza_COSIF_Contas_Finais",
        "routine_type": "PROCEDURE"
      }
    ]
  }
]
```

- `command`: `INSERT`, `SELECT INTO`, `UPDATE` ou `DELETE`.
- `routine`: função/stored procedure que executa o comando.
- `routine_type`: `PROCEDURE` ou `FUNCTION`.
- Chave de merge: `table`. Diferente de `lineage.json`, os modificadores da
  mesma tabela são **acumulados** entre rastreamentos (deduplicados por
  `command`/`routine`), pois bancos diferentes podem gravar na mesma tabela e
  cada conexão enxerga apenas parte do servidor.

### Comandos reconhecidos

- `INSERT [INTO] <tabela>`
- `SELECT ... INTO <tabela>`
- `UPDATE <tabela|alias> SET ...` (resolve alias via `FROM ... alias`)
- `DELETE FROM <tabela>` e `DELETE <alias> FROM <tabela> <alias>`

Observações de parsing:

- Comentários (`--`, `/* */`) e literais de texto são removidos com um
  scanner de passada única (não se confunde com `--` dentro de strings).
- Identificadores entre `[colchetes]` ou `"aspas duplas"` são suportados.
- `banco..tabela` (esquema omitido) é normalizado para `banco.dbo.tabela`.
- Nomes não qualificados são resolvidos para o banco da própria rotina;
  referências de 3 partes vão para o banco alvo.
- CTEs e tabelas temporárias (`#temp`) e variáveis de tabela (`@tabela`) são
  ignoradas.
- **SQL dinâmico é capturado**: os literais usados em `EXEC('...')` /
  `sp_executesql N'...'` são desembrulhados recursivamente (até 3 níveis), de
  modo que `SET @sql = 'DELETE FROM dbo.T'; EXEC(@sql)` registra o `DELETE`.
  Palavras-chave que aparecem isoladas em trechos concatenados (ex.:
  `'INSERT INTO ' + @tabela`) são descartadas para não virar tabela.

### Modificações cross-database

O ponto mais importante: uma SP pode estar em um banco e gravar em outro. Por
isso o rastreamento varre as rotinas de **todos os bancos acessíveis** do
servidor (`sys.databases` com `HAS_DBACCESS = 1`) e resolve referências
cross-database. Isso captura, por exemplo, uma SP em `desig_d5_limites` que faz
`INSERT INTO DESIG_D5_Monitoramento_de_Limites..tabela`.

A varredura cross-database pode ser desligada em ambientes onde for custosa:

```python
# db_metadata_crawler/settings.py
LINEAGE_SCAN_ALL_DATABASES = False
```

## 4. Integração com o rastreamento

`DatabaseCrawler.crawl()` chama `_crawl_lineage(cursor)` ao final (somente
MSSQL). A extração é **best-effort**: falhas são registradas em log e não
interrompem o rastreamento de metadados.

Caminhos configuráveis em `settings.py`:

```python
LINEAGE_JSON_PATH = BASE_DIR / 'lineage.json'
MODIFIERS_JSON_PATH = BASE_DIR / 'modifiers.json'
LINEAGE_SCAN_ALL_DATABASES = True
```

Os arquivos são servidos por `/lineage.json/` e `/modifiers.json/`. Se um
arquivo não existir, o endpoint responde `404` e a interface degrada
graciosamente.

## 5. Interface

Na página de detalhes (`/table/<id>/`):

- **Tabela**: a seção chama-se **"Modificadores (comandos DML)"** e lista, em
  uma tabela, o comando, a função/stored procedure e o tipo. A árvore de
  dependências não é exibida (não se aplica a tabelas).
- **View**: a seção chama-se **"Árvore de Dependências"** (árvore recursiva de
  `lineage.json`). Views **não** exibem a lista de modificadores, pois o conceito
  de comandos DML que gravam na tabela não se aplica a uma view.

A interface busca `/modifiers.json` e faz o *match* pela chave
`banco.esquema.tabela` em minúsculas.

## 6. Uso standalone (máquina com acesso ao SQL Server)

```bash
python outros/dependencias/extract.py reprebh
```

Gera/atualiza `lineage.json` e `modifiers.json` no diretório corrente
(varrendo todos os bancos acessíveis). Copie o `modifiers.json` resultante para
a raiz do projeto se necessário.

## 7. Prontidão para produção

- A emulação de rastreamento (`CRAWL_EMULATE=true`) é um recurso **de
  desenvolvimento**: em produção, mantenha-a **desligada** para que o banco real
  seja acessado.
- A varredura cross-database exige permissão de leitura nos bancos alvo
  (`HAS_DBACCESS`); bancos sem permissão são ignorados.
- O diretório dos JSON (`BASE_DIR`/`DADOS_PATH`) precisa ser gravável pelo
  usuário do serviço. A escrita é atômica (`arquivo.tmp` + `os.replace`).
- Em bases muito grandes, o rastreamento (colunas + linhagem) pode ultrapassar
  o timeout do gunicorn. Se necessário, aumente `--timeout` no serviço
  (ex.: `/etc/systemd/system/dict-db.service`) ou desligue
  `LINEAGE_SCAN_ALL_DATABASES`.
- `lineage.json` e `modifiers.json` podem ser versionados como *snapshot*; em
  produção eles são regravados a cada rastreamento (merge incremental, nada é
  apagado).

## 8. Testes

```bash
./venv/bin/python manage.py test metadata_crawler
```

Os testes cobrem o parser DML (INSERT/SELECT INTO/UPDATE/DELETE, alias, CTE,
temporárias, strings, identificadores cross-database), o agrupamento por tabela
e o merge incremental dos JSON.
