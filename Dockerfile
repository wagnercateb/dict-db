# Django BCCloud: ver Template (do Ezer) com as configurações necessárias para uso do Django pelo Desig na BCCloud com Single-Sign On e outras configurações.
# https://tfs.bcnet.bcb.gov.br/tfs/LiaCollection/DESIG_JOBS/_git/dimac-colop-dict-db?path=%2FDockerfile

FROM docker-lia.repo.bcnet.bcb.gov.br/base/python3.11:0.0.3

RUN echo "deb https://repo.bcnet.bcb.gov.br/debian bullseye main" > /etc/apt/sources.list && \
    echo "deb https://repo.bcnet.bcb.gov.br/debian-security bullseye-security main" >> /etc/apt/sources.list && \
    echo "deb https://repo.bcnet.bcb.gov.br/debian bullseye-updates main" >> /etc/apt/sources.list
RUN curl --silent https://repo.bcnet.bcb.gov.br/docker-lia/keys/microsoft.asc | apt-key add - && \
    echo "deb https://repo.bcnet.bcb.gov.br/ubuntu-microsoft/20.04/prod/ focal main" > /etc/apt/sources.list.d/mssql-release.list


# instala pip sem pedir confirmação (-y): só usar no wsl; no azure/kubernetes dá erro
# RUN apt-get update && apt-get install -y python3-pip unixodbc
RUN apt-get update 

# Configura cache Kerberos KCM conforme diretriz da BcCloud
RUN sed -i "s/\[libdefaults\]/[libdefaults]\n    default_ccache_name = KCM:/g" /etc/krb5.conf || true

RUN mkdir /dados
RUN mkdir /dados/dict-db

# working directory for the project. Este será o ROOT DA APLICAÇÃO. 
WORKDIR /app

# copia o arquivo requirements.txt (no mesmo diretório desse Dockerfile) para o working directory do projeto definido acima (.)
COPY requirements.txt .
# roda um comando no prompt para install dependencies do nosso projeto Python
RUN pip install -r requirements.txt

# copia os arquivos da application para o workdir (/app, definido acima)
COPY *.py .

# em produção, o banco de dados ficará em /dados/dict-db/dict-db.sqlite3
# COPY ./dict-db.sqlite3 .

# ADD copia o folder inteiro com seu conteúdo
# os diretórios são RECRIADOS DO ZERO, dentro de /app, pois este é o WORKDIR do app
ADD metadata_crawler metadata_crawler
ADD db_metadata_crawler db_metadata_crawler

# RUN pip install -r requirements.txt -i http://artifactory/artifactory/api/pypi/pypi/simple --trusted-host artifactory

# PARA APPS DJANGO: Exponha a porta em que a aplicação vai rodar
# (porta default do Kubernetes é 8080 mas uso 5000 porque, no sbcdf70c, tem que debugar nessa porta)
EXPOSE 5000

#CMD ["python", "manage.py", "runserver", "0.0.0.0:5000", "--noreload"]
CMD ["sh", "-c", "python manage.py migrate && python manage.py runserver 0.0.0.0:5000 --noreload"]


