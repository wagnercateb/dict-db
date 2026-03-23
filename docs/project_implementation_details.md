# Database Metadata Crawler - Detailed Implementation Guide

This document provides a comprehensive, step-by-step guide on how the Database Metadata Crawler project was implemented, including all terminal commands, code explanations, and implementation decisions.

## Table of Contents

1. [Project Setup](#project-setup)
2. [Django Project Creation](#django-project-creation)
3. [Django App Creation](#django-app-creation)
4. [Project Configuration](#project-configuration)
5. [Database Models](#database-models)
6. [Forms](#forms)
7. [Utilities](#utilities)
8. [Views](#views)
9. [URL Configuration](#url-configuration)
10. [Templates](#templates)
11. [Admin Interface](#admin-interface)
12. [Documentation](#documentation)
13. [Database Migration](#database-migration)
14. [User Creation](#user-creation)
15. [Running the Application](#running-the-application)

## Project Setup

### Installing Required Packages

The first step was to install the necessary Python packages for the project:

```bash
pip install Django django-mssql-backend pyodbc
```

This installed:
- Django: The web framework
- django-mssql-backend: Django database backend for MS SQL Server
- pyodbc: Python ODBC bridge for connecting to MS SQL Server

The installation was successful, with django-mssql-backend version 2.8.1 and pyodbc version 5.2.0 being installed.

## Django Project Creation

Created the Django project structure using the django-admin command:

```bash
django-admin startproject db_metadata_crawler .
```

This created the basic Django project structure with the following files:
- `db_metadata_crawler/__init__.py`
- `db_metadata_crawler/settings.py`
- `db_metadata_crawler/urls.py`
- `db_metadata_crawler/wsgi.py`
- `db_metadata_crawler/asgi.py`
- `manage.py`

## Django App Creation

Created a Django app named `metadata_crawler` within the existing project structure:

```bash
python manage.py startapp metadata_crawler
```

This created the app structure with the following files:
- `metadata_crawler/__init__.py`
- `metadata_crawler/admin.py`
- `metadata_crawler/apps.py`
- `metadata_crawler/models.py`
- `metadata_crawler/tests.py`
- `metadata_crawler/views.py`
- `metadata_crawler/migrations/__init__.py`

## Project Configuration

### Updating settings.py

Updated the `settings.py` file to include the newly created app in the `INSTALLED_APPS` list:

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'metadata_crawler',  # Added the new app
]
```

The default SQLite database configuration was kept for simplicity, but in a production environment, this would be changed to use MS SQL Server.

## Database Models

Created the database models in `metadata_crawler/models.py` to define the data structure for the application:

```python
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class DatabaseConnection(models.Model):
    name = models.CharField(max_length=100)
    server = models.CharField(max_length=100)
    database = models.CharField(max_length=100)
    username = models.CharField(max_length=100, blank=True, null=True)
    password = models.CharField(max_length=100, blank=True, null=True)
    use_windows_auth = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_crawled = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} - {self.server}/{self.database}"

class TableMetadata(models.Model):
    TABLE_TYPE_CHOICES = [
        ('TABLE', 'Table'),
        ('VIEW', 'View'),
    ]
    
    connection = models.ForeignKey(DatabaseConnection, on_delete=models.CASCADE, related_name='tables')
    schema = models.CharField(max_length=100)
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=TABLE_TYPE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('connection', 'schema', 'name')

    def __str__(self):
        return f"{self.schema}.{self.name} ({self.type})"

class FieldMetadata(models.Model):
    table = models.ForeignKey(TableMetadata, on_delete=models.CASCADE, related_name='fields')
    name = models.CharField(max_length=100)
    data_type = models.CharField(max_length=100)
    is_nullable = models.BooleanField(default=True)
    is_primary_key = models.BooleanField(default=False)
    is_foreign_key = models.BooleanField(default=False)
    foreign_key_table = models.CharField(max_length=200, blank=True, null=True)
    foreign_key_column = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('table', 'name')

    def __str__(self):
        return f"{self.name} ({self.data_type})"

class MetadataComment(models.Model):
    COMMENT_TYPE_CHOICES = [
        ('TABLE', 'Table'),
        ('FIELD', 'Field'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    comment_type = models.CharField(max_length=10, choices=COMMENT_TYPE_CHOICES)
    table = models.ForeignKey(TableMetadata, on_delete=models.CASCADE, related_name='comments', null=True, blank=True)
    field = models.ForeignKey(FieldMetadata, on_delete=models.CASCADE, related_name='comments', null=True, blank=True)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.comment_type == 'TABLE':
            return f"Comment on {self.table} by {self.user.username}"
        else:
            return f"Comment on {self.field} by {self.user.username}"
```

These models define:
- `DatabaseConnection`: Stores information about database connections
- `TableMetadata`: Stores metadata about tables and views
- `FieldMetadata`: Stores metadata about fields in tables and views
- `MetadataComment`: Stores user comments on tables and fields

## Forms

Created the forms in `metadata_crawler/forms.py` to handle user input:

```python
from django import forms
from .models import DatabaseConnection, MetadataComment

class DatabaseConnectionForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(), required=False)
    
    class Meta:
        model = DatabaseConnection
        fields = ['name', 'server', 'database', 'username', 'password', 'use_windows_auth']
        
    def clean(self):
        cleaned_data = super().clean()
        use_windows_auth = cleaned_data.get('use_windows_auth')
        username = cleaned_data.get('username')
        password = cleaned_data.get('password')
        
        if not use_windows_auth and (not username or not password):
            raise forms.ValidationError(
                "Username and password are required when not using Windows Authentication"
            )
        
        return cleaned_data

class MetadataCommentForm(forms.ModelForm):
    class Meta:
        model = MetadataComment
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={'rows': 3}),
        }

class SearchForm(forms.Form):
    query = forms.CharField(label='Search', max_length=100)
```

These forms define:
- `DatabaseConnectionForm`: For adding and editing database connections
- `MetadataCommentForm`: For adding comments to tables and fields
- `SearchForm`: For searching metadata

## Utilities

Created the utilities in `metadata_crawler/utils.py` to handle database connections and metadata crawling:

```python
import pyodbc
from django.utils import timezone
from django.db.models import Q
from .models import TableMetadata, FieldMetadata

class DatabaseCrawler:
    def __init__(self, connection):
        self.connection = connection
        
    def get_connection_string(self):
        if self.connection.use_windows_auth:
            return f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={self.connection.server};DATABASE={self.connection.database};Trusted_Connection=yes;"
        else:
            return f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={self.connection.server};DATABASE={self.connection.database};UID={self.connection.username};PWD={self.connection.password};"
    
    def connect(self):
        try:
            conn_str = self.get_connection_string()
            return pyodbc.connect(conn_str)
        except Exception as e:
            raise Exception(f"Failed to connect to database: {str(e)}")
    
    def crawl_metadata(self):
        conn = self.connect()
        cursor = conn.cursor()
        
        # Get tables and views
        tables_query = """
        SELECT 
            TABLE_SCHEMA, 
            TABLE_NAME, 
            TABLE_TYPE 
        FROM 
            INFORMATION_SCHEMA.TABLES 
        WHERE 
            TABLE_TYPE IN ('BASE TABLE', 'VIEW')
        ORDER BY 
            TABLE_SCHEMA, TABLE_NAME
        """
        
        cursor.execute(tables_query)
        tables = cursor.fetchall()
        
        for schema, name, type_str in tables:
            table_type = 'TABLE' if type_str == 'BASE TABLE' else 'VIEW'
            
            # Create or update table metadata
            table_obj, created = TableMetadata.objects.update_or_create(
                connection=self.connection,
                schema=schema,
                name=name,
                defaults={'type': table_type}
            )
            
            # Get columns for this table
            columns_query = """
            SELECT 
                c.COLUMN_NAME, 
                c.DATA_TYPE,
                c.IS_NULLABLE,
                CASE WHEN pk.COLUMN_NAME IS NOT NULL THEN 1 ELSE 0 END AS IS_PRIMARY_KEY,
                CASE WHEN fk.COLUMN_NAME IS NOT NULL THEN 1 ELSE 0 END AS IS_FOREIGN_KEY,
                OBJECT_SCHEMA_NAME(fk.referenced_object_id) AS FK_SCHEMA,
                OBJECT_NAME(fk.referenced_object_id) AS FK_TABLE,
                COL_NAME(fk.referenced_object_id, fk.referenced_column_id) AS FK_COLUMN
            FROM 
                INFORMATION_SCHEMA.COLUMNS c
            LEFT JOIN (
                SELECT 
                    ku.TABLE_SCHEMA,
                    ku.TABLE_NAME,
                    ku.COLUMN_NAME
                FROM 
                    INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                JOIN 
                    INFORMATION_SCHEMA.KEY_COLUMN_USAGE ku 
                    ON tc.CONSTRAINT_NAME = ku.CONSTRAINT_NAME
                WHERE 
                    tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
            ) pk ON c.TABLE_SCHEMA = pk.TABLE_SCHEMA 
                AND c.TABLE_NAME = pk.TABLE_NAME 
                AND c.COLUMN_NAME = pk.COLUMN_NAME
            LEFT JOIN (
                SELECT 
                    SCHEMA_NAME(fk.schema_id) AS TABLE_SCHEMA,
                    OBJECT_NAME(fk.parent_object_id) AS TABLE_NAME,
                    COL_NAME(fk.parent_object_id, fkc.parent_column_id) AS COLUMN_NAME,
                    fk.referenced_object_id,
                    fkc.referenced_column_id
                FROM 
                    sys.foreign_keys fk
                JOIN 
                    sys.foreign_key_columns fkc 
                    ON fk.object_id = fkc.constraint_object_id
            ) fk ON c.TABLE_SCHEMA = fk.TABLE_SCHEMA 
                AND c.TABLE_NAME = fk.TABLE_NAME 
                AND c.COLUMN_NAME = fk.COLUMN_NAME
            WHERE 
                c.TABLE_SCHEMA = ? AND c.TABLE_NAME = ?
            ORDER BY 
                c.ORDINAL_POSITION
            """
            
            cursor.execute(columns_query, (schema, name))
            columns = cursor.fetchall()
            
            for col_name, data_type, is_nullable, is_pk, is_fk, fk_schema, fk_table, fk_column in columns:
                # Create or update field metadata
                fk_table_full = f"{fk_schema}.{fk_table}" if fk_schema and fk_table else None
                
                FieldMetadata.objects.update_or_create(
                    table=table_obj,
                    name=col_name,
                    defaults={
                        'data_type': data_type,
                        'is_nullable': is_nullable == 'YES',
                        'is_primary_key': bool(is_pk),
                        'is_foreign_key': bool(is_fk),
                        'foreign_key_table': fk_table_full,
                        'foreign_key_column': fk_column
                    }
                )
        
        # Update last crawled timestamp
        self.connection.last_crawled = timezone.now()
        self.connection.save()
        
        cursor.close()
        conn.close()

def search_metadata(query):
    """Search for metadata matching the query"""
    tables = TableMetadata.objects.filter(
        Q(schema__icontains=query) | 
        Q(name__icontains=query)
    ).select_related('connection')
    
    fields = FieldMetadata.objects.filter(
        Q(name__icontains=query) | 
        Q(data_type__icontains=query) |
        Q(foreign_key_table__icontains=query) |
        Q(foreign_key_column__icontains=query)
    ).select_related('table', 'table__connection')
    
    comments = MetadataComment.objects.filter(
        Q(text__icontains=query)
    ).select_related('user', 'table', 'field')
    
    return {
        'tables': tables,
        'fields': fields,
        'comments': comments
    }
```

This utility code defines:
- `DatabaseCrawler`: A class for connecting to MS SQL Server and crawling metadata
- `search_metadata`: A function for searching across tables, fields, and comments

## Views

Updated the views in `metadata_crawler/views.py` to handle user interactions:

```python
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .models import DatabaseConnection, TableMetadata, FieldMetadata, MetadataComment
from .forms import DatabaseConnectionForm, MetadataCommentForm, SearchForm
from .utils import DatabaseCrawler, search_metadata

def home(request):
    connections = DatabaseConnection.objects.all().order_by('name')
    return render(request, 'metadata_crawler/home.html', {'connections': connections})

@login_required
def add_connection(request):
    if request.method == 'POST':
        form = DatabaseConnectionForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Database connection added successfully.')
            return redirect('home')
    else:
        form = DatabaseConnectionForm()
    
    return render(request, 'metadata_crawler/add_connection.html', {'form': form})

def connection_detail(request, connection_id):
    connection = get_object_or_404(DatabaseConnection, pk=connection_id)
    tables = TableMetadata.objects.filter(connection=connection).order_by('schema', 'name')
    
    return render(request, 'metadata_crawler/connection_detail.html', {
        'connection': connection,
        'tables': tables
    })

@login_required
def crawl_database(request, connection_id):
    connection = get_object_or_404(DatabaseConnection, pk=connection_id)
    
    try:
        crawler = DatabaseCrawler(connection)
        crawler.crawl_metadata()
        messages.success(request, 'Database metadata crawled successfully.')
    except Exception as e:
        messages.error(request, f'Error crawling database: {str(e)}')
    
    return redirect('connection_detail', connection_id=connection_id)

def table_detail(request, table_id):
    table = get_object_or_404(TableMetadata, pk=table_id)
    fields = FieldMetadata.objects.filter(table=table).order_by('name')
    comments = MetadataComment.objects.filter(table=table, comment_type='TABLE').order_by('-created_at')
    
    if request.method == 'POST' and request.user.is_authenticated:
        form = MetadataCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.user = request.user
            comment.table = table
            comment.comment_type = 'TABLE'
            comment.save()
            messages.success(request, 'Comment added successfully.')
            return redirect('table_detail', table_id=table_id)
    else:
        form = MetadataCommentForm()
    
    return render(request, 'metadata_crawler/table_detail.html', {
        'table': table,
        'fields': fields,
        'comments': comments,
        'form': form
    })

def field_detail(request, field_id):
    field = get_object_or_404(FieldMetadata, pk=field_id)
    comments = MetadataComment.objects.filter(field=field, comment_type='FIELD').order_by('-created_at')
    
    if request.method == 'POST' and request.user.is_authenticated:
        form = MetadataCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.user = request.user
            comment.field = field
            comment.comment_type = 'FIELD'
            comment.save()
            messages.success(request, 'Comment added successfully.')
            return redirect('field_detail', field_id=field_id)
    else:
        form = MetadataCommentForm()
    
    return render(request, 'metadata_crawler/field_detail.html', {
        'field': field,
        'comments': comments,
        'form': form
    })

def search_results(request):
    query = request.GET.get('query', '')
    results = {}
    
    if query:
        form = SearchForm(initial={'query': query})
        results = search_metadata(query)
    else:
        form = SearchForm()
    
    return render(request, 'metadata_crawler/search_results.html', {
        'form': form,
        'query': query,
        'results': results
    })
```

These views handle:
- Displaying the home page with a list of connections
- Adding new database connections
- Viewing connection details
- Crawling database metadata
- Viewing table and field details
- Adding comments to tables and fields
- Searching metadata

## URL Configuration

### App URLs

Created the URL configuration in `metadata_crawler/urls.py`:

```python
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('connections/add/', views.add_connection, name='add_connection'),
    path('connections/<int:connection_id>/', views.connection_detail, name='connection_detail'),
    path('connections/<int:connection_id>/crawl/', views.crawl_database, name='crawl_database'),
    path('tables/<int:table_id>/', views.table_detail, name='table_detail'),
    path('fields/<int:field_id>/', views.field_detail, name='field_detail'),
    path('search/', views.search_results, name='search_results'),
]
```

### Project URLs

Updated the main URL configuration in `db_metadata_crawler/urls.py`:

```python
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('metadata_crawler.urls')),
    path('login/', auth_views.LoginView.as_view(template_name='metadata_crawler/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/'), name='logout'),
]
```

## Templates

Created the template directory structure:

```bash
mkdir -p metadata_crawler/templates/metadata_crawler
```

### Base Template

Created the base template in `metadata_crawler/templates/metadata_crawler/base.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Database Metadata Crawler{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {
            padding-top: 56px;
            padding-bottom: 20px;
        }
        .navbar {
            margin-bottom: 20px;
        }
        .content {
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-md navbar-dark bg-dark fixed-top">
        <div class="container">
            <a class="navbar-brand" href="{% url 'home' %}">DB Metadata Crawler</a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav me-auto">
                    <li class="nav-item">
                        <a class="nav-link" href="{% url 'home' %}">Home</a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="{% url 'add_connection' %}">Add Connection</a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="{% url 'search_results' %}">Search</a>
                    </li>
                </ul>
                <ul class="navbar-nav">
                    {% if user.is_authenticated %}
                    <li class="nav-item">
                        <span class="nav-link">Welcome, {{ user.username }}</span>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="{% url 'logout' %}">Logout</a>
                    </li>
                    {% else %}
                    <li class="nav-item">
                        <a class="nav-link" href="{% url 'login' %}">Login</a>
                    </li>
                    {% endif %}
                </ul>
            </div>
        </div>
    </nav>

    <div class="container content">
        {% if messages %}
            {% for message in messages %}
                <div class="alert alert-{{ message.tags }}">
                    {{ message }}
                </div>
            {% endfor %}
        {% endif %}

        {% block content %}{% endblock %}
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
```

### Login Template

Created the login template in `metadata_crawler/templates/metadata_crawler/login.html`:

```html
{% extends 'metadata_crawler/base.html' %}

{% block title %}Login - Database Metadata Crawler{% endblock %}

{% block content %}
<div class="row justify-content-center">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header">
                <h2>Login</h2>
            </div>
            <div class="card-body">
                <form method="post">
                    {% csrf_token %}
                    <div class="mb-3">
                        <label for="id_username" class="form-label">Username</label>
                        <input type="text" name="username" id="id_username" class="form-control" required>
                    </div>
                    <div class="mb-3">
                        <label for="id_password" class="form-label">Password</label>
                        <input type="password" name="password" id="id_password" class="form-control" required>
                    </div>
                    <button type="submit" class="btn btn-primary">Login</button>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

### Home Template

Created the home template in `metadata_crawler/templates/metadata_crawler/home.html`:

```html
{% extends 'metadata_crawler/base.html' %}

{% block title %}Home - Database Metadata Crawler{% endblock %}

{% block content %}
<div class="jumbotron">
    <h1 class="display-4">Database Metadata Crawler</h1>
    <p class="lead">Explore and document your MS SQL Server database metadata.</p>
    <hr class="my-4">
    <p>Add a database connection to get started, or browse existing connections below.</p>
    <a class="btn btn-primary btn-lg" href="{% url 'add_connection' %}" role="button">Add Connection</a>
</div>

<h2 class="mt-4">Database Connections</h2>

{% if connections %}
<div class="list-group mt-3">
    {% for connection in connections %}
    <div class="list-group-item list-group-item-action">
        <div class="d-flex w-100 justify-content-between">
            <h5 class="mb-1">{{ connection.name }}</h5>
            <small>Last crawled: {% if connection.last_crawled %}{{ connection.last_crawled|date:"Y-m-d H:i" }}{% else %}Never{% endif %}</small>
        </div>
        <p class="mb-1">{{ connection.server }} / {{ connection.database }}</p>
        <div class="mt-2">
            <a href="{% url 'connection_detail' connection.id %}" class="btn btn-sm btn-outline-primary">View Details</a>
            <a href="{% url 'crawl_database' connection.id %}" class="btn btn-sm btn-outline-success">Crawl Database</a>
        </div>
    </div>
    {% endfor %}
</div>
{% else %}
<div class="alert alert-info mt-3">
    No database connections found. <a href="{% url 'add_connection' %}">Add one</a> to get started.
</div>
{% endif %}
{% endblock %}
```

### Add Connection Template

Created the add connection template in `metadata_crawler/templates/metadata_crawler/add_connection.html`:

```html
{% extends 'metadata_crawler/base.html' %}

{% block title %}Add Connection - Database Metadata Crawler{% endblock %}

{% block content %}
<h2>Add Database Connection</h2>

<div class="card mt-3">
    <div class="card-body">
        <form method="post">
            {% csrf_token %}
            
            {% if form.non_field_errors %}
            <div class="alert alert-danger">
                {% for error in form.non_field_errors %}
                {{ error }}
                {% endfor %}
            </div>
            {% endif %}
            
            <div class="mb-3">
                <label for="id_name" class="form-label">Connection Name</label>
                <input type="text" name="name" id="id_name" class="form-control {% if form.name.errors %}is-invalid{% endif %}" value="{{ form.name.value|default:'' }}" required>
                {% if form.name.errors %}
                <div class="invalid-feedback">{{ form.name.errors.0 }}</div>
                {% endif %}
            </div>
            
            <div class="mb-3">
                <label for="id_server" class="form-label">Server</label>
                <input type="text" name="server" id="id_server" class="form-control {% if form.server.errors %}is-invalid{% endif %}" value="{{ form.server.value|default:'' }}" required>
                {% if form.server.errors %}
                <div class="invalid-feedback">{{ form.server.errors.0 }}</div>
                {% endif %}
                <div class="form-text">Example: localhost\SQLEXPRESS or server.domain.com</div>
            </div>
            
            <div class="mb-3">
                <label for="id_database" class="form-label">Database</label>
                <input type="text" name="database" id="id_database" class="form-control {% if form.database.errors %}is-invalid{% endif %}" value="{{ form.database.value|default:'' }}" required>
                {% if form.database.errors %}
                <div class="invalid-feedback">{{ form.database.errors.0 }}</div>
                {% endif %}
            </div>
            
            <div class="mb-3 form-check">
                <input type="checkbox" name="use_windows_auth" id="id_use_windows_auth" class="form-check-input" {% if form.use_windows_auth.value %}checked{% endif %}>
                <label for="id_use_windows_auth" class="form-check-label">Use Windows Authentication</label>
            </div>
            
            <div id="sql_auth_fields">
                <div class="mb-3">
                    <label for="id_username" class="form-label">Username</label>
                    <input type="text" name="username" id="id_username" class="form-control {% if form.username.errors %}is-invalid{% endif %}" value="{{ form.username.value|default:'' }}">
                    {% if form.username.errors %}
                    <div class="invalid-feedback">{{ form.username.errors.0 }}</div>
                    {% endif %}
                </div>
                
                <div class="mb-3">
                    <label for="id_password" class="form-label">Password</label>
                    <input type="password" name="password" id="id_password" class="form-control {% if form.password.errors %}is-invalid{% endif %}">
                    {% if form.password.errors %}
                    <div class="invalid-feedback">{{ form.password.errors.0 }}</div>
                    {% endif %}
                </div>
            </div>
            
            <button type="submit" class="btn btn-primary">Add Connection</button>
            <a href="{% url 'home' %}" class="btn btn-secondary">Cancel</a>
        </form>
    </div>
</div>

<script>
    document.addEventListener('DOMContentLoaded', function() {
        const windowsAuthCheckbox = document.getElementById('id_use_windows_auth');
        const sqlAuthFields = document.getElementById('sql_auth_fields');
        
        function toggleAuthFields() {
            if (windowsAuthCheckbox.checked) {
                sqlAuthFields.style.display = 'none';
            } else {
                sqlAuthFields.style.display = 'block';
            }
        }
        
        windowsAuthCheckbox.addEventListener('change', toggleAuthFields);
        toggleAuthFields();
    });
</script>
{% endblock %}
```

### Connection Detail Template

Created the connection detail template in `metadata_crawler/templates/metadata_crawler/connection_detail.html`:

```html
{% extends 'metadata_crawler/base.html' %}

{% block title %}{{ connection.name }} - Database Metadata Crawler{% endblock %}

{% block content %}
<div class="d-flex justify-content-between align-items-center">
    <h2>{{ connection.name }}</h2>
    <div>
        <a href="{% url 'crawl_database' connection.id %}" class="btn btn-success">Crawl Metadata</a>
    </div>
</div>

<div class="card mt-3">
    <div class="card-header">
        <h5>Connection Details</h5>
    </div>
    <div class="card-body">
        <div class="row">
            <div class="col-md-6">
                <p><strong>Server:</strong> {{ connection.server }}</p>
                <p><strong>Database:</strong> {{ connection.database }}</p>
                <p><strong>Authentication:</strong> {% if connection.use_windows_auth %}Windows Authentication{% else %}SQL Server Authentication{% endif %}</p>
            </div>
            <div class="col-md-6">
                <p><strong>Created:</strong> {{ connection.created_at|date:"Y-m-d H:i" }}</p>
                <p><strong>Updated:</strong> {{ connection.updated_at|date:"Y-m-d H:i" }}</p>
                <p><strong>Last Crawled:</strong> {% if connection.last_crawled %}{{ connection.last_crawled|date:"Y-m-d H:i" }}{% else %}Never{% endif %}</p>
            </div>
        </div>
    </div>
</div>

<h3 class="mt-4">Tables and Views</h3>

{% if tables %}
<div class="table-responsive mt-3">
    <table class="table table-striped table-hover">
        <thead>
            <tr>
                <th>Schema</th>
                <th>Name</th>
                <th>Type</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>
            {% for table in tables %}
            <tr>
                <td>{{ table.schema }}</td>
                <td>{{ table.name }}</td>
                <td>{{ table.get_type_display }}</td>
                <td>
                    <a href="{% url 'table_detail' table.id %}" class="btn btn-sm btn-outline-primary">View Details</a>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% else %}
<div class="alert alert-info mt-3">
    No tables or views found. <a href="{% url 'crawl_database' connection.id %}">Crawl the database</a> to retrieve metadata.
</div>
{% endif %}
{% endblock %}
```

### Table Detail Template

Created the table detail template in `metadata_crawler/templates/metadata_crawler/table_detail.html`:

```html
{% extends 'metadata_crawler/base.html' %}

{% block title %}{{ table.schema }}.{{ table.name }} - Database Metadata Crawler{% endblock %}

{% block content %}
<div class="d-flex justify-content-between align-items-center">
    <h2>{{ table.schema }}.{{ table.name }}</h2>
    <div>
        <a href="{% url 'connection_detail' table.connection.id %}" class="btn btn-outline-secondary">Back to Connection</a>
    </div>
</div>

<div class="card mt-3">
    <div class="card-header">
        <h5>Table Details</h5>
    </div>
    <div class="card-body">
        <div class="row">
            <div class="col-md-6">
                <p><strong>Schema:</strong> {{ table.schema }}</p>
                <p><strong>Name:</strong> {{ table.name }}</p>
                <p><strong>Type:</strong> {{ table.get_type_display }}</p>
            </div>
            <div class="col-md-6">
                <p><strong>Connection:</strong> <a href="{% url 'connection_detail' table.connection.id %}">{{ table.connection.name }}</a></p>
                <p><strong>Created:</strong> {{ table.created_at|date:"Y-m-d H:i" }}</p>
                <p><strong>Updated:</strong> {{ table.updated_at|date:"Y-m-d H:i" }}</p>
            </div>
        </div>
    </div>
</div>

<h3 class="mt-4">Fields</h3>

{% if fields %}
<div class="table-responsive mt-3">
    <table class="table table-striped table-hover">
        <thead>
            <tr>
                <th>Name</th>
                <th>Data Type</th>
                <th>Nullable</th>
                <th>Primary Key</th>
                <th>Foreign Key</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>
            {% for field in fields %}
            <tr>
                <td>{{ field.name }}</td>
                <td>{{ field.data_type }}</td>
                <td>{% if field.is_nullable %}<span class="text-success">Yes</span>{% else %}<span class="text-danger">No</span>{% endif %}</td>
                <td>{% if field.is_primary_key %}<span class="text-primary">Yes</span>{% else %}No{% endif %}</td>
                <td>
                    {% if field.is_foreign_key %}
                    <span class="text-primary">Yes</span> ({{ field.foreign_key_table }}.{{ field.foreign_key_column }})
                    {% else %}
                    No
                    {% endif %}
                </td>
                <td>
                    <a href="{% url 'field_detail' field.id %}" class="btn btn-sm btn-outline-primary">View Details</a>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% else %}
<div class="alert alert-info mt-3">
    No fields found for this table.
</div>
{% endif %}

<h3 class="mt-4">Comments</h3>

{% if user.is_authenticated %}
<div class="card mt-3">
    <div class="card-header">
        <h5>Add Comment</h5>
    </div>
    <div class="card-body">
        <form method="post">
            {% csrf_token %}
            <div class="mb-3">
                {{ form.text.label_tag }}
                {{ form.text }}
                {% if form.text.errors %}
                <div class="invalid-feedback d-block">{{ form.text.errors.0 }}</div>
                {% endif %}
            </div>
            <button type="submit" class="btn btn-primary">Add Comment</button>
        </form>
    </div>
</div>
{% endif %}

{% if comments %}
<div class="list-group mt-3">
    {% for comment in comments %}
    <div class="list-group-item">
        <div class="d-flex w-100 justify-content-between">
            <h6 class="mb-1">{{ comment.user.username }}</h6>
            <small>{{ comment.created_at|date:"Y-m-d H:i" }}</small>
        </div>
        <p class="mb-1">{{ comment.text }}</p>
    </div>
    {% endfor %}
</div>
{% else %}
<div class="alert alert-info mt-3">
    No comments yet.
</div>
{% endif %}
{% endblock %}
```

### Field Detail Template

Created the field detail template in `metadata_crawler/templates/metadata_crawler/field_detail.html`:

```html
{% extends 'metadata_crawler/base.html' %}

{% block title %}{{ field.name }} - Database Metadata Crawler{% endblock %}

{% block content %}
<div class="d-flex justify-content-between align-items-center">
    <h2>{{ field.name }}</h2>
    <div>
        <a href="{% url 'table_detail' field.table.id %}" class="btn btn-outline-secondary">Back to Table</a>
    </div>
</div>

<div class="card mt-3">
    <div class="card-header">
        <h5>Field Details</h5>
    </div>
    <div class="card-body">
        <div class="row">
            <div class="col-md-6">
                <p><strong>Name:</strong> {{ field.name }}</p>
                <p><strong>Data Type:</strong> {{ field.data_type }}</p>
                <p><strong>Nullable:</strong> {% if field.is_nullable %}<span class="text-success">Yes</span>{% else %}<span class="text-danger">No</span>{% endif %}</p>
                <p><strong>Primary Key:</strong> {% if field.is_primary_key %}<span class="text-primary">Yes</span>{% else %}No{% endif %}</p>
            </div>
            <div class="col-md-6">
                <p><strong>Table:</strong> <a href="{% url 'table_detail' field.table.id %}">{{ field.table.schema }}.{{ field.table.name }}</a></p>
                <p><strong>Foreign Key:</strong> {% if field.is_foreign_key %}<span class="text-primary">Yes</span>{% else %}No{% endif %}</p>
                {% if field.is_foreign_key %}
                <p><strong>References:</strong> {{ field.foreign_key_table }}.{{ field.foreign_key_column }}</p>
                {% endif %}
                <p><strong>Created:</strong> {{ field.created_at|date:"Y-m-d H:i" }}</p>
                <p><strong>Updated:</strong> {{ field.updated_at|date:"Y-m-d H:i" }}</p>
            </div>
        </div>
    </div>
</div>

<h3 class="mt-4">Comments</h3>

{% if user.is_authenticated %}
<div class="card mt-3">
    <div class="card-header">
        <h5>Add Comment</h5>
    </div>
    <div class="card-body">
        <form method="post">
            {% csrf_token %}
            <div class="mb-3">
                {{ form.text.label_tag }}
                {{ form.text }}
                {% if form.text.errors %}
                <div class="invalid-feedback d-block">{{ form.text.errors.0 }}</div>
                {% endif %}
            </div>
            <button type="submit" class="btn btn-primary">Add Comment</button>
        </form>
    </div>
</div>
{% endif %}

{% if comments %}
<div class="list-group mt-3">
    {% for comment in comments %}
    <div class="list-group-item">
        <div class="d-flex w-100 justify-content-between">
            <h6 class="mb-1">{{ comment.user.username }}</h6>
            <small>{{ comment.created_at|date:"Y-m-d H:i" }}</small>
        </div>
        <p class="mb-1">{{ comment.text }}</p>
    </div>
    {% endfor %}
</div>
{% else %}
<div class="alert alert-info mt-3">
    No comments yet.
</div>
{% endif %}
{% endblock %}
```

### Search Results Template

Created the search results template in `metadata_crawler/templates/metadata_crawler/search_results.html`:

```html
{% extends 'metadata_crawler/base.html' %}

{% block title %}Search Results - Database Metadata Crawler{% endblock %}

{% block content %}
<h2>Search</h2>

<div class="card mt-3">
    <div class="card-body">
        <form method="get" action="{% url 'search_results' %}" class="d-flex">
            <input type="text" name="query" class="form-control me-2" value="{{ query }}" placeholder="Search tables, fields, and comments..." required>
            <button type="submit" class="btn btn-primary">Search</button>
        </form>
    </div>
</div>

{% if query %}
<h3 class="mt-4">Results for "{{ query }}"</h3>

<ul class="nav nav-tabs mt-3" id="resultsTabs" role="tablist">
    <li class="nav-item" role="presentation">
        <button class="nav-link active" id="tables-tab" data-bs-toggle="tab" data-bs-target="#tables" type="button" role="tab">Tables ({{ results.tables|length }})</button>
    </li>
    <li class="nav-item" role="presentation">
        <button class="nav-link" id="fields-tab" data-bs-toggle="tab" data-bs-target="#fields" type="button" role="tab">Fields ({{ results.fields|length }})</button>
    </li>
    <li class="nav-item" role="presentation">
        <button class="nav-link" id="comments-tab" data-bs-toggle="tab" data-bs-target="#comments" type="button" role="tab">Comments ({{ results.comments|length }})</button>
    </li>
</ul>

<div class="tab-content mt-3" id="resultsTabsContent">
    <div class="tab-pane fade show active" id="tables" role="tabpanel">
        {% if results.tables %}
        <div class="table-responsive">
            <table class="table table-striped table-hover">
                <thead>
                    <tr>
                        <th>Connection</th>
                        <th>Schema</th>
                        <th>Name</th>
                        <th>Type</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {% for table in results.tables %}
                    <tr>
                        <td>{{ table.connection.name }}</td>
                        <td>{{ table.schema }}</td>
                        <td>{{ table.name }}</td>
                        <td>{{ table.get_type_display }}</td>
                        <td>
                            <a href="{% url 'table_detail' table.id %}" class="btn btn-sm btn-outline-primary">View Details</a>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% else %}
        <div class="alert alert-info">
            No tables found matching "{{ query }}".
        </div>
        {% endif %}
    </div>
    
    <div class="tab-pane fade" id="fields" role="tabpanel">
        {% if results.fields %}
        <div class="table-responsive">
            <table class="table table-striped table-hover">
                <thead>
                    <tr>
                        <th>Table</th>
                        <th>Name</th>
                        <th>Data Type</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {% for field in results.fields %}
                    <tr>
                        <td>{{ field.table.schema }}.{{ field.table.name }}</td>
                        <td>{{ field.name }}</td>
                        <td>{{ field.data_type }}</td>
                        <td>
                            <a href="{% url 'field_detail' field.id %}" class="btn btn-sm btn-outline-primary">View Details</a>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% else %}
        <div class="alert alert-info">
            No fields found matching "{{ query }}".
        </div>
        {% endif %}
    </div>
    
    <div class="tab-pane fade" id="comments" role="tabpanel">
        {% if results.comments %}
        <div class="list-group">
            {% for comment in results.comments %}
            <div class="list-group-item">
                <div class="d-flex w-100 justify-content-between">
                    <h6 class="mb-1">
                        {% if comment.comment_type == 'TABLE' %}
                        Comment on <a href="{% url 'table_detail' comment.table.id %}">{{ comment.table.schema }}.{{ comment.table.name }}</a>
                        {% else %}
                        Comment on <a href="{% url 'field_detail' comment.field.id %}">{{ comment.field.name }}</a> in <a href="{% url 'table_detail' comment.field.table.id %}">{{ comment.field.table.schema }}.{{ comment.field.table.name }}</a>
                        {% endif %}
                    </h6>
                    <small>{{ comment.created_at|date:"Y-m-d H:i" }} by {{ comment.user.username }}</small>
                </div>
                <p class="mb-1">{{ comment.text }}</p>
            </div>
            {% endfor %}
        </div>
        {% else %}
        <div class="alert alert-info">
            No comments found matching "{{ query }}".
        </div>
        {% endif %}
    </div>
</div>
{% endif %}
{% endblock %}
```

## Admin Interface

Updated the admin interface in `metadata_crawler/admin.py`:

```python
from django.contrib import admin
from .models import DatabaseConnection, TableMetadata, FieldMetadata, MetadataComment

@admin.register(DatabaseConnection)
class DatabaseConnectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'server', 'database', 'use_windows_auth', 'last_crawled')
    search_fields = ('name', 'server', 'database')
    list_filter = ('use_windows_auth', 'last_crawled')
    readonly_fields = ('created_at', 'updated_at', 'last_crawled')

@admin.register(TableMetadata)
class TableMetadataAdmin(admin.ModelAdmin):
    list_display = ('schema', 'name', 'type', 'connection')
    search_fields = ('schema', 'name')
    list_filter = ('type', 'connection')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(FieldMetadata)
class FieldMetadataAdmin(admin.ModelAdmin):
    list_display = ('name', 'table', 'data_type', 'is_nullable', 'is_primary_key', 'is_foreign_key')
    search_fields = ('name', 'data_type', 'table__name', 'table__schema')
    list_filter = ('is_nullable', 'is_primary_key', 'is_foreign_key', 'data_type')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(MetadataComment)
class MetadataCommentAdmin(admin.ModelAdmin):
    list_display = ('get_commented_object', 'user', 'comment_type', 'created_at')
    search_fields = ('text', 'user__username')
    list_filter = ('comment_type', 'created_at', 'user')
    readonly_fields = ('created_at', 'updated_at')
    
    def get_commented_object(self, obj):
        if obj.comment_type == 'TABLE':
            return f"{obj.table.schema}.{obj.table.name}"
        else:
            return f"{obj.field.table.schema}.{obj.field.table.name}.{obj.field.name}"
    get_commented_object.short_description = 'Object'
```

## Documentation

Created a README.md file to document the project:

```markdown
# Database Metadata Crawler

A Django web application for crawling, exploring, and documenting MS SQL Server database metadata.

## Features

- Connect to multiple MS SQL Server databases
- Automatically crawl and extract metadata from tables, views, and fields
- Browse tables, views, and fields with detailed metadata
- Search across all metadata
- Add comments to tables and fields
- User authentication for adding comments
- Admin interface for managing metadata

## Requirements

- Python 3.8+
- Django 5.2+
- MS SQL Server
- ODBC Driver for SQL Server

## Installation

1. Clone the repository
2. Install the required packages:

```bash
pip install -r requirements.txt
```

3. Apply migrations:

```bash
python manage.py migrate
```

4. Create a superuser:

```bash
python manage.py createsuperuser
```

5. Run the development server:

```bash
python manage.py runserver
```

6. Access the application at http://127.0.0.1:8000/

## Usage

1. Log in with your superuser account
2. Add a database connection
3. Crawl the database to extract metadata
4. Browse tables, views, and fields
5. Add comments to document your database
6. Search for specific metadata

## MS SQL Server Connection

The application supports two authentication methods for MS SQL Server:

1. **Windows Authentication**: Uses the Windows credentials of the user running the application
2. **SQL Server Authentication**: Uses a username and password

For Windows Authentication, make sure the user running the application has the necessary permissions to access the database.

For SQL Server Authentication, provide a valid username and password with appropriate permissions.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
```

Created a requirements.txt file:

```
Django>=5.2.0,<6.0.0
django-mssql-backend>=2.8.0,<3.0.0
pyodbc>=5.0.0,<6.0.0
```

## Database Migration

Created the initial database migrations:

```bash
python manage.py makemigrations
```

This created the initial migration file in `metadata_crawler/migrations/0001_initial.py`.

Applied the migrations to create the database tables:

```bash
python manage.py migrate
```

This created all the necessary database tables for the application.

## User Creation

Created a superuser to access the admin interface:

```bash
python manage.py createsuperuser
```

Provided the following information:
- Username: admin
- Email: admin@example.com
- Password: (a secure password)

## Running the Application

Started the Django development server:

```bash
python manage.py runserver
```

The server started successfully and was accessible at http://127.0.0.1:8000/.

## Conclusion

The Database Metadata Crawler application was successfully implemented with all the required features. The application provides a user-friendly interface for exploring and documenting MS SQL Server database metadata, with features for searching, commenting, and browsing metadata.

The project follows Django best practices, with a clean separation of concerns between models, views, templates, and utilities. The code is well-organized and documented, making it easy to maintain and extend in the future.