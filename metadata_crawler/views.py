from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse, HttpResponseForbidden
from django.urls import reverse
from django.core.cache import cache

from .models import DatabaseConnection, TableMetadata, FieldMetadata, MetadataComment
from .forms import DatabaseConnectionForm, MetadataCommentForm, SearchForm, AdvancedSearchForm, CrawlCredentialsForm
from .utils import DatabaseCrawler, search_metadata
from .utilitarios import logger

import traceback
import os
import json
import pyodbc
import platform
import subprocess

from django.conf import settings
from django.http import FileResponse, Http404


def home(request):
    """Página inicial com busca e lista de conexões"""
    connections = DatabaseConnection.objects.all().order_by('name').prefetch_related('comments__user')
    search_form = SearchForm()
    context = {
        'connections': connections,
        'search_form': search_form,
        'can_add_connection': request.session.get('can_add_connection', False),
    }
    return render(request, 'metadata_crawler/home.html', context)


def add_connection(request):
    """Adicionar uma nova conexão ao banco de dados"""
    if request.method == 'POST':
        form = DatabaseConnectionForm(request.POST)
        if form.is_valid():
            conn = form.save()
            # Comentário opcional da conexão
            comment_text = (request.POST.get('connection_comment') or '').strip()
            if comment_text and request.user.is_authenticated:
                MetadataComment.objects.create(
                    user=request.user,
                    connection=conn,
                    comment_type='CONNECTION',
                    comment=comment_text,
                )
            messages.success(request, 'Conexão adicionada com sucesso!')
            return redirect('home')
    else:
        form = DatabaseConnectionForm()
    return render(request, 'metadata_crawler/add_connection.html', {'form': form})


def edit_connection(request, connection_id):
    """Editar uma conexão existente"""
    connection = get_object_or_404(DatabaseConnection, id=connection_id)
    if not request.session.get('can_add_connection', False):
        messages.error(request, 'Você não tem permissão para editar conexões.')
        return redirect('connection_detail', connection_id=connection.id)
    if request.method == 'POST':
        form = DatabaseConnectionForm(request.POST, instance=connection)
        if form.is_valid():
            conn = form.save()
            # Comentário opcional da conexão (adiciona como novo comentário)
            comment_text = (request.POST.get('connection_comment') or '').strip()
            if comment_text and request.user.is_authenticated:
                MetadataComment.objects.create(
                    user=request.user,
                    connection=conn,
                    comment_type='CONNECTION',
                    comment=comment_text,
                )
            messages.success(request, 'Conexão atualizada com sucesso!')
            return redirect('connection_detail', connection_id=connection.id)
    else:
        form = DatabaseConnectionForm(instance=connection)
    return render(request, 'metadata_crawler/add_connection.html', {
        'form': form,
        'is_edit': True,
        'connection': connection,
    })

def connection_detail(request, connection_id):
    """Visualizar detalhes da conexão do banco de dados com comentários"""
    connection = get_object_or_404(DatabaseConnection, id=connection_id)
    tables = TableMetadata.objects.filter(database_connection=connection).order_by('schema', 'name')
    
    # Pre-fetch comments for each table to show in the column toggle
    for table in tables:
        table.latest_comments = MetadataComment.objects.filter(
            Q(connection=table.database_connection) | Q(connection__isnull=True),
            comment_type='TABLE',
            table_schema=table.schema,
            table_name=table.name
        ).order_by('-created_at')[:3]

    comments = MetadataComment.objects.filter(connection=connection, comment_type='CONNECTION').order_by('-created_at')

    # Lidar com o formulário de novo comentário (CONNECTION)
    if request.method == 'POST' and request.user.is_authenticated:
        comment_form = MetadataCommentForm(request.POST)
        if comment_form.is_valid():
            comment = comment_form.save(commit=False)
            comment.user = request.user
            comment.connection = connection
            comment.comment_type = 'CONNECTION'
            comment.save()
            messages.success(request, 'Comentário adicionado com sucesso!')
            return redirect('connection_detail', connection_id=connection.id)
    else:
        comment_form = MetadataCommentForm()
    
    context = {
        'connection': connection,
        'tables': tables,
        'comments': comments,
        'comment_form': comment_form,
    }
    return render(request, 'metadata_crawler/connection_detail.html', context)


