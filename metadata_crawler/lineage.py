"""Extração de linhagem (dependências) e de modificadores DML.

Este módulo é intencionalmente puro (não importa Django) para poder ser
reutilizado tanto pelo crawler (``metadata_crawler.utils``) quanto por scripts
standalone (``outros/dependencias/extract.py``).

Dois artefatos são produzidos:

* ``lineage.json``   – dependências das *views* (quais tabelas/views cada view lê).
* ``modifiers.json`` – comandos DML (INSERT, SELECT ... INTO, UPDATE, DELETE)
  executados por *funções* e *stored procedures* que afetam cada tabela.

Formato do ``modifiers.json`` (agrupado por tabela alvo)::

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
"""

import json
import os
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Limpeza de SQL
# ---------------------------------------------------------------------------
def strip_sql_noise(sql: str) -> str:
    """Remove comentários e literais de texto com um scanner de passada única.

    Diferente de substituições por regex encadeadas, o scanner não se confunde
    com ``--`` dentro de strings nem com aspas dentro de comentários, evitando
    perder comandos DML reais.
    """
    if not sql:
        return ""

    out: List[str] = []
    i = 0
    n = len(sql)
    state = None  # None | 'line' | 'block' | 'string' | 'dquote'
    while i < n:
        ch = sql[i]
        two = sql[i:i + 2]

        if state is None:
            if two == "--":
                state = "line"
                i += 2
                out.append(" ")
            elif two == "/*":
                state = "block"
                i += 2
                out.append(" ")
            elif ch == "'":
                state = "string"
                i += 1
                out.append("''")
            elif ch == '"':
                state = "dquote"
                out.append(ch)
                i += 1
            else:
                out.append(ch)
                i += 1
        elif state == "line":
            if ch in "\r\n":
                state = None
                out.append(ch)
            i += 1
        elif state == "block":
            if two == "*/":
                state = None
                i += 2
            else:
                i += 1
        elif state == "string":
            if two == "''":
                i += 2
            elif ch == "'":
                state = None
                i += 1
            else:
                i += 1
        else:  # dquote
            if two == '""':
                out.append('""')
                i += 2
            elif ch == '"':
                state = None
                out.append(ch)
                i += 1
            else:
                out.append(ch)
                i += 1

    return "".join(out)


# ---------------------------------------------------------------------------
# Identificadores (com suporte a [colchetes], "aspas duplas" e nomes com pontos)
# ---------------------------------------------------------------------------
_IDENT = r'(?:\[[^\]]+\]|"[^"]+"|[A-Za-z_@#][\w$#@]*)'
# O segmento após o ponto é opcional para aceitar ``banco..tabela`` (esquema
# omitido), comum em referências cross-database.
_QUALIFIED = rf"{_IDENT}(?:\s*\.\s*(?:{_IDENT})?){{0,3}}"

_CTE_WITH_RE = re.compile(r"\bWITH\s+(.+?)\bSELECT\b", re.IGNORECASE | re.DOTALL)
_CTE_NAME_RE = re.compile(r"([A-Za-z_@#][\w$#@]*)\s+AS\s*\(", re.IGNORECASE)


def split_identifier(raw: str) -> List[str]:
    """Divide um identificador qualificado respeitando [colchetes]/"aspas".

    Segmentos vazios são preservados para distinguir ``banco..tabela``.
    """
    raw = (raw or "").strip()
    if not raw:
        return []

    parts: List[str] = []
    buf = ""
    depth = 0
    in_dquote = False
    for ch in raw:
        if ch == "[" and not in_dquote:
            depth += 1
            buf += ch
        elif ch == "]" and not in_dquote:
            depth = max(0, depth - 1)
            buf += ch
        elif ch == '"':
            in_dquote = not in_dquote
            buf += ch
        elif ch == "." and depth == 0 and not in_dquote:
            parts.append(buf.strip())
            buf = ""
        else:
            buf += ch
    parts.append(buf.strip())

    cleaned = []
    for part in parts:
        part = part.strip()
        if part.startswith("[") and part.endswith("]"):
            part = part[1:-1]
        elif part.startswith('"') and part.endswith('"') and len(part) >= 2:
            part = part[1:-1]
        cleaned.append(part)
    return cleaned


