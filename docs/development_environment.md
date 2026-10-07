# Ambiente de Desenvolvimento (SQL Server / ODBC / Emulação)

Este documento descreve como preparar e operar o ambiente de desenvolvimento
quando ele **não** tem acesso à rede interna do BACEN, ao domínio/Windows
Authentication (Kerberos) ou aos drivers ODBC usados em produção.

Em produção nada muda: as conexões reais com **SQL Server** (Windows
Authentication via `Trusted_Connection=yes` + Kerberos) e **Teradata**
(`teradatasql`) continuam sendo usadas normalmente.

## 1. Driver ODBC do SQL Server no Linux

### Sintoma

Ao rastrear uma conexão MSSQL no Linux surge o erro:

```
[unixODBC][Driver Manager]Can't open lib 'SQL Server' : file not found (0) (SQLDriverConnect)
```

Isso acontece porque a aplicação monta a connection string com o driver
legado `Driver={SQL Server}` (`metadata_crawler/utils.py`), que só existe no
Windows ou na imagem base de produção (BcCloud).

### Solução

Execute o script idempotente (requer root):

```bash
sudo scripts/setup_mssql_odbc.sh
```

O script:

1. adiciona o repositório do Microsoft ODBC Driver (caso ausente);
2. instala `unixodbc` + `msodbcsql17` (somente se necessário);
3. registra o alias legado `[SQL Server]` em `/etc/odbcinst.ini` apontando
   para o ODBC Driver 17 — **apenas se ele ainda não existir**, para nunca
   sobrescrever o driver usado em produção;
4. lista os drivers ODBC disponíveis.

O Driver 17 foi escolhido por ter comportamento equivalente ao driver legado
`{SQL Server}` (sem criptografia obrigatória), diferente do Driver 18.

Validação:

```bash
python -c "import pyodbc; print(pyodbc.drivers())"
# ['ODBC Driver 18 for SQL Server', 'SQL Server', 'ODBC Driver 17 for SQL Server']
```

## 2. Emulação de rastreamento (`CRAWL_EMULATE`)

Mesmo com o driver instalado, o host de desenvolvimento pode não alcançar o
servidor real (`sqldesigprod` não resolve, sem `krb5.conf`, sem ticket
Kerberos). Nesse caso o erro passa a ser:

```
('HYT00', '[HYT00] [Microsoft][ODBC Driver 17 for SQL Server]Login timeout expired ...')
```

Para permitir o desenvolvimento da interface, existe um fallback de emulação
controlado pela variável de ambiente `CRAWL_EMULATE` (**desligado por
padrão**).

Comportamento quando `CRAWL_EMULATE=true` e a conexão real falha:

- o rastreamento é considerado bem-sucedido;
- os metadados **já existentes** no SQLite (ex.: snapshot de produção) são
  **preservados** — nenhum registro é apagado;
- se a conexão ainda não tiver metadados, é gerado um conjunto sintético
  mínimo (`TABELA_EXEMPLO`, `VW_EXEMPLO`) para manter a navegação funcional.

### Habilitando no serviço de desenvolvimento

No unit do systemd (`/etc/systemd/system/dict-db.service`):

```ini
Environment=CRAWL_EMULATE=true
```

E recarregue:

```bash
sudo systemctl daemon-reload
sudo systemctl restart dict-db.service
```

### Garantias

- `CRAWL_EMULATE` é opt-in: em produção, sem a variável, a conexão real é
  sempre tentada primeiro e os erros continuam sendo propagados.
- A emulação só é acionada em **falha de conexão**; o fluxo real (SQL Server e
  Teradata) permanece intacto.