def crawl_database(request, connection_id):
    """Rastrear metadados do banco de dados específico, solicitando credenciais runtime"""
    connection = get_object_or_404(DatabaseConnection, id=connection_id)

    if request.method == 'POST':
        form = CrawlCredentialsForm(request.POST)
        if form.is_valid():
            runtime_username = form.cleaned_data.get('username') or ''
            runtime_password = form.cleaned_data.get('password') or ''

            # Validação específica: Teradata requer credenciais
            if connection.database_type == 'TERADATA' and (not runtime_username or not runtime_password):
                messages.error(request, 'Para Teradata, informe usuário e senha (LDAP).')
                return render(request, 'metadata_crawler/crawl_credentials.html', {
                    'connection': connection,
                    'form': form,
                })

            try:
                crawler = DatabaseCrawler(connection, runtime_username=runtime_username, runtime_password=runtime_password)
                crawler.crawl()
                messages.success(request, 'Rastreamento concluído com sucesso!')
                return redirect('connection_detail', connection_id=connection.id)
            except Exception as e:
                logger.error(f"Erro ao rastrear: {e}\n{traceback.format_exc()}")
                messages.error(request, f"Erro ao rastrear: {e}")
                return render(request, 'metadata_crawler/crawl_credentials.html', {
                    'connection': connection,
                    'form': form,
                })
    else:
        # GET: exibir formulário de credenciais
        initial_username = connection.username or ''
        form = CrawlCredentialsForm(initial={'username': initial_username})
        return render(request, 'metadata_crawler/crawl_credentials.html', {
            'connection': connection,
            'form': form,
        })


def table_detail(request, table_id):
    """Visualizar detalhes da tabela/view"""
    table = get_object_or_404(TableMetadata, id=table_id)
    fields = FieldMetadata.objects.filter(table=table).order_by('name')
    
    # Pre-fetch comments for each field to show in the column toggle
    for field in fields:
        field.latest_comments = MetadataComment.objects.filter(
            Q(connection=field.table.database_connection) | Q(connection__isnull=True),
            comment_type='FIELD',
            table_schema=field.table.schema,
            table_name=field.table.name,
            field_name=field.name
        ).order_by('-created_at')[:3]

    # Busca comentários de TABELA por conexão + schema + nome
    # Fallback: se houver comentários com connection=None mas schema/nome iguais, também mostra
    comments = MetadataComment.objects.filter(
        Q(connection=table.database_connection) | Q(connection__isnull=True),
        comment_type='TABLE',
        table_schema=table.schema,
        table_name=table.name,
    ).order_by('-created_at')
    
    # Lidar com o formulário de novo comentário
    if request.method == 'POST' and request.user.is_authenticated:
        comment_form = MetadataCommentForm(request.POST)
        if comment_form.is_valid():
            comment = comment_form.save(commit=False)
            # Preenche novos campos baseados em NOME, incluindo conexão
            comment.user = request.user
            comment.connection = table.database_connection
            comment.table_schema = table.schema
            comment.table_name = table.name
            comment.comment_type = 'TABLE'
            comment.save()
            messages.success(request, 'Comentário adicionado com sucesso!')
            return redirect('table_detail', table_id=table.id)
    else:
        comment_form = MetadataCommentForm()
    
    # Build the lookup key for the lineage viewer:
    # db  = database name (first part before dot, lowercased), matches lineage.json prefix
    # tbl = schema.name (three-part: db.schema.name), lowercased
    lineage_db = (table.database_connection.database or '').strip().lower()
    lineage_tbl = f"{lineage_db}.{table.schema}.{table.name}".lower()

    context = {
        'table': table,
        'fields': fields,
        'comments': comments,
        'comment_form': comment_form,
        'lineage_db': lineage_db,
        'lineage_tbl': lineage_tbl,
    }
    return render(request, 'metadata_crawler/table_detail.html', context)


def field_detail(request, field_id):
    """Visualizar detalhes do campo"""
    field = get_object_or_404(FieldMetadata, id=field_id)
    # Busca comentários de CAMPO por conexão + schema + nome da tabela + nome do campo
    # Fallback: se houver comentários com connection=None mas schema/nome/campo iguais, também mostra
    comments = MetadataComment.objects.filter(
        Q(connection=field.table.database_connection) | Q(connection__isnull=True),
        comment_type='FIELD',
        table_schema=field.table.schema,
        table_name=field.table.name,
        field_name=field.name,
    ).order_by('-created_at')
    
    # Lidar com o formulário de novo comentário
    if request.method == 'POST' and request.user.is_authenticated:
        comment_form = MetadataCommentForm(request.POST)
        if comment_form.is_valid():
            comment = comment_form.save(commit=False)
            # Preenche novos campos baseados em NOME, incluindo conexão
            comment.user = request.user
            comment.connection = field.table.database_connection
            comment.table_schema = field.table.schema
            comment.table_name = field.table.name
            comment.field_name = field.name
            comment.comment_type = 'FIELD'
            comment.save()
            messages.success(request, 'Comentário adicionado com sucesso!')
            return redirect('field_detail', field_id=field.id)
    else:
        comment_form = MetadataCommentForm()
    
    context = {
        'field': field,
        'comments': comments,
        'comment_form': comment_form,
    }
    return render(request, 'metadata_crawler/field_detail.html', context)