def normalize_table(db: str, raw: str) -> Optional[str]:
    """Normaliza um identificador para ``banco.esquema.tabela`` (minúsculas).

    Suporta nomes de 1 a 3 partes e a forma ``banco..tabela``. Retorna ``None``
    para objetos que não são tabelas físicas (ex.: tabelas temporárias
    ``#temp``).
    """
    db = (db or "").strip().lower()
    parts = [("" if p == "<default>" else p.strip().lower())
             for p in split_identifier(raw)]
    if not parts:
        return None
    # Tabelas temporárias (#temp) e variáveis de tabela (@tabela) não são
    # objetos físicos e não devem aparecer como tabelas modificadas.
    if any(p.startswith(("#", "@")) for p in parts if p):
        return None

    name = parts[-1].strip()
    if not name:
        return None
    schema = parts[-2].strip() if len(parts) >= 2 else ""
    database = parts[-3].strip() if len(parts) >= 3 else ""

    if not schema:
        schema = "dbo"
    if not database:
        database = db
    return f"{database}.{schema}.{name}"


def extract_cte_names(sql: str) -> set:
    """Coleta nomes de CTEs para não confundi-las com tabelas reais."""
    names = set()
    for match in _CTE_WITH_RE.finditer(sql):
        block = match.group(1)
        for name in _CTE_NAME_RE.findall(block):
            names.add(name.lower())
    return names


# ---------------------------------------------------------------------------
# Extração de dependências de views (portado de extract.py)
# ---------------------------------------------------------------------------
def fix_broken_cte(sql_text: str) -> str:
    """Reconstrói o WITH quando uma CTE perdeu sua cláusula inicial."""
    if re.search(r"\)\s*SELECT", sql_text, re.IGNORECASE):
        parts = re.split(r"\)\s*SELECT", sql_text, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) == 2:
            first_select = parts[0].strip()
            second_select = parts[1].strip()
            return f"WITH agrupados AS ( {first_select} ) SELECT {second_select}"
    return sql_text


def clean_sql(sql_text: str) -> str:
    """Remove comentários e tokens problemáticos de SQL de view."""
    if not sql_text:
        return ""

    sql_text = re.sub(r"--.*", "", sql_text)
    sql_text = re.sub(r"/\*.*?\*/", "", sql_text, flags=re.DOTALL)
    sql_text = re.sub(r"[\[\]]", "", sql_text)
    sql_text = re.sub(r"PIVOT\s*\(.*?\)\s*\w+", "", sql_text, flags=re.IGNORECASE | re.DOTALL)

    match = re.search(r"\bSELECT\b", sql_text, re.IGNORECASE)
    if match:
        sql_text = sql_text[match.start():]

    sql_text = re.sub(r"SELECT\s+TOP\s+100\s+PERCENT", "SELECT", sql_text, flags=re.IGNORECASE)
    sql_text = re.sub(r"\s+", " ", sql_text)

    def simplify_select_clause(m):
        select_part = re.sub(r"\bdbo\.", "", m.group(1), flags=re.IGNORECASE)
        return f"SELECT {select_part} FROM"

    sql_text = re.sub(r"SELECT (.*?) FROM", simplify_select_clause, sql_text, flags=re.IGNORECASE)

    sql_text = re.sub(r"\bGO\b", "", sql_text, flags=re.IGNORECASE)
    sql_text = re.sub(r"\bSET\s+\w+.*?;", "", sql_text, flags=re.IGNORECASE)
    sql_text = sql_text.strip()
    sql_text = re.sub(r"[\[\]]", "", sql_text)
    sql_text = re.sub(r"--.*", "", sql_text)
    sql_text = re.sub(r"/\*.*?\*/", "", sql_text, flags=re.DOTALL)
    sql_text = re.sub(r"\s+", " ", sql_text)

    sql_text = fix_broken_cte(sql_text)

    match = re.search(r"\bSELECT\b", sql_text, re.IGNORECASE)
    if match:
        return sql_text[match.start():]
    return sql_text


def extract_table_identifiers(db: str, sql: str, normalize_case: bool = True) -> List[str]:
    """Extrai tabelas/views referenciadas em FROM/JOIN de um SELECT."""
    cleaned_sql = re.sub(r"\s+", " ", sql)

    cte_names = set()
    cte_match = _CTE_WITH_RE.search(cleaned_sql)
    if cte_match:
        for name in _CTE_NAME_RE.findall(cte_match.group(1)):
            cte_names.add(name.lower())

    table_pattern = re.compile(
        r"(?i)\b(?:from|join)\s+"
        r"((?:[a-z_][\w$]*)(?:\.(?:[a-z_][\w$]*)){0,2})"
    )
    matches = table_pattern.findall(cleaned_sql)

    tables = set()
    for identifier in matches:
        normalized = identifier.lower() if normalize_case else identifier
        base_name = normalized.split(".")[-1]
        if base_name not in cte_names:
            tables.add(normalized)

    qualified = []
    for t in tables:
        t = str(t).replace("<default>.", "")
        dots = t.count(".")
        if dots >= 2:
            # já vem como banco.esquema.tabela
            qualified.append(t)
        elif dots == 1:
            # esquema.tabela -> falta apenas o banco
            qualified.append(f"{db}.{t}")
        else:
            # tabela -> assume o esquema dbo do banco atual
            qualified.append(f"{db}.dbo.{t}")
    return sorted(qualified)


