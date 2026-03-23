import os

import subprocess
import base64
from pathlib import Path

import logging

logger = logging.getLogger(__name__)


def autenticar_usuario():
   #pega dados do usuário de serviço nas variáveis de ambiente
   username = os.getenv('username_dlo')
   psw = os.getenv('password_dlo')
   # logger.debug(username)

   #autentica o usuário no LDAP (Kerberos)
   autenticar_usuario_kinit(username,psw)
   # logger.info("Usuário autenticado via kinit")
   return [username, psw]


def autenticar_usuario_kinit(login_usuario, senha_usuario):
   out = None
  
   # logger.debug('autentica no kerberos com autenticar_usuario_kinit')
   ambiente = os.environ.get('OS','')
   if "WIN" in ambiente.upper():
       #se for windows não faz nada
       logger.info("Windows, não faz nada")
       out = None
      
   else:
       #logar(os.environ.get('OS',''))
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
       logger.debug(f"klist: {result.stdout}")

   return out

 

#######exemplo

if __name__ == "__main__":
    logger.info(f"usuario: {os.getenv('username_dlo')}")
    autenticar_usuario_kinit( os.getenv('username_dlo'), os.getenv('password_dlo') )

 
def ensure_kerberos_ticket():
    ambiente = os.environ.get('OS','')
    if "WIN" in ambiente.upper():
        logger.info("Windows, não faz nada")
        return None

    kinit_habilitado = os.getenv('KINIT_HABILITADO', 'false').strip().lower() == 'true'
    principal = os.getenv('APP_USER') or os.getenv('username_dlo')
    senha = os.getenv('APP_PASS') or os.getenv('password_dlo')
    keytab_b64 = Path('/app/secrets/cloud.keytab.b64')
    keytab_file = Path('/app/secrets/cloud.keytab')

    out = None
    if kinit_habilitado and keytab_b64.exists():
        if not principal:
            raise Exception("APP_USER (principal) não definido para autenticação via keytab")
        if not keytab_file.exists():
            decoded = base64.b64decode(keytab_b64.read_bytes())
            keytab_file.write_bytes(decoded)
        with subprocess.Popen(["kinit", "-kt", str(keytab_file), principal], stderr=subprocess.PIPE, stdout=subprocess.PIPE) as kinit_cmd:
            out = kinit_cmd.communicate()[1]
        logger.info("Autenticado via keytab")
    elif principal and senha:
        with subprocess.Popen(["echo", senha], stdout=subprocess.PIPE) as echo_cmd:
            with subprocess.Popen(["kinit", principal], stderr=subprocess.PIPE, stdin=echo_cmd.stdout, stdout=subprocess.PIPE) as kinit_cmd:
                out = kinit_cmd.communicate()[1]
            echo_cmd.stdout.close()
        logger.info("Autenticado via senha (kinit)")
    else:
        logger.warning("Principal/senha não definidos para kinit; pulando autenticação")

    result = subprocess.run(['klist'], capture_output=True, text=True, check=False)
    logger.debug(f"klist: {result.stdout}")
    return out

 