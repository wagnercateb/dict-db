Para testar local:

- baixe o arquivo atualizado do sqlite usando o FileManager: https://dimac-colop-flaskdesig-jobs.cloud-p.bcnet.bcb.gov.br/filemanager/dados/dict-db
- abra um prompt no VSCode e execute: wsl
    - diretório linux: /c/Users/desig.cateb/Dados/Bacen/ProjetosTFS/desig-jobs__________BcCloud/dimac-colop-dict-db
- copie o arquivo atualizado do sqlite para: C:\Users\desig.cateb\Dados\bacen\ProjetosTFS\desig-jobs__________BcCloud\dimac-colop-dict-db\
- faça o build: docker build .
- veja o hash da imagem criada: docker images
- execute expondo a porta 5000 e mapeando o diretório corrente para /dados/dict-db: 
        docker run -d 
            -p 5000:5000  
            -v /c/Users/desig.cateb/Dados/Bacen/ProjetosTFS/desig-jobs__________BcCloud/dimac-colop-dict-db/:/dados/dict-db hash-da-imagem
- navegue: localhost:5000  
- para debugar dentro do container:
    - ver o container_id com: docker ps
    - acesse o bash (ou o sh) do container: docker exec -it container_id bash

Para fechar o container:

- veja o número do container em execução: docker ps (-a lista também os que estão parados)
- pare o container: docker stop hash-do-cotainer
- apague este container: docker rm 1a6
    - ou apague todos: docker rm -f $(docker ps -aq)
- apague sua imagem se não for mais usar: docker rmi hash-da-imagem



