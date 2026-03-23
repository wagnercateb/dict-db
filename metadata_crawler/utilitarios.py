
#para autenticacao kinit
import os
import subprocess

#para usar o objeto logger default do python
import logging

#para detectar o ambiente em que o docker está rodando
import platform



def autenticar_usuario_kinit(login_usuario, senha_usuario):
    logger.info('entrou em autenticar_usuario_kinit')
    out = None
    
    logger.info('autentica no kerberos com autenticar_usuario_kinit')
    ambiente = os.environ.get('OS','')
    if "WIN" in ambiente.upper():
        #se for windows não faz nada
        logger.info("Windows, não faz nada")
        out = None
        
    else:
        logger.info(os.environ.get('OS',''))
        if login_usuario is not None:
            
            # faz 'echo' do conteúdo da variável 'senha_usuario' e armazena-o na variável local echo_cmd.stdout
            # echo_cmd é o resultado do 'with subprocess', então ele está disponível no bloco seguinte, onde
            #   a senha obtida aqui será usada como echo_cmd.stdout, no argumento 'stdin' do próximo subprocesso
            with subprocess.Popen(
                ["echo", senha_usuario],
                stdout=subprocess.PIPE #, shell = True

            ) as echo_cmd:
                #autentica o usuário no LDAP (Kerberos)
                with subprocess.Popen(
                    ["kinit", login_usuario],
                    stderr=subprocess.PIPE,
                    stdin=echo_cmd.stdout,
                    stdout=subprocess.PIPE,
                ) as kinit_cmd:
                    out = kinit_cmd.communicate()[1]
                    logger.info("autenticou no Linux")
                echo_cmd.stdout.close()

        # After running kinit, you should see a ticket when you execute 'klist'
        # If not, there may be an issue with your Kerberos configuration or the credentials provided.
        result = subprocess.run(['klist'], capture_output=True, text=True, check=False)
        logger.info('KINIT AUTENTICOU: klist: ', result.stdout)

    return out


def autenticar_usuario():
    logger.info('entrou em autenticar_usuario')
    #pega dados do usuário de serviço nas variáveis de ambiente
    username = os.getenv('username_dlo')
    psw = os.getenv('password_dlo')
    logger.info(username)

    #autentica o usuário no LDAP (Kerberos)
    autenticar_usuario_kinit(username,psw)
    logger.info(str(username) + " autenticou")
    return [username, psw]



def detect_runtime_environment():
    env = os.getenv('ENVIRONMENT')
    if env: return env

    # Check if running in Docker
    in_docker = os.path.exists('/.dockerenv') 
    # esse código não rodou no windows:
    # or any(
    #     'docker' in line or 'containerd' in line
    #     for line in open('/proc/1/cgroup', 'rt', errors='ignore')
    # )

    # Check for Kubernetes
    in_kubernetes = os.environ.get('KUBERNETES_SERVICE_HOST') is not None

    # Check if running in WSL
    uname_release = platform.uname().release.lower()
    in_wsl = 'microsoft' in uname_release or 'wsl' in uname_release

    # Check if running on native Windows
    system_name = platform.system()
    in_native_windows = system_name == 'Windows'

    # Now determine environment type
    if in_kubernetes:
        return 'kubernetes'
    elif in_docker and in_wsl:
        return 'docker-wsl'
    elif in_docker:
        return 'docker-other'
    elif in_wsl:
        return 'wsl-host'
    elif in_native_windows:
        return 'windows'
    else:
        return 'bare-metal'


# log default do Django (usado em outros módulos)
logger = logging.getLogger(__name__)
# logger.info(f"Logger name: {logger.name}")    #aqui: metadata_crawler.utils 
# testes do log:
# logger.debug("This is a debug message.")
# logger.info("This is an info message.")
# logger.warning("This is a warning.")
# logger.error("This is an error.")
# logger.critical("This is critical.")


#retorna string com as props do objeto
def obj_props(obj):
    descricao = ''
    for attr in dir(obj):
        if not attr.startswith( '__'):
            value = getattr(obj, attr)
            if not callable(value):
                descricao += f"{attr} = {value}; "
    return descricao


 #só usados por causa da funcao logar():
# from datetime import datetime
# import platform
# from pathlib import Path
# BASE_DIR = Path(__file__).resolve().parent.parent
# # Set database path based on OS
# if platform.system() == "Windows":
#     DB_FILE_FULLPATH = BASE_DIR / 'dict-db.sqlite3'  # Development
# else:
#     DB_FILE_FULLPATH = '/dados/dict-db/dict-db.sqlite3'  # Production
# def logar(*msg):
#     msg = ' '.join(str(part) for part in msg)
#     try:
#         with open('___log.txt', "a", encoding='utf-8') as f:        
#             f.write(datetime.now().strftime("%c") + '   ' + msg + '\n')        
#     except Exception as e:
#         logger.info(str(e    ))
#     logger.info(msg)
# logar('teste logar')