def search_results(request, query=None):
    """Resultados simples de pesquisa"""
    if request.method == 'GET' and 'q' in request.GET:
        query = request.GET.get('q', '').strip()
        if not query:
            messages.info(request, 'Informe um termo para pesquisar.')
            return redirect('home')
        # Redireciona para URL amigável: /search/<query>/
        return redirect('search_results', query=query)

    results = search_metadata(query)
    tables = results['tables']
    fields = results['fields']
    comments = results['comments']

    # Pre-fetch comments for simple search tables to show in the column toggle
    for table in tables:
        table.latest_comments = MetadataComment.objects.filter(
            Q(connection=table.database_connection) | Q(connection__isnull=True),
            comment_type='TABLE',
            table_schema=table.schema,
            table_name=table.name
        ).order_by('-created_at')[:3]

    # Hidratar objetos alvo dos comentários para compatibilidade com templates
    # Após a migração, MetadataComment armazena nomes; resolvemos objetos aqui.
    def _hydrate_comment_targets(comments_qs):
        table_keys = []
        field_keys = []
        for c in comments_qs:
            if c.comment_type == 'TABLE' and c.connection_id and c.table_schema and c.table_name:
                table_keys.append((c.connection_id, c.table_schema, c.table_name))
            elif c.comment_type == 'FIELD' and c.connection_id and c.table_schema and c.table_name and c.field_name:
                field_keys.append((c.connection_id, c.table_schema, c.table_name, c.field_name))

        table_map = {}
        field_map = {}
        if table_keys:
            conn_ids = {k[0] for k in table_keys}
            schemas = {k[1] for k in table_keys}
            names = {k[2] for k in table_keys}
            tables_found = TableMetadata.objects.filter(
                database_connection_id__in=conn_ids,
                schema__in=schemas,
                name__in=names,
            ).select_related('database_connection')
            table_map = {(t.database_connection_id, t.schema, t.name): t for t in tables_found}
        if field_keys:
            conn_ids_f = {k[0] for k in field_keys}
            schemas_f = {k[1] for k in field_keys}
            tnames_f = {k[2] for k in field_keys}
            fnames_f = {k[3] for k in field_keys}
            fields_found = FieldMetadata.objects.filter(
                table__database_connection_id__in=conn_ids_f,
                table__schema__in=schemas_f,
                table__name__in=tnames_f,
                name__in=fnames_f,
            ).select_related('table', 'table__database_connection')
            field_map = {(f.table.database_connection_id, f.table.schema, f.table.name, f.name): f for f in fields_found}

        for c in comments_qs:
            if c.comment_type == 'TABLE':
                c.table = table_map.get((c.connection_id, c.table_schema, c.table_name))
            elif c.comment_type == 'FIELD':
                c.field = field_map.get((c.connection_id, c.table_schema, c.table_name, c.field_name))

    _hydrate_comment_targets(comments)

    # tokens para destaque
    table_tokens = query.split() if query else []
    field_tokens = table_tokens
    comment_tokens = table_tokens

    return render(request, 'metadata_crawler/search_results.html', {
        'query': query,
        'tables': tables,
        'fields': fields,
        'comments': comments,
        'table_tokens': table_tokens,
        'field_tokens': field_tokens,
        'comment_tokens': comment_tokens,
    })


