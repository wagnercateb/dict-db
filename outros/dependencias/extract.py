"""Extração de dependências de views e de modificadores DML (standalone).

Rode localmente (usa autenticação integrada do Windows):

    python extract.py [nome_do_banco]

Gera/atualiza:

* ``lineage.json``   – dependências das views.
* ``modifiers.json`` – comandos DML (INSERT, SELECT ... INTO, UPDATE, DELETE)
  executados por funções/stored procedures, agrupados por tabela afetada.

A lógica de parsing é compartilhada com o crawler Django e vive em
``metadata_crawler/lineage.py``.
"""

import os
import sys

import pyodbc

# Garante o import do pacote do projeto ao rodar este script diretamente.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from metadata_crawler.lineage import (  # noqa: E402
    build_table_modifier_index,
    extract_routine_modifiers,
    extract_view_dependencies,
    list_accessible_databases,
    load_json,
    merge_records,
    write_json,
)


def process_all_views(db: str, connection_string: str, output_file: str = "lineage.json"):
    """Processa todas as views do banco e retorna suas dependências."""
    try:
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
    except Exception:
        print("Erro de conexão com o banco " + db)
        return []

    try:
        results = extract_view_dependencies(db, cursor)
    finally:
        conn.close()

    for item in results:
        if item.get("status") == "error":
            print(f"❌ Error processing {item['object']}")
            if item.get("erro"):
                print(item["erro"])
        else:
            print(f"✅ Processed {item['object']}")

    print("Fim do loop pelo banco " + db)
    return results


def process_all_routines(db: str, connection_string: str):
    """Processa funções/stored procedures e retorna os DMLs por tabela.

    Varre as rotinas de todos os bancos acessíveis do servidor para capturar
    modificações cross-database (uma SP em outro banco que grava neste).
    """
    try:
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
    except Exception:
        print("Erro de conexão com o banco " + db)
        return []

    try:
        try:
            databases = list_accessible_databases(cursor)
        except Exception:
            databases = [db]
        if db not in databases:
            databases.append(db)

        routines = []
        for routine_db in databases:
            try:
                routines.extend(extract_routine_modifiers(routine_db, cursor))
            except Exception as exc:
                print(f"⚠️  Ignorando banco {routine_db}: {exc}")
    finally:
        conn.close()

    print(
        f"Fim do loop de rotinas ({len(routines)} com DML) "
        f"varrendo {len(databases)} banco(s)"
    )
    return build_table_modifier_index(routines)


def update_file_with_new_objects(full_filename: str, new_results: list, key: str = "object"):
    """Atualiza/insere registros no JSON mantendo os existentes."""
    existing = load_json(full_filename)
    updated = merge_records(existing, new_results, key)
    write_json(full_filename, updated)


def main():
    db = sys.argv[1] if len(sys.argv) > 1 else "desig_cadastro"
    print(f"Using database: {db}")

    connection_string = (
        r"DRIVER={ODBC Driver 17 for SQL Server}; SERVER=sqldesigprod; "
        r"DATABASE=" + db + "; Trusted_Connection=yes;"
    )

    views = process_all_views(db, connection_string, "lineage.json")
    update_file_with_new_objects("lineage.json", views, "object")

    modifiers = process_all_routines(db, connection_string)
    update_file_with_new_objects("modifiers.json", modifiers, "table")

    print("✅ Done")


if __name__ == "__main__":
    main()
