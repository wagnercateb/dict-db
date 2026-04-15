
from typing import List
import pyodbc
import os
import json
import re
import sys

# Não vi benefício em usar a biblioteca 
# from sqllineage.runner import LineageRunner
# No SQL Server ela deu erros e é muito mais lenta que o método extract_table_identifiers()


def fix_broken_cte(sql_text: str) -> str:
    """
    Fix cases where a CTE lost its WITH clause
    """

    # detect pattern: ") SELECT"
    if re.search(r'\)\s*SELECT', sql_text, re.IGNORECASE):

        parts = re.split(r'\)\s*SELECT', sql_text, maxsplit=1, flags=re.IGNORECASE)

        if len(parts) == 2:
            first_select = parts[0].strip()
            second_select = parts[1].strip()

            fixed_sql = f"""
            WITH agrupados AS (
                {first_select}
            )
            SELECT {second_select}
            """

            return fixed_sql

    return sql_text


def clean_sql(sql_text: str) -> str:
    """Remove comments and problematic tokens from SQL"""

    # --- OPTIONAL: simplify repeated dbo prefixes in SELECT only ---
    # (keep them in FROM/JOIN for lineage accuracy)
    def simplify_select_clause(match):
        select_part = match.group(1)
        # remove dbo. prefix only in select list
        select_part = re.sub(r'\bdbo\.', '', select_part, flags=re.IGNORECASE)
        return f"SELECT {select_part} FROM"
    
    # remove inline comments --
    sql_text = re.sub(r'--.*', '', sql_text)

    # remove block comments /* */
    sql_text = re.sub(r'/\*.*?\*/', '', sql_text, flags=re.DOTALL)

    # --- remove brackets ---
    sql_text = re.sub(r'[\[\]]', '', sql_text)

    # Remove PIVOT (...) alias
    sql_text = re.sub(
        r'PIVOT\s*\(.*?\)\s*\w+',
        '',
        sql_text,
        flags=re.IGNORECASE | re.DOTALL
    )

    # --- remove CREATE VIEW / PROC wrapper ---
    match = re.search(r'\bSELECT\b', sql_text, re.IGNORECASE)
    if match:
        sql_text = sql_text[match.start():]

    # --- remove TOP 100 PERCENT ---
    sql_text = re.sub(
        r'SELECT\s+TOP\s+100\s+PERCENT',
        'SELECT',
        sql_text,
        flags=re.IGNORECASE
    )

    # --- simplify multiple spaces ---
    sql_text = re.sub(r'\s+', ' ', sql_text)

    sql_text = re.sub(
        r'SELECT (.*?) FROM',
        simplify_select_clause,
        sql_text,
        flags=re.IGNORECASE
    )


    # remove GO statements
    sql_text = re.sub(r'\bGO\b', '', sql_text, flags=re.IGNORECASE)

    # remove SET statements (often useless for lineage)
    sql_text = re.sub(r'\bSET\s+\w+.*?;', '', sql_text, flags=re.IGNORECASE)

    sql_text = sql_text.strip()


    # remove brackets [dbo] → dbo
    sql_text = re.sub(r'[\[\]]', '', sql_text)

    # remove comments
    sql_text = re.sub(r'--.*', '', sql_text)
    sql_text = re.sub(r'/\*.*?\*/', '', sql_text, flags=re.DOTALL)

    # normalize spaces
    sql_text = re.sub(r'\s+', ' ', sql_text)


    # --- FIX BROKEN CTE (NEW STEP) ---
    sql_text = fix_broken_cte(sql_text)


    # find SELECT keyword
    match = re.search(r'\bSELECT\b', sql_text, re.IGNORECASE)

    if match:
        return sql_text[match.start():]
    
    return sql_text



def process_single_object(db: str, schema: str, name: str, sql: str) -> dict:
    """Process one SQL object and return lineage"""

    cleaned_sql = clean_sql(sql)

    try:
        sources = extract_table_identifiers(db, cleaned_sql)
        return {
            "object": f"{db}.{schema}.{name}",
            "sources": sources,
            "status": "success"
        }
                
    except Exception as e:
        return {
            "object": f"{db}.{schema}.{name}",
            "sources": [],
            "status": "error",
            "erro": str(e)
        }            


    