def extract_view_dependencies(db: str, cursor) -> List[dict]:
    """Consulta as views do banco e devolve suas dependências."""
    cursor.execute(
        """
        SELECT
            s.name AS schema_name,
            v.name AS object_name,
            m.definition
        FROM sys.views v
        JOIN sys.schemas s ON v.schema_id = s.schema_id
        JOIN sys.sql_modules m ON v.object_id = m.object_id
        """
    )
    results = []
    for schema_name, object_name, definition in cursor.fetchall():
        obj = f"{db}.{schema_name}.{object_name}"
        if not definition:
            results.append({"object": obj, "sources": [], "status": "error",
                            "erro": "definition indisponível"})
            continue
        try:
            sources = extract_table_identifiers(db, clean_sql(definition))
            results.append({"object": obj, "sources": sources, "status": "success"})
        except Exception as exc:  # pragma: no cover - defensivo
            results.append({"object": obj, "sources": [], "status": "error",
                            "erro": str(exc)})
    return results


# ---------------------------------------------------------------------------
# Extração de modificadores DML (INSERT, SELECT INTO, UPDATE, DELETE)
# ---------------------------------------------------------------------------
_INSERT_RE = re.compile(r"\bINSERT\s+(?:INTO\s+)?(" + _QUALIFIED + r")", re.IGNORECASE)
# SELECT ... INTO não pode atravessar o fim da instrução (;) nem o início de
# outro comando DML, senão um "SELECT ...; INSERT INTO t" seria lido como
# "SELECT INTO t".
_SELECT_INTO_RE = re.compile(
    r"\bSELECT\b(?:(?!\bFROM\b|\bINSERT\b|\bUPDATE\b|\bDELETE\b|\bMERGE\b|;)[\s\S])*?"
    r"\bINTO\s+(" + _QUALIFIED + r")",
    re.IGNORECASE,
)
_UPDATE_RE = re.compile(r"\bUPDATE\s+(" + _QUALIFIED + r")\s+SET\b", re.IGNORECASE)
_DELETE_FROM_RE = re.compile(r"\bDELETE\s+FROM\s+(" + _QUALIFIED + r")", re.IGNORECASE)
_DELETE_ALIAS_RE = re.compile(r"\bDELETE\s+(?!FROM\b)(" + _QUALIFIED + r")", re.IGNORECASE)
_FROM_ALIAS_RE = re.compile(
    r"\bFROM\s+(" + _QUALIFIED + r")(?:\s+(?:AS\s+)?(" + _IDENT + r"))?",
    re.IGNORECASE,
)


def _resolve_alias_target(text: str, target_raw: str) -> str:
    """Resolve ``UPDATE alias`` / ``DELETE alias`` para a tabela do FROM.

    Procura o alias em todo o texto (ou no contexto informado, quando o DML veio
    de um pedaço de SQL dinâmico montado por concatenação).
    """
    parts = [p for p in split_identifier(target_raw) if p]
    if len(parts) >= 2:
        return target_raw
    alias = parts[0].strip("[]").lower() if parts else ""
    if not alias:
        return target_raw

    for match in _FROM_ALIAS_RE.finditer(text):
        table, table_alias = match.group(1), match.group(2)
        if table_alias and table_alias.strip("[]").lower() == alias:
            return table
    return target_raw


# Heurística usada para decidir se um literal de texto pode conter SQL
# dinâmico (evita reprocessar mensagens/e-mails sem comandos).
_DYNAMIC_SQL_HINT_RE = re.compile(
    r"\b(?:INSERT|UPDATE|DELETE|SELECT|EXEC|EXECUTE|MERGE|BULK)\b",
    re.IGNORECASE,
)

# Profundidade máxima de recursão ao desembrulhar SQL dinâmico aninhado.
_MAX_DYNAMIC_SQL_DEPTH = 3


