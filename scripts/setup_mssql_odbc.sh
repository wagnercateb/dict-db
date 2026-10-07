#!/usr/bin/env bash
#
# Instala o driver ODBC do Microsoft SQL Server no Linux e registra o alias
# legado "SQL Server" para que as connection strings da aplicacao
# (Driver={SQL Server}) continuem funcionando fora do Windows/producao.
#
# Em producao o driver legado {SQL Server} ja existe (base image BcCloud).
# Em ambientes de desenvolvimento Linux ele nao existe, o que gera o erro:
#   "Can't open lib 'SQL Server' : file not found"
#
# Este script emula o comportamento de producao mapeando {SQL Server} para o
# ODBC Driver 17 (mesmo comportamento do driver legado: sem criptografia
# obrigatoria). Nao altera o codigo da aplicacao nem o Teradata.
#
# Idempotente. Requer root.

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Execute como root (sudo)." >&2
    exit 1
fi

if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
fi
UBUNTU_VERSION="${VERSION_ID:-24.04}"

MS_KEYRING="/etc/apt/keyrings/microsoft-prod.gpg"
MS_LIST="/etc/apt/sources.list.d/mssql-release.list"

install_ms_repo() {
    if [ -f "$MS_LIST" ] && [ -f "$MS_KEYRING" ]; then
        return
    fi
    mkdir -p /etc/apt/keyrings
    curl -sSL https://packages.microsoft.com/keys/microsoft.asc \
        | gpg --dearmor -o "$MS_KEYRING"
    curl -sSL "https://packages.microsoft.com/config/ubuntu/${UBUNTU_VERSION}/prod.list" \
        -o "$MS_LIST"
    # Garante que o repositorio use a chave recem-instalada.
    sed -i "s|signed-by=[^]]*|signed-by=${MS_KEYRING}|" "$MS_LIST"
}

install_ms_repo

# Instala unixODBC + msodbcsql17 somente se ainda nao estiverem presentes.
if ! command -v odbcinst >/dev/null 2>&1 || [ -z "$(ls /opt/microsoft/msodbcsql17/lib64/libmsodbcsql-*.so.* 2>/dev/null)" ]; then
    apt-get update -o Dir::Etc::sourcelist="sources.list.d/mssql-release.list" \
        -o Dir::Etc::sourceparts="-" -o APT::Get::List-Cleanup="0"
    ACCEPT_EULA=Y DEBIAN_FRONTEND=noninteractive apt-get install -y unixodbc msodbcsql17
fi

DRIVER_LIB="$(ls /opt/microsoft/msodbcsql17/lib64/libmsodbcsql-*.so.* | head -n1)"

# Registra o alias legado apenas se ainda nao existir, para nunca sobrescrever
# o driver usado em producao.
if ! odbcinst -q -d -n "SQL Server" >/dev/null 2>&1; then
    {
        echo ""
        echo "[SQL Server]"
        echo "Description=Legacy alias for Microsoft SQL Server (maps to ODBC Driver 17)"
        echo "Driver=${DRIVER_LIB}"
        echo "UsageCount=1"
    } >> /etc/odbcinst.ini
    echo "Alias 'SQL Server' registrado apontando para ${DRIVER_LIB}"
else
    echo "Alias 'SQL Server' ja registrado; nada a fazer."
fi

echo "Drivers ODBC disponiveis:"
odbcinst -q -d
