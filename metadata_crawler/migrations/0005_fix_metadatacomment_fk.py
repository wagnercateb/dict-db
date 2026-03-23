from django.db import migrations

SQL = r'''
PRAGMA foreign_keys=off;

CREATE TABLE "metadata_crawler_metadatacomment_new" (
    "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
    "comment_type" varchar(10) NOT NULL,
    "comment" text NOT NULL,
    "created_at" datetime NOT NULL,
    "updated_at" datetime NOT NULL,
    "field_id" bigint NULL REFERENCES "metadata_crawler_fieldmetadata" ("id") DEFERRABLE INITIALLY DEFERRED,
    "user_id" integer NOT NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED,
    "table_id" bigint NULL REFERENCES "metadata_crawler_tablemetadata" ("id") DEFERRABLE INITIALLY DEFERRED,
    connection_id INTEGER
);

INSERT INTO "metadata_crawler_metadatacomment_new" SELECT * FROM "metadata_crawler_metadatacomment";

DROP TABLE "metadata_crawler_metadatacomment";
ALTER TABLE "metadata_crawler_metadatacomment_new" RENAME TO "metadata_crawler_metadatacomment";

PRAGMA foreign_keys=on;
'''

class Migration(migrations.Migration):

    dependencies = [
        ('metadata_crawler', '0004_alter_fieldmetadata_data_type_and_more'),
    ]

    operations = [
        migrations.RunSQL(sql=SQL, reverse_sql=""),
    ]