def advanced_search(request):
    """Pesquisa avançada com múltiplos filtros"""
    tables = fields = comments = None
    form = AdvancedSearchForm(request.GET or None)

    if form.is_valid():
        # Connections filter
        selected_connections = form.cleaned_data.get('connections') or []
        selected_connections = [int(cid) for cid in selected_connections]

        # Authors filter
        selected_authors = form.cleaned_data.get('comment_authors') or []
        selected_authors = [int(uid) for uid in selected_authors]

        # Tabelas
        table_q = Q()
        name_tokens = [t for t in (form.cleaned_data.get('table_name') or '').split() if t]
        schema_tokens = [t for t in (form.cleaned_data.get('table_schema') or '').split() if t]
        types = form.cleaned_data.get('table_type') or []
        has_table_text_filters = bool(name_tokens or schema_tokens)
        for t in name_tokens:
            table_q &= Q(name__icontains=t)
        for t in schema_tokens:
            table_q &= Q(schema__icontains=t)
        if types:
            table_q &= Q(type__in=types)
        if selected_connections:
            table_q &= Q(database_connection__id__in=selected_connections)
        # Apenas lista tabelas quando houver texto nos filtros de tabela/view
        if has_table_text_filters:
            tables = TableMetadata.objects.filter(table_q).distinct()

        # Campos
        field_q = Q()
        field_name = form.cleaned_data.get('field_name')
        field_data_type = form.cleaned_data.get('field_data_type')
        field_table_types = form.cleaned_data.get('field_table_type') or []
        fname_tokens = [t for t in (field_name or '').split() if t]
        ftype_tokens = [t for t in (field_data_type or '').split() if t]
        has_field_text_filters = bool(fname_tokens or ftype_tokens)
        for t in fname_tokens:
            field_q &= Q(name__icontains=t)
        for t in ftype_tokens:
            field_q &= Q(data_type__icontains=t)
        # Apply table type filter for fields
        if field_table_types:
            field_q &= Q(table__type__in=field_table_types)
        # Apply connection filter through table relationship
        if selected_connections:
            field_q &= Q(table__database_connection__id__in=selected_connections)
        # Apply exclude table terms
        exclude_raw = form.cleaned_data.get('exclude_table_terms') or ''
        exclude_terms = [t.strip() for t in exclude_raw.split(',') if t.strip()]
        if exclude_terms:
            ex_q = Q()
            for t in exclude_terms:
                ex_q |= Q(table__name__icontains=t)
            field_q &= ~ex_q
        # Apenas lista campos quando houver texto nos filtros de campos
        if has_field_text_filters:
            fields = FieldMetadata.objects.filter(field_q).distinct()

        # Comentários: segue a mesma lógica dos campos (dispara apenas com texto no comentário)
        comment_q = Q()
        comment_text = form.cleaned_data.get('comment_text')
        comment_types = form.cleaned_data.get('comment_type') or []
        ctext_tokens = [t for t in (comment_text or '').split() if t]
        
        # Filtros de texto (OR entre palavras, AND entre filtros)
        if ctext_tokens:
            text_or_q = Q()
            for t in ctext_tokens:
                text_or_q |= Q(comment__icontains=t)
            comment_q &= text_or_q
        
        # Filtro de tipos de comentário
        if comment_types:
            comment_q &= Q(comment_type__in=comment_types)
            
        # Filtro de conexões
        # Se o usuário selecionou TODAS as conexões, não filtramos por ID para permitir
        # que comentários legados (sem connection_id) também apareçam.
        all_connections_count = len(form.fields['connections'].choices)
        if selected_connections and len(selected_connections) < all_connections_count:
            comment_q &= Q(connection__id__in=selected_connections)
            
        # Filtro de autores
        all_authors_count = len(form.fields['comment_authors'].choices)
        if selected_authors and len(selected_authors) < all_authors_count:
            comment_q &= Q(user__id__in=selected_authors)
            
        # Filtros cruzados (Tabela/View e Campo) - Devem ser aplicados apenas se preenchidos
        # e não devem excluir comentários que não possuem esses campos (como CONNECTION) 
        # a menos que o usuário queira filtrar especificamente por eles.
        cross_q = Q()
        if name_tokens:
            temp_or_q = Q()
            for t in name_tokens:
                temp_or_q |= Q(table_name__icontains=t)
            cross_q &= temp_or_q
        if schema_tokens:
            temp_or_q = Q()
            for t in schema_tokens:
                temp_or_q |= Q(table_schema__icontains=t)
            cross_q &= temp_or_q
        if fname_tokens:
            temp_or_q = Q()
            for t in fname_tokens:
                temp_or_q |= Q(field_name__icontains=t)
            cross_q &= temp_or_q
        
        if cross_q.children:
            # Se houver filtros cruzados, aplicamos eles apenas aos tipos que possuem esses campos,
            # mas permitimos que comentários de CONNECTION apareçam (se estiverem selecionados).
            if 'CONNECTION' in comment_types or not comment_types:
                comment_q &= (cross_q | Q(comment_type='CONNECTION'))
            else:
                comment_q &= cross_q
            
        # Determine if we should show comments based on any filter being present
        has_any_comment_filter = bool(
            ctext_tokens or 
            cross_q.children or 
            (len(comment_types) < 3 if comment_types else False) or
            (len(selected_connections) < all_connections_count if selected_connections else False) or
            (len(selected_authors) < all_authors_count if selected_authors else False)
        )
        
        if has_any_comment_filter:
            comments = MetadataComment.objects.filter(comment_q).distinct()
            
            # Hidratação dos objetos alvo (Table/Field) para exibição de links
            def _hydrate_comment_targets(comments_qs):
                table_keys = []
                field_keys = []
                for c in comments_qs:
                    if c.comment_type == 'TABLE' and c.table_schema and c.table_name:
                        # Se não houver connection_id, ainda tentamos hidratar se houver apenas uma tabela com esse nome
                        if c.connection_id:
                            table_keys.append((c.connection_id, c.table_schema, c.table_name))
                    elif c.comment_type == 'FIELD' and c.table_schema and c.table_name and c.field_name:
                        if c.connection_id:
                            field_keys.append((c.connection_id, c.table_schema, c.table_name, c.field_name))

                table_map = {}
                field_map = {}
                if table_keys:
                    conn_ids = {k[0] for k in table_keys}
                    schemas = {k[1] for k in table_keys}
                    names = {k[2] for k in table_keys}
                    tables_found = TableMetadata.objects.filter(
                        database_connection_id__in=conn_ids,
                        schema__in=schemas,
                        name__in=names,
                    ).select_related('database_connection')
                    table_map = {(t.database_connection_id, t.schema, t.name): t for t in tables_found}
                if field_keys:
                    conn_ids_f = {k[0] for k in field_keys}
                    schemas_f = {k[1] for k in field_keys}
                    tnames_f = {k[2] for k in field_keys}
                    fnames_f = {k[3] for k in field_keys}
                    fields_found = FieldMetadata.objects.filter(
                        table__database_connection_id__in=conn_ids_f,
                        table__schema__in=schemas_f,
                        table__name__in=tnames_f,
                        name__in=fnames_f,
                    ).select_related('table', 'table__database_connection')
                    field_map = {(f.table.database_connection_id, f.table.schema, f.table.name, f.name): f for f in fields_found}

                for c in comments_qs:
                    if c.comment_type == 'TABLE':
                        c.table = table_map.get((c.connection_id, c.table_schema, c.table_name))
                        # Fallback se não houver connection_id (comentários órfãos ou legados)
                        if not c.table and not c.connection_id and c.table_schema and c.table_name:
                            c.table = TableMetadata.objects.filter(schema=c.table_schema, name=c.table_name).first()
                    elif c.comment_type == 'FIELD':
                        c.field = field_map.get((c.connection_id, c.table_schema, c.table_name, c.field_name))
                        # Fallback
                        if not c.field and not c.connection_id and c.table_schema and c.table_name and c.field_name:
                            c.field = FieldMetadata.objects.filter(table__schema=c.table_schema, table__name=c.table_name, name=c.field_name).first()

            _hydrate_comment_targets(comments)

    return render(request, 'metadata_crawler/advanced_search.html', {
        'form': form,
        'tables': tables,
        'fields': fields,
        'comments': comments,
        # tokens for highlighting
        'table_tokens': (name_tokens if 'name_tokens' in locals() else []) + (schema_tokens if 'schema_tokens' in locals() else []),
        'field_tokens': (fname_tokens if 'fname_tokens' in locals() else []) + (ftype_tokens if 'ftype_tokens' in locals() else []),
        'comment_tokens': (ctext_tokens if 'ctext_tokens' in locals() else []),
    })