def extract_string_literals(sql: str) -> List[str]:
    """Extrai o conteúdo dos literais de texto, ignorando comentários.

    É usado para recuperar comandos DML embutidos em SQL dinâmico executado
    por ``EXEC('...')`` / ``sp_executesql N'...'``. O scanner ignora
    ``--`` e ``/* */`` para não confundir apóstrofos em comentários e trata a
    duplicação de aspas (``''``) como escape.
    """
    if not sql:
        return []

    literals: List[str] = []
    i = 0
    n = len(sql)
    state = None  # None | 'line' | 'block'
    while i < n:
        ch = sql[i]
        two = sql[i:i + 2]

        if state is None:
            if two == "--":
                state = "line"
                i += 2
            elif two == "/*":
                state = "block"
                i += 2
            elif ch == "'":
                j = i + 1
                buf: List[str] = []
                while j < n:
                    if sql[j:j + 2] == "''":
                        buf.append("'")
                        j += 2
                    elif sql[j] == "'":
                        break
                    else:
                        buf.append(sql[j])
                        j += 1
                literals.append("".join(buf))
                i = j + 1 if j < n else n
            else:
                i += 1
        elif state == "line":
            if ch in "\r\n":
                state = None
            i += 1
        else:  # block
            if two == "*/":
                state = None
                i += 2
            else:
                i += 1

    return literals


# Palavras-chave que não são nomes de tabela. Aparecem como "tabela" quando
# um trecho de SQL dinâmico é montado por concatenação e termina logo após a
# palavra (ex.: ``'INSERT INTO ' + @tabela`` -> ``INSERT INTO``).
_SQL_RESERVED_WORDS = {
    "into", "values", "value", "set", "where", "from", "select", "insert",
    "update", "delete", "merge", "table", "top", "output", "default", "null",
    "join", "inner", "left", "right", "full", "outer", "cross", "apply", "on",
    "as", "with", "union", "all", "distinct", "and", "or", "not", "exists",
    "in", "is", "group", "order", "by", "having", "exec", "execute",
    "sp_executesql", "return", "begin", "end", "if", "else", "declare",
    "print", "goto", "case", "when", "then", "else", "cast", "convert",
    "truncate", "drop", "create", "alter", "identity", "option", "lock",
    "nolock", "holdlock", "rowlock", "readpast", "percent",
}


def _is_bare_reserved_word(raw: str) -> bool:
    """True quando o identificador é uma palavra-chave sem [colchetes]/"aspas"."""
    token = (raw or "").strip()
    if re.fullmatch(r"[A-Za-z_][\w$]*", token):
        return token.lower() in _SQL_RESERVED_WORDS
    return False


def _extract_static_modifiers(db: str, text: str,
                              alias_context: Optional[str] = None) -> List[Tuple[str, str]]:
    """Extrai DML de um texto já limpo (comentários/literais removidos).

    ``alias_context`` permite resolver ``UPDATE alias`` / ``DELETE alias`` cujo
    ``FROM`` ficou em outro trecho de SQL dinâmico.
    """
    cte_names = extract_cte_names(text)
    alias_text = alias_context if alias_context is not None else text
    found: List[Tuple[str, str]] = []

    def add(command: str, raw: str) -> None:
        if _is_bare_reserved_word(raw):
            return
        table = normalize_table(db, raw)
        if not table:
            return
        if table.split(".")[-1] in cte_names:
            return
        found.append((command, table))

    for match in _INSERT_RE.finditer(text):
        add("INSERT", match.group(1))

    for match in _SELECT_INTO_RE.finditer(text):
        add("SELECT INTO", match.group(1))

    for match in _UPDATE_RE.finditer(text):
        add("UPDATE", _resolve_alias_target(alias_text, match.group(1)))

    for match in _DELETE_FROM_RE.finditer(text):
        add("DELETE", match.group(1))

    for match in _DELETE_ALIAS_RE.finditer(text):
        add("DELETE", _resolve_alias_target(alias_text, match.group(1)))

    return found


def _extract_dynamic_modifiers(db: str, sql: str, alias_context: str,
                               depth: int) -> List[Tuple[str, str]]:
    """Desembrulha literais de SQL dinâmico, recursivamente."""
    if depth >= _MAX_DYNAMIC_SQL_DEPTH:
        return []

    found: List[Tuple[str, str]] = []
    for literal in extract_string_literals(sql):
        if not literal or not _DYNAMIC_SQL_HINT_RE.search(literal):
            continue
        found.extend(
            _extract_static_modifiers(db, strip_sql_noise(literal),
                                      alias_context=alias_context)
        )
        found.extend(_extract_dynamic_modifiers(db, literal, alias_context, depth + 1))
    return found


