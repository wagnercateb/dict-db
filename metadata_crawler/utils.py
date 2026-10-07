import pyodbc
import os
import platform
from .models import DatabaseConnection, TableMetadata, FieldMetadata
from django.utils import timezone
from .models import TableMetadata, FieldMetadata, MetadataComment

#Q() facilita construir queries com vários OR, AND, etc 
from django.db.models import Q

from .utilitarios import logger, detect_runtime_environment

ENVIRONMENT = detect_runtime_environment()

class DatabaseCrawler:
    def __init__(self, connection_id, runtime_username=None, runtime_password=None):
        #depois de alterar FK para name ao invés de id, isso começou a dar erro:
        #self.connection = DatabaseConnection.objects.get(id=connection_id)
        #assim resolveu porque o que está vinda é o objeto connection e não só um id:
        self.connection = DatabaseConnection.objects.get(id=connection_id.id)
        self.runtime_username = runtime_username
        self.runtime_password = runtime_password

    def get_connection_string(self):
        """Generate a connection string based on database type"""
        
        if getattr(self.connection, "connection_string", None) != None:
            return self.connection.connection_string
        
        conn_str = ''
        if self.connection.database_type == 'MSSQL':
            conn_str = 'Driver={SQL Server}; Server=' + self.connection.server + '; Database=' + self.connection.database + ';'
            if self.runtime_username and self.runtime_password:
                conn_str += f"UID={self.runtime_username};PWD={self.runtime_password};"
            else:
                #if ENVIRONMENT == 'windows' or ENVIRONMENT == 'docker-wsl':
                if ENVIRONMENT == 'docker-wsl':
                    conn_str += "Trusted_Connection=yes;Integrated Security=SSPI;"
                else:
                    conn_str += "Trusted_Connection=yes;"
        elif self.connection.database_type == 'TERADATA':
            host = self.connection.server or ''
            user = (self.runtime_username or '')
            pwd = (self.runtime_password or '')
            conn_str = (
                '{"host":"' + host + '", '
                '"logmech":"LDAP", '
                '"tmode":"TERA", '
                '"user":"' + user + '", '
                '"password":"' + pwd + '"}'
            )
        
        logger.info(f"connection_string: {conn_str}")
        return conn_str
    

    def connect(self):
        """Connect to the database"""
        try:
            conn_str = self.get_connection_string()

            # Em Linux, inicializa Kerberos conforme necessário (MSSQL Trusted_Connection ou Teradata KRB5)
            if os.name != 'nt':
                from .autenticar_user import ensure_kerberos_ticket
                try:
                    mssql_needs_ticket = (self.connection.database_type == 'MSSQL' and 'Trusted_Connection=yes' in conn_str)
                    td_needs_ticket = (self.connection.database_type == 'TERADATA' and ('Authentication=KRB5' in conn_str or os.getenv('TERADATA_LOGMECH', '').upper() == 'KRB5'))
                    if mssql_needs_ticket or td_needs_ticket:
                        logger.info('Inicializando Kerberos (kinit) conforme configuração da conexão')
                        ensure_kerberos_ticket()
                except Exception as auth_err:
                    # Best-effort: loga e segue com a conexão; ODBC/driver reportará erro se ticket for necessário
                    logger.error(f"Falha ao inicializar Kerberos (seguindo sem interromper): {auth_err}")

            # Suporte ao driver Python do Teradata como estratégia comprovada em Docker
            if self.connection.database_type == 'TERADATA':
                try:
                    import teradatasql  # type: ignore
                except Exception as imp_err:
                    raise Exception(f"teradatasql não instalado: {imp_err}. Inclua 'teradatasql' no requirements/ambiente.")
 
                logger.debug("Conectando via driver Python teradatasql")
                return teradatasql.connect(conn_str)
            
            else:
                logger.debug("Conectando via driver pyodbc sql server")
                #Abre a conexão com o Banco de Dados
                return pyodbc.connect(conn_str)

        except Exception as e:
            err = str(e) 
            # Oferece uma mensagem mais clara quando houver problema de SSPI/Kerberos no SQL Server
            if (
                self.connection.database_type == 'MSSQL'
                and (
                    'SSPI Provider' in err
                    or 'Kerberos' in err
                    or 'KRB5' in err
                )
            ):
                raise Exception(
                    "Falha ao conectar ao banco de dados: problema de autenticação integrada (SSPI/Kerberos). "
                    "Se não estiver em um ambiente de domínio ou se executar dentro de WSL/contêiner, preencha 'Usuário' e 'Senha' para usar autenticação SQL. "
                    "Caso precise de Windows Auth, garanta que a sessão Windows tenha credenciais válidas e que o driver ODBC esteja instalado corretamente. "
                    f"Detalhes: {err}"
                )
            raise Exception(f"Falha ao conectar ao banco de dados: {err}")
        
        finally:
            logger.info(f"conn_str: {conn_str}")
    

    def _emulation_enabled(self):
        """Habilita emulacao de rastreamento (somente ambientes de desenvolvimento).

        Controlado por CRAWL_EMULATE; desligado por padrao para nunca afetar producao.
        """
        return os.getenv('CRAWL_EMULATE', 'false').strip().lower() in ('1', 'true', 'yes', 'on')

    def _emulated_crawl(self):
        """Emula um rastreamento bem-sucedido quando o banco real nao esta acessivel.

        Mantem os metadados ja existentes (ex.: snapshot de producao no SQLite) e,
        se a conexao ainda nao tiver metadados, gera um conjunto sintetico minimo
        para que a interface continue navegavel no ambiente de desenvolvimento.
        """
        existing = TableMetadata.objects.filter(database_connection=self.connection)
        if not existing.exists():
            self._generate_synthetic_metadata()

        self.connection.last_crawled = timezone.now()
        self.connection.save()

        return {
            'tables_count': TableMetadata.objects.filter(database_connection=self.connection, type='TABLE').count(),
            'views_count': TableMetadata.objects.filter(database_connection=self.connection, type='VIEW').count(),
            'fields_count': FieldMetadata.objects.filter(table__database_connection=self.connection).count(),
            'emulated': True,
        }

    def _generate_synthetic_metadata(self):
        """Cria metadados sinteticos deterministicos para a emulacao em dev."""
        specs = [
            ('TABELA_EXEMPLO', 'TABLE', [
                ('ID', 'INT', False, True),
                ('NOME', 'VARCHAR', True, False),
                ('DT_CRIACAO', 'DATETIME', True, False),
            ]),
            ('VW_EXEMPLO', 'VIEW', [
                ('ID', 'INT', True, False),
                ('NOME', 'VARCHAR', True, False),
            ]),
        ]
        for name, table_type, fields in specs:
            table = TableMetadata.objects.create(
                database_connection=self.connection,
                schema='dbo',
                name=name,
                type=table_type,
            )
            for fname, ftype, nullable, pk in fields:
                FieldMetadata.objects.create(
                    table=table,
                    name=fname,
                    data_type=ftype,
                    is_nullable=nullable,
                    is_primary_key=pk,
                )

    def crawl(self):
        """Crawl the database and extract metadata"""
        try:
            conn = self.connect()
        except Exception as connect_err:
            if self._emulation_enabled():
                logger.warning(
                    f"CRAWL_EMULATE ativo: emulando rastreamento de {self.connection} "
                    f"apos falha de conexao: {connect_err}"
                )
                return self._emulated_crawl()
            raise Exception(f"Erro ao rastrear banco de dados: {str(connect_err)}")

        try:
            cursor = conn.cursor()
            
            # Clear existing metadata for this connection
            TableMetadata.objects.filter(database_connection=self.connection).delete()
            
            # Get tables and views based on database type
            if self.connection.database_type == 'MSSQL':
                tables_query = """
                SELECT 
                    t.TABLE_SCHEMA as schema_name,
                    t.TABLE_NAME as table_name,
                    'TABLE' as table_type
                FROM 
                    INFORMATION_SCHEMA.TABLES t
                WHERE 
                    t.TABLE_TYPE = 'BASE TABLE'
                UNION
                SELECT 
                    v.TABLE_SCHEMA as schema_name,
                    v.TABLE_NAME as table_name,
                    'VIEW' as table_type
                FROM 
                    INFORMATION_SCHEMA.VIEWS v
                ORDER BY 
                    schema_name, table_name
                """
            elif self.connection.database_type == 'TERADATA':
                # in Teradata’s DBC.TablesV (and other DBC dictionary views), the TableKind column indicates the type of object the row describes. It isn’t limited only to “table” vs “view”; it covers many kinds of objects stored in the system dictionary. Here’s a comprehensive list of possible TableKind values and what they represent (based on the official Teradata documentation):
                # Value	Meaning (Object Type)
                # A	Aggregate function
                # B	Combined aggregate and ordered analytical function
                # C	Table operator parser contract function
                # D	JAR
                # E	External stored procedure
                # F	Standard function
                # G	Trigger
                # H	Instance or constructor method
                # I	Join index
                # J	Journal
                # K	Foreign server object
                # L	User-defined table operator
                # M	Macro
                # N	Hash index
                # O	Table with No Primary Index (NoPI table)
                # P	Stored procedure
                # Q	Queue table
                # R	Table function
                # S	Ordered analytical function
                # T	Table (regular table, either with primary index or partitioning)
                # U	User-defined type (UDT)
                # V	View
                # X	Authorization (role/user/etc.)
                # Y	GLOP set
                # Z	UIF (User Installed File)
                # 1	A DATASET schema object created by CREATE SCHEMA
                # 2	Function alias object
                # 3	Unbounded Array Framework (UAF) Time Series functions

                # Note: Some values (especially newer ones like K, L, Y, Z, 1/2/3) may depend on your Teradata version and optional features; core objects like tables (T), views (V), macros (M), indexes (I, N), and procedures (P) are universally present.

                tables_query = """
                SELECT 
                    DatabaseName as schema_name,
                    TableName as table_name,
                        CASE WHEN TableKind in ('O','T') THEN 'TABLE' ELSE 'VIEW' END as table_type
                FROM 
                    DBC.TablesV
                WHERE 
                    DatabaseName = ? AND
                        (TableKind in ('T', 'O', 'V'))
                ORDER BY 
                    schema_name, table_name
                """
                
            logger.debug(f"Executando consulta para obter tabelas e views")
            if self.connection.database_type == 'TERADATA':
                cursor.execute(tables_query, (self.connection.database,))
            else:
                cursor.execute(tables_query)
                
            tables_data = cursor.fetchall()
            
            # Process tables and views
            for table_row in tables_data:
                schema_name, table_name, table_type = table_row
                
                # Create table/view metadata
                table = TableMetadata.objects.create(
                    database_connection=self.connection,
                    schema=schema_name,
                    name=table_name,
                    type=table_type
                )
                
                # Get columns for this table/view based on database type
                if self.connection.database_type == 'MSSQL':
                    columns_query = """
                        SELECT 
                            c.COLUMN_NAME,
                            c.DATA_TYPE,
                            CASE WHEN c.IS_NULLABLE = 'YES' THEN 1 ELSE 0 END as is_nullable,
                            CASE WHEN pk.COLUMN_NAME IS NOT NULL THEN 1 ELSE 0 END as is_primary_key,
                            CASE WHEN fk.COLUMN_NAME IS NOT NULL THEN 1 ELSE 0 END as is_foreign_key,
                            COALESCE(fk.referenced_table_schema + '.' + fk.referenced_table_name, '') as foreign_key_table,
                            COALESCE(fk.referenced_column_name, '') as foreign_key_column
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
                                AND tc.TABLE_SCHEMA = ku.TABLE_SCHEMA
                                AND tc.TABLE_NAME = ku.TABLE_NAME
                            WHERE 
                                tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
                        ) pk ON c.TABLE_SCHEMA = pk.TABLE_SCHEMA 
                            AND c.TABLE_NAME = pk.TABLE_NAME 
                            AND c.COLUMN_NAME = pk.COLUMN_NAME
                        LEFT JOIN (
                            -- Foreign key columns info
                            SELECT 
                                sch1.name AS table_schema,
                                tab1.name AS table_name,
                                col1.name AS column_name,
                                sch2.name AS referenced_table_schema,
                                tab2.name AS referenced_table_name,
                                col2.name AS referenced_column_name
                            FROM 
                                sys.foreign_key_columns fkc
                            INNER JOIN sys.tables tab1 ON fkc.parent_object_id = tab1.object_id
                            INNER JOIN sys.schemas sch1 ON tab1.schema_id = sch1.schema_id
                            INNER JOIN sys.columns col1 ON fkc.parent_object_id = col1.object_id AND fkc.parent_column_id = col1.column_id
                            INNER JOIN sys.tables tab2 ON fkc.referenced_object_id = tab2.object_id
                            INNER JOIN sys.schemas sch2 ON tab2.schema_id = sch2.schema_id
                            INNER JOIN sys.columns col2 ON fkc.referenced_object_id = col2.object_id AND fkc.referenced_column_id = col2.column_id
                        ) fk ON c.TABLE_SCHEMA = fk.table_schema
                            AND c.TABLE_NAME = fk.table_name
                            AND c.COLUMN_NAME = fk.column_name
                        WHERE 
                            c.TABLE_SCHEMA = ?
                            AND c.TABLE_NAME = ?
                        ORDER BY 
                            c.ORDINAL_POSITION;
                    """
                    cursor.execute(columns_query, (schema_name, table_name))
                elif self.connection.database_type == 'TERADATA':
                    columns_query = """
                    SELECT 
                            ColumnName AS COLUMN_NAME,

                            /* Convert ColumnType code → descriptive data type name */
                            CASE ColumnType
                                WHEN 'I'  THEN 'INTEGER'
                                WHEN 'I1' THEN 'BYTEINT'
                                WHEN 'I2' THEN 'SMALLINT'
                                WHEN 'I8' THEN 'BIGINT'
                                WHEN 'D'  THEN 'DECIMAL'
                                WHEN 'F'  THEN 'FLOAT'
                                WHEN 'N'  THEN 'NUMBER'
                                WHEN 'BO' THEN 'BOOLEAN'

                                WHEN 'CV' THEN 'VARCHAR'
                                WHEN 'CF' THEN 'CHAR'
                                WHEN 'CO' THEN 'CLOB'
                                WHEN 'LV' THEN 'LONG VARCHAR'
                                WHEN 'LF' THEN 'LONG CHAR'

                                WHEN 'UV' THEN 'VARGRAPHIC'
                                WHEN 'UF' THEN 'GRAPHIC'
                                WHEN 'UO' THEN 'JSON'

                                WHEN 'DA' THEN 'DATE'
                                WHEN 'TS' THEN 'TIMESTAMP'
                                WHEN 'TZ' THEN 'TIME WITH TIME ZONE'
                                WHEN 'SZ' THEN 'TIMESTAMP WITH TIME ZONE'
                                WHEN 'AT' THEN 'INTERVAL DAY TO SECOND'
                                WHEN 'YM' THEN 'INTERVAL YEAR TO MONTH'

                                WHEN 'BV' THEN 'VARBYTE'
                                WHEN 'BF' THEN 'BYTE'
                                WHEN 'BO' THEN 'BLOB'
                                WHEN 'XM' THEN 'XML'
                                WHEN 'JN' THEN 'JSON'

                                WHEN 'PD' THEN 'PERIOD(DATE)'
                                WHEN 'PT' THEN 'PERIOD(TIME)'
                                WHEN 'PS' THEN 'PERIOD(TIMESTAMP)'
                                WHEN 'UT' THEN 'UDT'
                                WHEN 'DT' THEN 'DISTINCT TYPE'

                                ELSE ColumnType   /* fallback for any unknown codes */
                            END AS DATA_TYPE,

                            CASE WHEN Nullable = 'Y' THEN 1 ELSE 0 END AS is_nullable,
                            CASE WHEN ColumnConstraint = 'P' THEN 1 ELSE 0 END AS is_primary_key,
                            CASE WHEN ColumnConstraint = 'F' THEN 1 ELSE 0 END AS is_foreign_key,
                            '' AS foreign_key_table,
                            '' AS foreign_key_column

                        FROM DBC.ColumnsV
                        WHERE DatabaseName = ? AND TableName = ?
                        ORDER BY ColumnId;
                    """
                    cursor.execute(columns_query, (schema_name, table_name))
                columns_data = cursor.fetchall()
                
                # Teradata ColumnType Codes and Descriptions
                # Numeric Types
                # Code     Meaning
                # I        INTEGER (4-byte signed)
                # I1       BYTEINT (1-byte signed)
                # I2       SMALLINT (2-byte signed)
                # I8       BIGINT (8-byte signed)
                # F            FLOAT / REAL (4-byte)
                # D            DECIMAL / NUMERIC (packed)
                # N            NUMBER (ANSI)
                # BO       BOOLEAN
                # Character Types
                # Code     Meaning
                # CV       VARCHAR
                # CF       CHAR / CHARACTER
                # CO       CLOB
                # LV       LONG VARCHAR
                # LF       LONG CHAR
                # Unicode / Graphic Types
                # Code     Meaning
                # UV       VARGRAPHIC
                # UF       GRAPHIC
                # UO       JSON (stored as Unicode object)
                # MC       CHARACTER SET UNICODE (internal code used rarely)
                # Date / Time Types
                # Code     Meaning
                # DA       DATE
                # TS       TIMESTAMP
                # TZ       TIME WITH TIME ZONE
                # SZ       TIMESTAMP WITH TIME ZONE
                # AT       INTERVAL DAY TO SECOND
                # YM       INTERVAL YEAR TO MONTH
                # Byte / Binary Types
                # Code     Meaning
                # BV       VARBYTE
                # BF       BYTE / BYTE(n)
                # BO       BLOB
                # XM       XML
                # JN       JSON
                # PM       Parameterized JSON
                # Other / Specialized Types
                # Code     Meaning
                # PD       PERIOD DATE
                # PT       PERIOD TIME
                # PS       PERIOD TIMESTAMP
                # PM       TD_ANYTYPE (polymorphic parameter type)
                # UT       User-defined Type (UDT)
                # DT       Distinct Type
                # UD       UDT (generic code in older versions)
                
                # Process columns
                print (f'processando colunas da tabela {table.name}...')
                for column_row in columns_data:
                    column_name, data_type, is_nullable, is_primary_key, is_foreign_key, foreign_key_table, foreign_key_column = column_row
                    
                    # Create column metadata
                    FieldMetadata.objects.create(
                        table=table,
                        name=column_name,
                        data_type=data_type,
                        is_nullable=bool(is_nullable),
                        is_primary_key=bool(is_primary_key),
                        is_foreign_key=bool(is_foreign_key),
                        foreign_key_table=foreign_key_table if foreign_key_table else None
                    )
            
            # Update last crawled timestamp
            self.connection.last_crawled = timezone.now()
            self.connection.save()
            
            conn.close()
            
            return {
                'tables_count': TableMetadata.objects.filter(database_connection=self.connection, type='TABLE').count(),
                'views_count': TableMetadata.objects.filter(database_connection=self.connection, type='VIEW').count(),
                'fields_count': FieldMetadata.objects.filter(table__database_connection=self.connection).count()
            }
            
        except Exception as e:
            raise Exception(f"Erro ao rastrear banco de dados: {str(e)}")


