# NeoMarketplace no Windows

## Arquitetura da tarefa 1

A tarefa 1 está implementada com **FastAPI**, não com Django. O endpoint `POST /api/v1/products` fica em `app/main.py`, e os testes automatizados ficam em `tests/test_products.py`.

Não é necessário instalar Django para executar esta versão. FastAPI foi escolhido porque a entrega atual é um serviço B2B focado em API, validação de JSON, contrato OpenAPI e testes de endpoint. Django só deve ser introduzido posteriormente se o projeto precisar de um painel administrativo completo, ORM e estrutura de aplicação web mais abrangente.

## Requisitos

Instale no Windows:

1. Python 3.10 ou superior, disponível em [python.org](https://www.python.org/downloads/windows/).
2. Git para Windows, disponível em [git-scm.com](https://git-scm.com/download/win).
3. Visual Studio Code, opcional, para editar o projeto.

Durante a instalação do Python, marque **Add Python to PATH**.

## Instalação pelo PowerShell

Abra o PowerShell na pasta do projeto e permita scripts apenas para o processo atual:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup_windows.ps1
```

O script cria o ambiente virtual `.venv` e instala as dependências de `requirements.txt`.

## Executar os testes

```powershell
.\test_windows.ps1
```

O resultado esperado é semelhante a `6 passed`.

## Iniciar a API

```powershell
.\run_windows.ps1
```

Acesse a documentação interativa em <http://127.0.0.1:8000/docs> e o health check em <http://127.0.0.1:8000/health>.

## Publicar a branch da tarefa

A publicação deve ser feita na pasta que contém este projeto:

```powershell
git remote set-url origin git@github.com:luisfernandoneto11/market.git
git switch task-01-create-product
git push -u origin task-01-create-product
```

Para confirmar a autenticação SSH antes do push:

```powershell
ssh -T git@github.com
```

## Alternativa sem scripts PowerShell

Se a política do computador bloquear arquivos `.ps1`, execute diretamente:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```
