from django.db import migrations, models


# Esta migração realiza a transição de FKs baseadas em IDs (table_id, field_id)
# na tabela metadata_crawler_metadatacomment, para uma abordagem baseada em NOMES
# com inclusão de connection_id na FK composta da Tabela (connection_id, schema, name).
#
# Passos:
# 1) Adiciona colunas table_schema, table_name e field_name ao modelo.
# 2) Preenche essas colunas com dados derivados de table_id/field_id.
# 3) Reconstrói a tabela para remover table_id/field_id e adicionar a FK composta
#    para Tabela via (connection_id, table_schema, table_name) -> (database_connection_id, schema, name).
# 4) Mantém connection_id como FK para DatabaseConnection.
#
# Observação: devido ao esquema atual e limitações do SQLite, não é possível criar
# uma FK composta direta para FieldMetadata usando apenas nomes sem table_id.
# Portanto, armazenamos field_name sem uma FK de banco explícita; a integridade
# é mantida pela aplicação.


BACKFILL_SQL = r'''
-- Preenchimento das novas colunas a partir dos IDs existentes
UPDATE metadata_crawler_metadatacomment AS c
SET table_schema = (
    SELECT t.schema FROM metadata_crawler_tablemetadata t WHERE t.id = c.table_id
),
    table_name = (
    SELECT t.name FROM metadata_crawler_tablemetadata t WHERE t.id = c.table_id
),
    field_name = (
    SELECT f.name FROM metadata_crawler_fieldmetadata f WHERE f.id = c.field_id
)
WHERE c.table_id IS NOT NULL OR c.field_id IS NOT NULL;
'''


REBUILD_SQL = r'''
PRAGMA foreign_keys=off;

-- Criar tabela nova com colunas baseadas em nomes e FKs desejadas
CREATE TABLE "metadata_crawler_metadatacomment_new" (
    "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
    "comment_type" varchar(12) NOT NULL,
    "comment" text NOT NULL,
    "created_at" datetime NOT NULL,
    "updated_at" datetime NOT NULL,
    -- Autor
    "user_id" integer NOT NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED,
    -- Conexão alvo (FK simples por id)
    "connection_id" integer NULL REFERENCES "metadata_crawler_databaseconnection" ("id") DEFERRABLE INITIALLY DEFERRED,
    -- Referência por NOME da Tabela (composta com a conexão)
    "table_schema" varchar(100) NULL,
    "table_name" varchar(100) NULL,
    -- Referência por NOME do Campo (sem FK explícita por limitações do esquema)
    "field_name" varchar(100) NULL,
    -- FK composta para Tabela: (connection_id, table_schema, table_name)
    FOREIGN KEY ("connection_id", "table_schema", "table_name")
        REFERENCES "metadata_crawler_tablemetadata" ("database_connection_id", "schema", "name")
        DEFERRABLE INITIALLY DEFERRED
);

-- Copiar dados da tabela antiga para a nova, mapeando as colunas
INSERT INTO "metadata_crawler_metadatacomment_new" (
    id, comment_type, comment, created_at, updated_at, user_id, connection_id, table_schema, table_name, field_name
)
SELECT 
    c.id, c.comment_type, c.comment, c.created_at, c.updated_at, c.user_id,
    c.connection_id,
    c.table_schema, c.table_name,
    c.field_name
FROM "metadata_crawler_metadatacomment" c;

-- Remover a tabela antiga e renomear a nova
DROP TABLE "metadata_crawler_metadatacomment";
ALTER TABLE "metadata_crawler_metadatacomment_new" RENAME TO "metadata_crawler_metadatacomment";

PRAGMA foreign_keys=on;
'''


class Migration(migrations.Migration):

    dependencies = [
        ('metadata_crawler', '0005_fix_metadatacomment_fk'),
    ]

    operations = [
        # 1) Adicionar novas colunas ao modelo
        migrations.AddField(
            model_name='metadatacomment',
            name='table_schema',
            field=models.CharField(max_length=100, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='metadatacomment',
            name='table_name',
            field=models.CharField(max_length=100, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='metadatacomment',
            name='field_name',
            field=models.CharField(max_length=100, null=True, blank=True),
        ),

        # 2) Preencher novas colunas com dados existentes
        migrations.RunSQL(sql=BACKFILL_SQL, reverse_sql=""),

        # 3) Reconstruir a tabela para remover table_id/field_id e adicionar FK composta por nomes
        migrations.RunSQL(sql=REBUILD_SQL, reverse_sql=""),

        # 4) Informar ao Django que os antigos campos foram removidos do modelo
        migrations.RemoveField(
            model_name='metadatacomment',
            name='table',
        ),
        migrations.RemoveField(
            model_name='metadatacomment',
            name='field',
        ),
    ]

