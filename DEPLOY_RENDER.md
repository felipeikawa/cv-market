# C&V MARKET — preparação para Render

Nenhum serviço é criado por estes arquivos. O deploy deve ser realizado em uma etapa posterior.

## Configuração do futuro Web Service

- Runtime: Python (recomendado Python 3.11).
- Build Command: `pip install -r requirements.txt`.
- Start Command: `gunicorn --bind 0.0.0.0:$PORT app:app` (igual ao Procfile).
- Health Check Path: `/health`.
- O Render fornece `PORT` e `RENDER=true`. Não copiar o prefixo `web:` do Procfile para o Start Command.
- Desabilitar deploy automático caso os próximos pushes ainda não devam publicar alterações.

## Variáveis de ambiente

- `APP_ENV=production`: explicita produção. `RENDER=true` também força produção, mesmo que APP_ENV indique desenvolvimento.
- `DATABASE_URL`: conexão PostgreSQL do Session Pooler Supabase, com credenciais escapadas para URL. Configurar como segredo no painel. Nunca registrar seu valor.
- `SECRET_KEY`: segredo forte e aleatório, estável entre reinicializações. Configurar como segredo no painel.
- `PORT`: fornecida pelo Render; o Gunicorn escuta em `0.0.0.0` nessa porta.
- `PYTHON_VERSION`: usar uma versão completa suportada de Python 3.11 na criação do serviço.

Não definir `FLASK_DEBUG=1` em produção. O código mantém debug desligado em produção e exige PostgreSQL, sem fallback para SQLite. Cookies de sessão usam Secure, HttpOnly e SameSite=Lax em produção, que requer HTTPS.

O `.env` é carregado explicitamente da raiz apenas em desenvolvimento, sem substituir variáveis já existentes. Em produção as variáveis devem vir do ambiente do serviço. A inicialização de produção não cria tabelas, não migra bancos e não altera usuários. O schema atual já foi migrado; mudanças futuras de schema precisam de uma etapa própria.

## Administrador inicial

O Supabase migrado já possui usuários: não é necessário executar bootstrap.
Para uma instalação futura com schema pronto e **sem nenhum usuário**, definir temporariamente `BOOTSTRAP_ADMIN_NAME`, `BOOTSTRAP_ADMIN_EMAIL` e `BOOTSTRAP_ADMIN_PASSWORD` (mínimo 8 caracteres) e executar uma única vez, de forma controlada:

```sh
flask --app app bootstrap-admin
```

O comando não altera nem recria usuários se a base já tiver qualquer usuário. Remover as variáveis de bootstrap após o uso. Não executar simultaneamente. Em desenvolvimento, o bootstrap de uma base vazia continua disponível ao iniciar o app.

## XMLs e uploads

O filesystem padrão do Render é efêmero. Por isso, em produção, a aplicação lê o XML enviado em memória e grava apenas os dados extraídos no PostgreSQL. Não grava XML em disco e não oferece download/consulta do arquivo original. A tela de importação avisa para guardar uma cópia.

Os caminhos de XML importados do SQLite continuam sendo apenas referências: os arquivos locais não estão no Render. Listagem de NF-e, detalhes, produtos da nota e conferências continuam usando o banco. Até integrar armazenamento persistente, não haverá recuperação, download nem arquivamento dos XMLs originais pelo serviço. `XML_STORAGE_DIR` vale somente para o arquivamento em desenvolvimento; defini-la não habilita persistência em produção. Supabase Storage não foi implementado.

## Desenvolvimento e validação

```sh
python3 -m pip install -r requirements.txt
python3 app.py
```

Sem DATABASE_URL, o desenvolvimento usa `database/cv_market.db`. Para testar SQLite quando o `.env` contém a conexão remota, `DATABASE_URL='' python3 app.py` evita utilizar essa conexão. `FLASK_DEBUG=1` habilita debug somente em desenvolvimento. SECRET_KEY deve estar no ambiente ou no `.env` local.

Testes isolados (criam apenas dados sintéticos em diretório temporário, sem carregar o `.env` real):

```sh
python3 -m unittest discover -s tests -v
python3 -m pip check
```

O `/health` retorna somente `{"status":"ok"}` sem consultar banco; valida o processo HTTP, não a disponibilidade do PostgreSQL.

## Arquivos privados e logs

Não versionar `.env`, bancos SQLite, uploads, XML/PDF reais, ambientes virtuais nem credenciais. O `.gitignore` cobre esses arquivos; ele não remove arquivos já rastreados. Revisar `git status` antes de qualquer commit futuro. Erros internos de produção registram somente a classe da exceção, sem traceback, parâmetros SQL ou connection string. Não habilitar logs de debug SQL/driver ou dumps de ambiente.

Referências: [Flask no Render](https://render.com/docs/deploy-flask), [variáveis do Render](https://render.com/docs/environment-variables), [filesystem e deploys](https://render.com/docs/deploys).
