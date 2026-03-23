# Autenticação com Kerberos (BcCloud)

Este documento descreve como a aplicação realiza autenticação com Kerberos em produção (Linux) na BcCloud, tanto para conexões Microsoft SQL Server (Windows Authentication) quanto para Teradata via ODBC.

## Visão Geral

- Em Linux, antes de abrir conexões ODBC que dependem de SSO/Kerberos, a aplicação tenta garantir um ticket Kerberos (TGT) válido.
- A inicialização é "best-effort": erros são logados e a conexão segue. Se o banco exigir ticket e ele não estiver disponível, o driver ODBC retornará erro na conexão.

## Ativação (KINIT_HABILITADO)

- Defina a variável de ambiente `KINIT_HABILITADO=true` para habilitar o fluxo com keytab.
- Quando habilitado, se existir o arquivo `/app/secrets/cloud.keytab.b64`, a aplicação utilizará o keytab para autenticação.
- Na ausência do keytab, a aplicação tenta autenticação via usuário/senha definidos em `APP_USER` e `APP_PASS` (ou `username_dlo`/`password_dlo`).

## Keytab

1. Gere o keytab (via `kadmin` ou `ktutil`).
2. Converta para base64 e disponibilize em `/app/secrets/cloud.keytab.b64`.
3. O aplicativo decodifica para `/app/secrets/cloud.keytab` e executa `kinit -kt /app/secrets/cloud.keytab <principal>`.

> Segurança: prefira o keytab ao par usuário/senha.

## Usuário/Senha

- Defina `APP_USER` e `APP_PASS` no ambiente (pode usar os segredos padrão da BcCloud `@{user}` / `@{pass}`).
- Alternativamente, as variáveis legadas `username_dlo` / `password_dlo` são aceitas.

## Dockerfile

Incluímos a configuração do cache do Kerberos conforme BcCloud para uso do KCM:

```
RUN sed -i "s/\[libdefaults\]/[libdefaults]\n    default_ccache_name = KCM:/g" /etc/krb5.conf || true
```

## Conexões

- MSSQL (Windows Authentication): quando a string de conexão usa `Trusted_Connection=yes` em Linux, a aplicação tenta garantir o ticket Kerberos antes do `pyodbc.connect`.
- Teradata: quando nenhum usuário/senha é fornecido, a aplicação monta a string de conexão com `Authentication=KRB5` e tenta garantir o ticket antes do `pyodbc.connect`.

## Variáveis de Ambiente

- `KINIT_HABILITADO`: `true` para habilitar fluxo via keytab.
- `APP_USER` / `APP_PASS`: principal e senha do serviço (fallback).
- `username_dlo` / `password_dlo`: variáveis legadas aceitas como fallback.
- Opcional: `KRB5CCNAME` para customizar o caminho do cache de credenciais.

## Requisitos de Ambiente (Linux)

- Cliente Kerberos e configuração (`krb5.conf`) válidos com realm/KDC corretos.
- ODBC drivers instalados: `msodbcsql17` e `unixODBC` para MSSQL; driver Teradata para ODBC.
- DNS/SPN adequados: o host em `SERVER/DBCNAME` deve resolver para o FQDN com SPN correto.

### Cache de Credenciais (KCM/KEYRING/FILE)

- Em alguns ambientes Docker, o serviço `KCM` não está disponível, causando erros como: `No Kerberos credentials available: No KCM server found`.
- Soluções:
  - Preferencial: habilitar `KCM` no host/contêiner conforme política interna.
  - Alternativa: configurar `default_ccache_name` para `KEYRING:persistent:%{uid}` ou `FILE:/tmp/krb5cc_%{uid}`.

Exemplos de configuração automática no `Dockerfile`:

```
# Usa KCM se disponível
RUN sed -i "s/\[libdefaults\]/[libdefaults]\n    default_ccache_name = KCM:/g" /etc/krb5.conf || true
# Fallback para KEYRING
RUN grep -q "default_ccache_name" /etc/krb5.conf || sed -i "s/\[libdefaults\]/[libdefaults]\n    default_ccache_name = KEYRING:persistent:%{uid}/g" /etc/krb5.conf || true
```

> Caso KEYRING não seja suportado, use o `FILE` como último recurso e garanta permissões no caminho.

## Troubleshooting

- Verifique tickets com `klist` (logs exibem o resultado em nível debug).
- Certifique-se de que o principal corresponde ao realm e que o SPN do alvo é válido.
- Em erro de conexão com mensagem de credenciais, valide se o ticket foi emitido e se o cache está acessível.

## Implementação no Código

- `metadata_crawler/autenticar_user.py`:
  - Função `ensure_kerberos_ticket()` que implementa:
    - Keytab via `/app/secrets/cloud.keytab.b64` (se `KINIT_HABILITADO=true`).
    - Fallback via `APP_USER`/`APP_PASS` ou variáveis legadas.
  - Logging com `logging` padrão.
- `metadata_crawler/utils.py`:
  - Chama `ensure_kerberos_ticket()` em Linux quando:
    - MSSQL com `Trusted_Connection=yes`, ou
    - Teradata com `Authentication=KRB5`.
  - Tratamento é best-effort (log de erro e continuidade).

## Teradata via `teradatasql` (Python)

- O teste de conexão suporta o driver Python `teradatasql` com string JSON:

```
{"host":"<host>", "logmech":"TD2", "tmode":"TERA", "user":"<user>", "password":"<pass>"}
```

- Instalação: incluir `teradatasql` em `requirements.txt` ou no ambiente alvo.
- Parâmetro `logmech` pode ser ajustado (`TD2`, `LDAP`, `KRB5`, etc.) conforme política do ambiente.

## Segurança

- Nunca versionar keytabs ou segredos.
- Use segredos gerenciados pela plataforma (BcCloud) e permissões mínimas necessárias.