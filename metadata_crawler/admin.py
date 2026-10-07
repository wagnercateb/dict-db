from django.contrib import admin
from .models import DatabaseConnection, TableMetadata, FieldMetadata, MetadataComment


@admin.register(DatabaseConnection)
class DatabaseConnectionAdmin(admin.ModelAdmin):
    list_display = ('server', 'database', 'last_crawled')
    search_fields = ('server', 'database')
    readonly_fields = ('created_at', 'updated_at', 'last_crawled')


@admin.register(TableMetadata)
class TableMetadataAdmin(admin.ModelAdmin):
    list_display = ('name', 'schema', 'type', 'database_connection')
    list_filter = ('type', 'database_connection')
    search_fields = ('name', 'schema')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(FieldMetadata)
class FieldMetadataAdmin(admin.ModelAdmin):
    list_display = ('name', 'table', 'data_type', 'is_nullable', 'is_primary_key', 'is_foreign_key')
    list_filter = ('is_nullable', 'is_primary_key', 'is_foreign_key', 'data_type')
    search_fields = ('name', 'table__name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(MetadataComment)
class MetadataCommentAdmin(admin.ModelAdmin):
    list_display = ('get_commented_object', 'comment_type', 'user', 'created_at')
    list_filter = ('comment_type', 'user')
    search_fields = ('comment', 'user__username')
    readonly_fields = ('created_at', 'updated_at')
    
    def get_commented_object(self, obj):
        if obj.comment_type == 'TABLE' and obj.connection and obj.table_schema and obj.table_name:
            return f"{obj.connection.database}:{obj.table_schema}.{obj.table_name}"
        elif obj.comment_type == 'FIELD' and obj.connection and obj.table_schema and obj.table_name and obj.field_name:
            return f"{obj.connection.database}:{obj.table_schema}.{obj.table_name}.{obj.field_name}"
        elif obj.connection:
            return f"{obj.connection.database}"
        return ""
    
    get_commented_object.short_description = 'Object'
