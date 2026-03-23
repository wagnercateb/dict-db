import sqlite3
import os
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'dict-db.sqlite3')
DB_PATH = os.path.abspath(DB_PATH)
print('DB_PATH:', DB_PATH)
con = sqlite3.connect(DB_PATH)
cur = con.cursor()
cur.execute("SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name LIKE '%fieldmetadata%' OR sql LIKE '%fieldmetadata%'")
rows = cur.fetchall()
print('objects_count:', len(rows))
for i, (typ, name, tbl, sql) in enumerate(rows, 1):
    print(f'[{i}] type={typ} name={name} tbl={tbl}')
    print(sql or '')
    print('----')
cur.execute("SELECT type, name, tbl_name, sql FROM sqlite_master WHERE sql LIKE '%_old%' OR name LIKE '%_old%'")
rows2 = cur.fetchall()
print('old_refs_count:', len(rows2))
for i, (typ, name, tbl, sql) in enumerate(rows2, 1):
    print(f'OLD[{i}] type={typ} name={name} tbl={tbl}')
    print(sql or '')
    print('----')
con.close()