def extract_dml_modifiers(db: str, sql: str, _depth: int = 0) -> List[dict]:
    """Extrai comandos DML que afetam tabelas em um corpo SQL.

    Além do SQL estático, desembrulha SQL dinâmico (``EXEC('INSERT ...')`` e
    ``sp_executesql N'DELETE ...'``) para capturar comandos construídos em
    literais de texto, recursivamente (até ``_MAX_DYNAMIC_SQL_DEPTH``).

    Retorna uma lista de ``{"command": ..., "table": banco.esquema.tabela}``
    sem duplicidades e preservando a ordem de aparição.
    """
    if not sql:
        return []

    text = strip_sql_noise(sql)
    found: List[Tuple[str, str]] = list(_extract_static_modifiers(db, text)) if text else []

    literals = extract_string_literals(sql)
    if literals and _depth < _MAX_DYNAMIC_SQL_DEPTH:
        # Contexto único com todos os literais para resolver aliases cujo FROM
        # ficou em outro pedaço do SQL dinâmico montado por concatenação.
        alias_context = "\n".join(strip_sql_noise(lit) for lit in literals) or text
        found.extend(_extract_dynamic_modifiers(db, sql, alias_context, _depth))

    seen = set()
    modifiers = []
    for command, table in found:
        key = (command, table)
        if key not in seen:
            seen.add(key)
            modifiers.append({"command": command, "table": table})
    return modifiers


_ROUTINE_TYPES = {
    "P": "PROCEDURE",
    "FN": "FUNCTION",
    "IF": "FUNCTION",
    "TF": "FUNCTION",
    "FS": "FUNCTION",
    "FT": "FUNCTION",
}


def _routine_query(db: str) -> str:
    """Monta a consulta de rotinas para um banco específico (cross-database)."""
    safe_db = db.replace("]", "]]")
    return f"""
SELECT
    s.name AS schema_name,
    o.name AS object_name,
    o.type AS object_type,
    m.definition AS definition
FROM [{safe_db}].sys.sql_modules m
JOIN [{safe_db}].sys.objects o ON m.object_id = o.object_id
JOIN [{safe_db}].sys.schemas s ON o.schema_id = s.schema_id
WHERE o.type IN ('P', 'FN', 'IF', 'TF', 'FS', 'FT')
"""


def list_accessible_databases(cursor) -> List[str]:
    """Lista os bancos de dados de usuário acessíveis na conexão."""
    cursor.execute(
        """
        SELECT name
        FROM sys.databases
        WHERE database_id > 4
          AND state = 0
          AND HAS_DBACCESS(name) = 1
        ORDER BY name
        """
    )
    return [row[0] for row in cursor.fetchall()]


def extract_routine_modifiers(db: str, cursor) -> List[dict]:
    """Consulta funções/stored procedures de ``db`` e devolve os DMLs.

    Os nomes de tabela sem qualificação são resolvidos para ``db`` (o banco da
    própria rotina); referências cross-database (``outro_banco.dbo.tabela`` ou
    ``outro_banco..tabela``) são resolvidas para o banco alvo.
    """
    cursor.execute(_routine_query(db))
    routines = []
    for schema_name, object_name, object_type, definition in cursor.fetchall():
        if not definition:
            continue
        try:
            modifiers = extract_dml_modifiers(db, definition)
        except Exception:
            # Uma definição problemática não pode descartar as demais rotinas
            # do banco (ex.: erro de decodificação do driver ODBC).
            continue
        if not modifiers:
            continue
        routines.append({
            "routine": f"{db}.{schema_name}.{object_name}",
            "routine_type": _ROUTINE_TYPES.get((object_type or "").strip().upper(), "ROUTINE"),
            "modifiers": modifiers,
        })
    return routines


def build_table_modifier_index(routines: Iterable[dict]) -> List[dict]:
    """Agrupa os modificadores por tabela alvo."""
    index: Dict[str, List[dict]] = {}
    for routine in routines:
        for modifier in routine.get("modifiers", []):
            index.setdefault(modifier["table"], []).append({
                "command": modifier["command"],
                "routine": routine["routine"],
                "routine_type": routine["routine_type"],
            })

    def sort_key(entry: dict) -> Tuple[str, str, str]:
        return (entry["routine"].lower(), entry["command"], entry["routine_type"])

    return [
        {"table": table, "modifiers": sorted(modifiers, key=sort_key)}
        for table, modifiers in sorted(index.items())
    ]