def edit_comment(request, comment_id):
    """Editar um comentário existente"""
    comment = get_object_or_404(MetadataComment, id=comment_id)
    
    # Verificar se o usuário atual é o criador do comentário
    if request.user != comment.user:
        return HttpResponseForbidden("Só quem criou um comentário pode editá-lo.")
    
    if request.method == 'POST':
        form = MetadataCommentForm(request.POST, instance=comment)
        if form.is_valid():
            form.save()
            messages.success(request, "Comentário atualizado com sucesso.")
            
            # Redirecionar para a página apropriada com base no tipo de comentário
            # Caso de TABLE
            if comment.comment_type == 'TABLE' and comment.table_schema and comment.table_name:
                q_table = Q(schema=comment.table_schema, name=comment.table_name)
                if comment.connection:
                    q_table &= Q(database_connection=comment.connection)
                table = TableMetadata.objects.filter(q_table).first()
                if table:
                    return redirect('table_detail', table_id=table.id)
                elif comment.connection:
                    return redirect('connection_detail', connection_id=comment.connection.id)
            
            # Caso de FIELD
            elif comment.comment_type == 'FIELD' and comment.table_schema and comment.table_name and comment.field_name:
                q_table = Q(schema=comment.table_schema, name=comment.table_name)
                if comment.connection:
                    q_table &= Q(database_connection=comment.connection)
                table = TableMetadata.objects.filter(q_table).first()
                if table:
                    field_obj = FieldMetadata.objects.filter(table=table, name=comment.field_name).first()
                    if field_obj:
                        return redirect('field_detail', field_id=field_obj.id)
                    return redirect('table_detail', table_id=table.id)
                elif comment.connection:
                    return redirect('connection_detail', connection_id=comment.connection.id)
            
            # Caso de CONNECTION ou fallback
            if comment.connection:
                return redirect('connection_detail', connection_id=comment.connection.id)
            else:
                return redirect('home')
    else:
        form = MetadataCommentForm(instance=comment)
    
    # Hydrate table/field for the template cancel button and display
    target_table = None
    target_field = None
    
    if comment.comment_type == 'TABLE' and comment.table_schema and comment.table_name:
        q_table = Q(schema=comment.table_schema, name=comment.table_name)
        if comment.connection:
            q_table &= Q(database_connection=comment.connection)
        target_table = TableMetadata.objects.filter(q_table).first()
        
    elif comment.comment_type == 'FIELD' and comment.table_schema and comment.table_name and comment.field_name:
        q_table = Q(schema=comment.table_schema, name=comment.table_name)
        if comment.connection:
            q_table &= Q(database_connection=comment.connection)
        target_table = TableMetadata.objects.filter(q_table).first()
        if target_table:
            target_field = FieldMetadata.objects.filter(table=target_table, name=comment.field_name).first()

    return render(request, 'metadata_crawler/edit_comment.html', {
        'form': form,
        'comment': comment,
        'target_table': target_table,
        'target_field': target_field,
    })


