@echo off
echo Ativando ambiente virtual...
call venv311\Scripts\activate

echo Aplicando migrações...
python manage.py migrate

echo Criando superusuário...
python manage.py createsuperuser

pause
