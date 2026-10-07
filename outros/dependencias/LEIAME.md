# Cadastro de metadados de dependências de views do SQL Server

- rode localmente (usa autenticação integrada do Windows)
- execute: python extract.py [xxx]
    - onde xxx é o nome do banco de dados (default=desig_cadastro)
- cria ou atualiza o arquivo lineage.json, onde cada view é representada por um objeto com as props:
    - object: nome da view com banco.schema.nome
    - sources: array de objetos (views e tabelas) das quais o objeto depende
    - ex.: 
        {
            "object": "reprebh.dbo.CONS_SFN_Nao_Consolidados",
            "sources": [
                "dsin01.dbo.cad_unicad",
                "reprebh.dbo.dbo.cons_sfn_cnpjs_nao_consolidados"
            ],
            "status": "success"
        },
    - obs.: objetos são acrescentados ou atualizados mas não apagados


# Modificadores DML (INSERT / SELECT INTO / UPDATE / DELETE)

- o mesmo `extract.py` também cria/atualiza `modifiers.json`, que documenta
  quais comandos DML afetam cada tabela e em qual função/stored procedure
- varre as rotinas de TODOS os bancos acessíveis do servidor (para capturar
  modificações cross-database, ex.: `INSERT INTO OUTRO_BANCO..tabela`)
- formato (agrupado por tabela alvo):
    {
        "table": "reprebh.dbo.cosif_contas_finais",
        "modifiers": [
            {
                "command": "INSERT",
                "routine": "reprebh.dbo.Atualiza_COSIF_Contas_Finais",
                "routine_type": "PROCEDURE"
            }
        ]
    }
- obs.: tabelas são acrescentadas ou atualizadas mas não apagadas
- detalhes de implementação e produção: docs/lineage_modifiers.md


# Consulta de dependências

- requer que o arquivo lineage.json esteja gravado no diretório do arquivo dependencias.html
- requer um servidor de arquivos para conseguir carregar o .json
- para consultar um banco/view por default, passe parâmetros bd/tbl na url
    - ex.: http://localhost:5500/dependencies.html?db=reprebh&tbl=reprebh.dbo.lim_limites_calculados_mensaisdiarios