def delete_comment(request, comment_id):
    """Excluir um comentário existente"""
    comment = get_object_or_404(MetadataComment, id=comment_id)
    
    # Verificar se o usuário atual é o criador do comentário
    if request.user != comment.user:
        return HttpResponseForbidden("Só quem criou um comentário pode editá-lo")
    
    # Armazenar a referência antes de excluir
    redirect_url = reverse('home')
    
    if comment.comment_type == 'TABLE' and comment.table_schema and comment.table_name:
        q_table = Q(schema=comment.table_schema, name=comment.table_name)
        if comment.connection:
            q_table &= Q(database_connection=comment.connection)
        
        table = TableMetadata.objects.filter(q_table).first()
        if table:
            redirect_url = reverse('table_detail', args=[table.id])
        elif comment.connection:
            redirect_url = reverse('connection_detail', args=[comment.connection.id])
            
    elif comment.comment_type == 'FIELD' and comment.table_schema and comment.table_name and comment.field_name:
        q_table = Q(schema=comment.table_schema, name=comment.table_name)
        if comment.connection:
            q_table &= Q(database_connection=comment.connection)
            
        table = TableMetadata.objects.filter(q_table).first()
        if table:
            field_obj = FieldMetadata.objects.filter(table=table, name=comment.field_name).first()
            if field_obj:
                redirect_url = reverse('field_detail', args=[field_obj.id])
            else:
                redirect_url = reverse('table_detail', args=[table.id])
        elif comment.connection:
            redirect_url = reverse('connection_detail', args=[comment.connection.id])
    
    elif comment.comment_type == 'CONNECTION' and comment.connection:
        redirect_url = reverse('connection_detail', args=[comment.connection.id])
    
    # Excluir o comentário
    comment.delete()
    messages.success(request, "Comentário excluído com sucesso.")
    
    return redirect(redirect_url)


def _mask_conn_str(conn_str: str) -> str:
    # simple masking for PWD
    return conn_str.replace('PWD=', 'PWD=***').replace('Password=', 'Password=***')