def extract_table_identifiers(db: str, sql: str, normalize_case: bool = True) -> List[str]:
    """
    Extract physical table/view identifiers from a T-SQL SELECT statement.

    Parameters
    ----------
    db : str
        Nome do banco de dados
    sql : str
        Full SQL text (e.g., CREATE VIEW body or plain SELECT).
    normalize_case : bool
        If True, returns identifiers in lower-case.

    Returns
    -------
    List[str]
        Sorted list of unique table/view identifiers.
        Examples:
            - vw_unicad_if_congl
            - desig_cadastro.dbo.cad_unicad
            - dbcOS001.dbo.cos_sal_saldopadrao_2014
    """

    # ------------------------------------------------------------------
    # 1) Normalize whitespace to simplify regex behavior
    # ------------------------------------------------------------------
    cleaned_sql = re.sub(r"\s+", " ", sql)

    # ------------------------------------------------------------------
    # 2) Capture CTE names (WITH cte AS (...), cte2 AS (...))
    # ------------------------------------------------------------------
    cte_pattern = re.compile(
        r"(?i)\bwith\s+(.+?)\bselect\b",
        re.DOTALL
    )

    cte_names = set()
    cte_match = cte_pattern.search(cleaned_sql)
    if cte_match:
        cte_block = cte_match.group(1)

        # Extract "cte_name AS ("
        for name in re.findall(r"(?i)\b([a-z_][\w$]*)\s+as\s*\(", cte_block):
            cte_names.add(name.lower())

    # ------------------------------------------------------------------
    # 3) Extract identifiers after FROM / JOIN
    # ------------------------------------------------------------------
    table_pattern = re.compile(
        r"(?i)\b(?:from|join)\s+"
        r"((?:[a-z_][\w$]*)(?:\.(?:[a-z_][\w$]*)){0,2})"
    )

    matches = table_pattern.findall(cleaned_sql)

    # ------------------------------------------------------------------
    # 4) Filter out CTE references and normalize
    # ------------------------------------------------------------------
    tables = set()

    for identifier in matches:
        normalized = identifier.lower() if normalize_case else identifier
        base_name = normalized.split(".")[-1]

        # Exclude CTE references
        if base_name not in cte_names:
            tables.add(normalized)

    tables = [
        (db + ".dbo." if str(t).count(".") < 2 else "") +
        str(t).replace("<default>.", "")
        for t in tables
    ]

    return sorted(tables)


def process_all_views(db: str, connection_string: str, output_file="lineage.json"):

    try:
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
    except Exception as e:
        print ("Erro de conexão com o banco " + db)
        return []

    contador = 0

    cursor.execute("""
    SELECT 
        s.name AS schema_name,
        v.name AS object_name,
        m.definition
    FROM sys.views v
    JOIN sys.schemas s ON v.schema_id = s.schema_id
    JOIN sys.sql_modules m ON v.object_id = m.object_id
    """)

    rows = cursor.fetchall()

    results = []

    for row in rows:
        schema = row.schema_name
        name = row.object_name
        sql = row.definition

        if sql == None:
            print("Campo definition não disponível na tabela sys.sql_modules do banco " + db)
            return []

        result = process_single_object(db, schema, name, sql)

        if result["status"] == "error":
            print(f"❌ Error processing {schema}.{name}")
            print(result['erro'])
        else:
            print(f"✅ Processed {schema}.{name}")

        results.append(result)

        # contador += 1
        # if contador > 10:
        #     break

    print('Fim do loop pelo banco '+ db)

    return results



def update_file_with_new_objects(full_filename:str, new_results:list):

    # Load existing data
    if not os.path.exists(full_filename):
        existing = []
    else:
        with open(full_filename, "r") as f:
            existing = json.load(f)        

    # Convert existing list to dict keyed by "object"
    existing_map = {item["object"]: item for item in existing}

    # Update / insert new items
    for item in new_results:
        existing_map[item["object"]] = item

    # Convert back to list
    updated_list = list(existing_map.values())

    # Save back to file
    with open(full_filename, "w") as f:
        json.dump(updated_list, f, indent=2)






def main():
    db = sys.argv[1] if len(sys.argv) > 1 else "desig_cadastro"
    print(f"Using database: {db}")

    connection_string = r"DRIVER={ODBC Driver 17 for SQL Server}; SERVER=sqldesigprod; DATABASE=" + db + "; Trusted_Connection=yes;"

    output_file = "lineage.json"

    # IMPORTANT: now this function returns NOTHING
    results = process_all_views(db, connection_string, output_file)

    update_file_with_new_objects(output_file, results)

    # reload results from file
    with open(output_file, "r") as f:
        results = json.load(f)

    print("✅ Done")



if __name__ == "__main__":
    main()