# def search_metadata(query):
#     """Pesquisa por metadados que correspondam à string de consulta"""
#     # Pesquisa em tabelas
#     tables = TableMetadata.objects.filter(name__icontains=query) | \
#              TableMetadata.objects.filter(schema__icontains=query)
    
#     # Pesquisa em campos
#     fields = FieldMetadata.objects.filter(name__icontains=query) | \
#              FieldMetadata.objects.filter(data_type__icontains=query)
    
#     # Pesquisa em comentários
#     from .models import MetadataComment
#     comments = MetadataComment.objects.filter(comment__icontains=query)
    
#     return {
#         'tables': tables,
#         'fields': fields,
#         'comments': comments
#     }


def search_metadata(query):
    """Pesquisa por metadados com suporte a múltiplas palavras em qualquer ordem.

    Combina tokens com AND (todas as palavras devem aparecer) e busca em múltiplos campos
    com OR por modelo: Tabelas (name, schema, type), Campos (name, data_type), Comentários (comment).
    """
    tokens = [t for t in (query or '').strip().split() if t]

    # Tabelas: para cada token, ele pode aparecer em name OU schema OU type; todos os tokens devem aparecer
    tables_q = Q()
    for t in tokens:
        tables_q &= (Q(name__icontains=t) | Q(schema__icontains=t) | Q(type__icontains=t))
    tables = TableMetadata.objects.filter(tables_q).distinct() if tokens else TableMetadata.objects.none()

    # Campos: name OU data_type; todos os tokens devem aparecer
    fields_q = Q()
    for t in tokens:
        fields_q &= (Q(name__icontains=t) | Q(data_type__icontains=t))
    fields = FieldMetadata.objects.filter(fields_q).distinct() if tokens else FieldMetadata.objects.none()

    # Comentários: em comment; todos os tokens devem aparecer
    comments_q = Q()
    for t in tokens:
        comments_q &= Q(comment__icontains=t)
    comments = MetadataComment.objects.filter(comments_q).distinct() if tokens else MetadataComment.objects.none()

    return {
        'tables': tables,
        'fields': fields,
        'comments': comments
    }
