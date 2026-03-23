from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

from .utilitarios import logger

# def save(self, *args, **kwargs):
#     if not self.username or not self.password:
#         self.username, self.password = autenticar_usuario()
#     super().save(*args, **kwargs)

class DatabaseConnection(models.Model):
    DATABASE_TYPE_CHOICES = [
        ('MSSQL', 'Microsoft SQL Server'),
        ('TERADATA', 'Teradata')
    ]
    name = models.CharField(max_length=100, unique=True)
    database_type = models.CharField(max_length=20, choices=DATABASE_TYPE_CHOICES)
    server = models.CharField(max_length=100)
    database = models.CharField(max_length=100)
    username = models.CharField(max_length=100, blank=True, null=True)
    password = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_crawled = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.name} ({self.database_type})"



class TableMetadata(models.Model):
    TABLE_TYPE_CHOICES = [
        ('TABLE', 'Table'),
        ('VIEW', 'View'),
    ]
    
    database_connection = models.ForeignKey(DatabaseConnection, on_delete=models.CASCADE, related_name='tables')
    name = models.CharField(max_length=100)
    schema = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=TABLE_TYPE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('database_connection', 'schema', 'name')
    
    def __str__(self):
        return f"{self.schema}.{self.name}"


class FieldMetadata(models.Model):
    table = models.ForeignKey(TableMetadata, on_delete=models.CASCADE, related_name='fields')
    name = models.CharField(max_length=100)
    data_type = models.CharField(max_length=100, blank=True, null=True)
    is_nullable = models.BooleanField(default=True, null=True)
    is_primary_key = models.BooleanField(default=False, null=True)
    is_foreign_key = models.BooleanField(default=False, null=True)
    foreign_key_table = models.CharField(max_length=200, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.table}.{self.name}"


class MetadataComment(models.Model):
    # Comentários podem ser feitos sobre: Tabela, Campo, ou Conexão.
    # Por solicitação, vamos referenciar Tabelas/Campos por NOME em vez de ID,
    # incluindo o connection_id (DatabaseConnection) na FK de Tabela para garantir unicidade.
    # Observação importante: o FieldMetadata não possui (connection, schema, table_name) embutidos,
    # portanto, a referência por nome para campos será armazenada, mas não haverá FK composta
    # de nível de banco diretamente para FieldMetadata (limitação do SQLite e do esquema atual).
    COMMENT_TYPE_CHOICES = [
        ('TABLE', 'Table'),
        ('FIELD', 'Field'),
        ('CONNECTION', 'Connection'),
    ]

    # Autor do comentário
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comments')

    # Conexão alvo (continua como FK por id)
    connection = models.ForeignKey(DatabaseConnection, on_delete=models.CASCADE, related_name='comments', null=True, blank=True)

    # Referência por NOME da Tabela (inclui schema). Esses campos substituem o antigo table_id.
    table_schema = models.CharField(max_length=100, null=True, blank=True)
    table_name = models.CharField(max_length=100, null=True, blank=True)

    # Referência por NOME do Campo. Substitui o antigo field_id.
    field_name = models.CharField(max_length=100, null=True, blank=True)

    # Tipo e conteúdo do comentário
    comment_type = models.CharField(max_length=12, choices=COMMENT_TYPE_CHOICES)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        # Representação legível considerando a nova estrutura baseada em nomes
        if self.comment_type == 'TABLE' and self.connection and self.table_schema and self.table_name:
            return f"Comment on {self.connection.name}:{self.table_schema}.{self.table_name}"
        elif self.comment_type == 'FIELD' and self.connection and self.table_schema and self.table_name and self.field_name:
            return f"Comment on {self.connection.name}:{self.table_schema}.{self.table_name}.{self.field_name}"
        elif self.connection:
            return f"Comment on {self.connection.name}"
        else:
            return "Comment"