def _run_kinit(principal: str, password: str = None, keytab_b64: str = None):
    """Run kinit using either password or keytab (base64). Linux only. Returns dict with outputs."""
    result = {
        'executed': False,
        'method': None,
        'stdout': '',
        'stderr': '',
        'klist': ''
    }
    if platform.system().lower().startswith('win'):
        result['stderr'] = 'kinit não disponível no Windows; pulando.'
        return result
    if not principal:
        result['stderr'] = 'Principal não informado para kinit.'
        return result
    try:
        if keytab_b64:
            import base64, tempfile
            fd, path = tempfile.mkstemp(prefix='keytab_', suffix='.kt')
            with os.fdopen(fd, 'wb') as f:
                f.write(base64.b64decode(keytab_b64))
            proc = subprocess.Popen(['kinit', '-kt', path, principal], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            out, err = proc.communicate()
            result.update({'executed': True, 'method': 'keytab', 'stdout': out or '', 'stderr': err or ''})
            try:
                os.remove(path)
            except Exception:
                pass
        elif password:
            proc = subprocess.Popen(['kinit', principal], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            out, err = proc.communicate(input=password + '\n')
            result.update({'executed': True, 'method': 'password', 'stdout': out or '', 'stderr': err or ''})
        # show creds
        proc = subprocess.Popen(['klist'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        klist_out, _ = proc.communicate()
        result['klist'] = klist_out
    except Exception as e:
        result['stderr'] = str(e)
    return result


def test_connections(request):
    """Página de teste de conexões MSSQL/Teradata com múltiplos cenários."""
    context = {
        'results': [],
        'env': {
            'os': platform.system(),
            'driver_default': os.getenv('MSSQL_DRIVER', 'ODBC Driver 17 for SQL Server'),
        }
    }
    if request.method == 'POST':
        db_type = request.POST.get('database_type')  # MSSQL or TERADATA
        server = request.POST.get('server')
        database = request.POST.get('database')
        auth_methods = request.POST.getlist('auth_methods')
        username = request.POST.get('username')
        password = request.POST.get('password')
        principal = request.POST.get('principal')
        keytab_b64 = request.POST.get('keytab_b64')
        encrypt = request.POST.get('encrypt')  # yes/no/empty
        trust = request.POST.get('trust_server_certificate')  # yes/no/empty
        driver = request.POST.get('driver') or os.getenv('MSSQL_DRIVER', 'ODBC Driver 17 for SQL Server')
        server_spn = request.POST.get('server_spn')
        logmech = request.POST.get('logmech')  # Teradata python driver

        for method in auth_methods:
            res = {
                'database_type': db_type,
                'server': server,
                'database': database,
                'auth_method': method,
                'username': username,
                'principal': principal,
                'encrypt': encrypt,
                'trust_server_certificate': trust,
                'driver': driver,
                'server_spn': server_spn,
                'conn_str': '',
                'conn_str_masked': '',
                'success': False,
                'error': '',
                'details': {},
            }

            try:
                if db_type == 'MSSQL':
                    # Ensure driver is wrapped in braces; avoid formatting pitfalls
                    driver_braced = driver.strip()
                    if not driver_braced.startswith('{'):
                        driver_braced = '{' + driver_braced + '}'
                    conn_str = f"DRIVER={driver_braced};SERVER={server};DATABASE={database};"
                    if encrypt:
                        conn_str += f"Encrypt={encrypt};"
                    if trust:
                        conn_str += f"TrustServerCertificate={trust};"
                    if server_spn:
                        conn_str += f"ServerSPN={server_spn};"
                    if method == 'mssql_integrated':
                        if os.name == 'nt':
                            conn_str += "Trusted_Connection=yes;Integrated Security=SSPI;"
                        else:
                            # Kerberos: optionally perform kinit
                            kin = _run_kinit(principal, password=password, keytab_b64=keytab_b64)
                            res['details']['kinit'] = kin
                            conn_str += "Trusted_Connection=yes;"
                    elif method == 'mssql_sql_auth':
                        conn_str += f"UID={username};PWD={password};"
                    elif method == 'mssql_sqlserver_native':
                        # Native SQL Server driver name works on Windows; on Linux typically unavailable
                        native_drv = '{SQL Server}'
                        conn_str = f"DRIVER={native_drv};Server={server};Database={database};Trusted_Connection=yes;"
                        if not platform.system().lower().startswith('win'):
                            raise Exception('Driver {SQL Server} não disponível em Linux. Use ODBC Driver 17/18.')
                    else:
                        raise Exception('Método de autenticação MSSQL desconhecido')

                elif db_type == 'TERADATA':
                    if method == 'td_python_json':
                        # Use teradatasql Python driver (JSON connection string)
                        try:
                            import teradatasql  # type: ignore
                        except Exception as imp_err:
                            raise Exception(f"teradatasql não instalado: {imp_err}. Instale 'teradatasql' no ambiente.")
                        json_conn = (
                            '{"host":"' + (server or '') + '", '
                            '"logmech":"' + (logmech or 'LDAP') + '", '
                            '"tmode":"TERA", '
                            '"user":"' + (username or '') + '", '
                            '"password":"' + (password or '') + '"}'
                        )
                        res['conn_str'] = json_conn
                        res['conn_str_masked'] = _mask_conn_str(json_conn)
                        con = teradatasql.connect(json_conn)
                        cur = con.cursor()
                        cur.execute('SELECT 1')
                        cur.fetchone()
                        con.close()
                        res['success'] = True
                        context['results'].append(res)
                        continue  # Skip ODBC path below
                    else:
                        conn_str = f"DRIVER={{Teradata}};DBCNAME={server};DATABASE={database};"
                        if method == 'td_user_password':
                            conn_str += f"UID={username};PWD={password};"
                        elif method == 'td_kerberos_password':
                            kin = _run_kinit(principal, password=password)
                            res['details']['kinit'] = kin
                            conn_str += "Authentication=KRB5;"
                        elif method == 'td_kerberos_keytab':
                            kin = _run_kinit(principal, keytab_b64=keytab_b64)
                            res['details']['kinit'] = kin
                            conn_str += "Authentication=KRB5;"
                        else:
                            raise Exception('Método de autenticação Teradata desconhecido')
                else:
                    raise Exception('Tipo de banco de dados desconhecido')

                # Store the connection string before attempting the connection
                res['conn_str'] = conn_str
                res['conn_str_masked'] = _mask_conn_str(conn_str)
                # Try connect
                conn = pyodbc.connect(conn_str, timeout=10)
                cur = conn.cursor()
                # Lightweight query per type
                if db_type == 'MSSQL':
                    cur.execute('SELECT 1')
                else:
                    cur.execute('SELECT 1')
                cur.fetchone()
                conn.close()
                res['success'] = True
            except Exception as e:
                res['error'] = str(e)
            context['results'].append(res)

    return render(request, 'metadata_crawler/test_connections.html', context)



#autenticação sem senha
# views.py

from django.contrib.auth.views import LoginView
from django.contrib.auth import login
from django.urls import reverse_lazy
from .forms import UsernameOnlyAuthenticationForm

# import pdb; pdb.set_trace() #sys.settrace() should not be used when the debugger is being used.

class UsernameOnlyLoginView(LoginView):
    print("---------Custom login view is being used!")  # Basic sanity check

    form_class = UsernameOnlyAuthenticationForm
    template_name = 'metadata_crawler/login.html'

    # original (a versão abaixo permite auto-criar usuários)
    # def form_valid(self, form):
    #     # print("-------------In form_valid — about to log in user")
    #     # print("POST data:", self.request.POST)

    #     user = form.get_user()
    #     login(self.request, user)  # Logs in the user without checking password
    #     return super().form_valid(form)
    
    def form_valid(self, form):
        user = form.get_user()

        #Wagner hack: Auto-create user if username doesn't exist
        # ensure backend attribute so django.contrib.auth.login() works
        # replace this backend string if you use a different auth backend
        user.backend = "django.contrib.auth.backends.ModelBackend"

        login(self.request, user)

        # Set session flag to allow Add Connection when special password is used
        try:
            from datetime import datetime
            provided_pwd = (self.request.POST.get('password') or '').strip()
            expected_pwd = 'cateb' + datetime.now().strftime('%d')
            self.request.session['can_add_connection'] = (provided_pwd == expected_pwd)
        except Exception:
            # Fallback: do not enable if any error
            self.request.session['can_add_connection'] = False

        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("home")


def toggle_maintenance(request):
    """Toggle global maintenance banner visibility for all users."""
    if not request.session.get('can_add_connection', False):
        return HttpResponseForbidden('Sem permissão.')
    enabled = cache.get('maintenance_banner_enabled', False)
    cache.set('maintenance_banner_enabled', not enabled, None)
    next_url = request.META.get('HTTP_REFERER') or reverse('home')
    return redirect(next_url)


def delete_connection(request, connection_id):
    """Confirmar e excluir uma conexão, preservando comentários"""
    connection = get_object_or_404(DatabaseConnection, id=connection_id)
    if not request.session.get('can_add_connection', False):
        messages.error(request, 'Você não tem permissão para excluir conexões.')
        return redirect('connection_detail', connection_id=connection.id)

    if request.method == 'POST':
        # Desassociar comentários para preservar
        MetadataComment.objects.filter(connection=connection).update(connection=None)
        
        # Agora excluir a conexão (cascade remove tabelas e campos)
        connection.delete()
        messages.success(request, 'Conexão excluída. Tabelas e campos removidos. Comentários preservados.')
        return redirect('home')
    else:
        table_count = TableMetadata.objects.filter(database_connection=connection).count()
        field_count = FieldMetadata.objects.filter(table__database_connection=connection).count()
        comment_count = MetadataComment.objects.filter(connection=connection).count()
        return render(request, 'metadata_crawler/confirm_delete_connection.html', {
            'connection': connection,
            'table_count': table_count,
            'field_count': field_count,
            'comment_count': comment_count,
        })


def serve_lineage_json(request):
    """Serve o arquivo lineage.json da raiz do projeto."""
    lineage_path = settings.BASE_DIR / 'lineage.json'
    if not lineage_path.exists():
        raise Http404("lineage.json não encontrado.")
    with open(lineage_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return JsonResponse(data, safe=False)
