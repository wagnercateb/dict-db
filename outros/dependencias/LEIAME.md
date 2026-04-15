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


# Consulta de dependências

- requer que o arquivo lineage.json esteja gravado no diretório do arquivo dependencias.html
- requer um servidor de arquivos para conseguir carregar o .json
- para consultar um banco/view por default, passe parâmetros bd/tbl na url
    - ex.: http://localhost:5500/dependencies.html?db=reprebh&tbl=reprebh.dbo.lim_limites_calculados_mensaisdiarios