# ---------------------------------------------------------------------------
# Persistência (merge incremental)
# ---------------------------------------------------------------------------
def load_json(path: str) -> list:
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, list) else []
    except (ValueError, OSError):
        return []


def merge_records(existing: Sequence[dict], new_records: Iterable[dict], key: str) -> list:
    """Atualiza/insere registros mantendo os demais (nada é apagado)."""
    merged = {item.get(key): item for item in existing if item.get(key)}
    for item in new_records:
        item_key = item.get(key)
        if item_key:
            merged[item_key] = item
    return list(merged.values())


def merge_modifier_records(existing: Sequence[dict], new_records: Iterable[dict]) -> list:
    """Acumula modificadores por tabela em vez de substituir o registro.

    Como o rastreamento é cross-database e pode ser feito por conexões com
    permissões diferentes, a mesma tabela pode ser modificada por rotinas de
    bancos distintos em rastreamentos distintos. Substituir o registro inteiro
    perderia os modificadores já conhecidos; aqui eles são unidos (sem
    duplicar ``command``/``routine``).
    """
    merged: Dict[str, dict] = {}
    for item in existing:
        table = item.get("table")
        if table:
            merged[table] = {
                "table": table,
                "modifiers": list(item.get("modifiers", [])),
            }

    for item in new_records:
        table = item.get("table")
        if not table:
            continue
        entry = merged.setdefault(table, {"table": table, "modifiers": []})
        # A deduplicação ignora a caixa do nome da rotina: o mesmo banco pode
        # ser relatado como ``REPREBH`` (``sys.databases``) ou ``reprebh`` (nome
        # da conexão) e não deve gerar linhas duplicadas.
        seen = {
            (m.get("command"), (m.get("routine") or "").lower(),
             m.get("routine_type"))
            for m in entry["modifiers"]
        }
        for modifier in item.get("modifiers", []):
            key = (modifier.get("command"),
                   (modifier.get("routine") or "").lower(),
                   modifier.get("routine_type"))
            if key not in seen:
                seen.add(key)
                entry["modifiers"].append(modifier)

    for entry in merged.values():
        entry["modifiers"].sort(
            key=lambda m: (m.get("routine", "").lower(), m.get("command", ""),
                           m.get("routine_type", ""))
        )

    return [merged[table] for table in sorted(merged)]


def write_json(path: str, data) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)


def update_lineage_files(db: str, cursor,
                         lineage_path: str,
                         modifiers_path: str,
                         databases: Optional[Sequence[str]] = None) -> dict:
    """Atualiza ``lineage.json`` e ``modifiers.json`` para uma conexão.

    ``databases`` permite varrer as rotinas de vários bancos do mesmo servidor
    para capturar modificações cross-database (ex.: uma stored procedure em
    ``desig_d5_limites`` que faz ``INSERT INTO DESIG_D5_...dbo.tabela``). Se
    omitido, apenas o banco ``db`` é varrido.
    """
    views = extract_view_dependencies(db, cursor)

    # O nome do banco configurado na conexão pode diferir apenas na caixa
    # (ex.: ``reprebh`` vs ``REPREBH`` devolvido por ``sys.databases``). Sem a
    # comparação case-insensitive o banco seria varrido duas vezes e as rotinas
    # apareceriam duplicadas em ``modifiers.json``.
    routine_db_list = list(databases) if databases else [db]
    if db.strip().lower() not in {d.strip().lower() for d in routine_db_list}:
        routine_db_list.append(db)

    routines: List[dict] = []
    for routine_db in routine_db_list:
        try:
            routines.extend(extract_routine_modifiers(routine_db, cursor))
        except Exception:
            # Bancos sem permissão/offline são ignorados; o rastreamento segue.
            continue

    modifier_index = build_table_modifier_index(routines)

    if lineage_path:
        existing_lineage = load_json(lineage_path)
        merged_lineage = merge_records(existing_lineage, views, "object")
        write_json(lineage_path, merged_lineage)

    if modifiers_path:
        existing_modifiers = load_json(modifiers_path)
        merged_modifiers = merge_modifier_records(existing_modifiers, modifier_index)
        write_json(modifiers_path, merged_modifiers)

    return {
        "views": len(views),
        "routines_with_dml": len(routines),
        "tables_modified": len(modifier_index),
    }
