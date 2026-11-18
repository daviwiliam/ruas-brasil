# RUAS BRASIL

Portal editorial de divulgação de artistas independentes de Piraquara e região
(música, artes visuais, jogos, audiovisual, literatura e moda).

O artista envia o material → a equipe editorial revisa, edita e **aprova ou
rejeita** → apenas materiais aprovados aparecem como matérias públicas.
Não é rede social nem loja. Relaciona-se ao **ODS 8, meta 8.3** (apoio à
criatividade e ao empreendedorismo); a divulgação **não garante** renda,
venda ou contratação.

## Sumário
- [Tecnologias](#tecnologias)
- [Estrutura](#estrutura)
- [Rodando localmente](#rodando-localmente)
- [Administração do conteúdo](#administração-do-conteúdo)
- [Testes e CI](#testes-e-ci)
- [Segurança e privacidade](#segurança-e-privacidade)
- [Desempenho e medição de LCP](#desempenho-e-medição-de-lcp)
- [Produção](#produção)
- [Decisões, limitações e pendências](#decisões-limitações-e-pendências)

## Tecnologias

Python 3.12 · Django 5.2.19 · PostgreSQL (testado no 17) · Psycopg 3.3 ·
Pillow 12.3 · Gunicorn 23 · Coverage 7 · GitHub Actions. Monolito MVT com
templates Django; JavaScript só para levar o foco ao resumo de erros
(`portal/static/portal/js/foco-erros.js`).

## Estrutura

```
config/                 configurações (lidas de variáveis de ambiente), URLs, WSGI
portal/
  models.py             Artista, Categoria, Material (+ restrições) e ControleLogin
  services.py           regras de envio, aprovação e rejeição (testáveis, checam permissão)
  imagens.py            validação real (Pillow) e reprocessamento em WebP sem metadados
  forms.py              formulário público, formulário editorial e login limitado
  login_limiter.py      limite de 5 falhas/15 min por conta ou IP
  middleware.py         Content-Security-Policy
  views.py, urls.py     portal público e entrega protegida de imagens
  admin.py              painel editorial (aprovar/rejeitar via POST)
  management/commands/  carregar_categorias, popular_demo, criar_admin
  templates/, static/   HTML semântico e CSS responsivo
  tests/                121 testes (Django TestCase + Client)
templates/              base, 404, 500 e personalizações do admin
docs/                   capturas de tela, descrição de PR e checklist
```

## Rodando localmente

Pré-requisitos: Python 3.12 (3.13 também funciona) e PostgreSQL. O Docker é
**opcional**, só para subir o PostgreSQL.

### 1. Banco de dados

**Opção A – Docker Compose** (usa os valores de `.env`):

```bash
docker compose up -d          # PostgreSQL em 127.0.0.1:5432
# se a porta 5432 já estiver ocupada:  POSTGRES_PORT=5433 docker compose up -d
```

**Opção B – PostgreSQL já instalado:**

```sql
CREATE USER ruas_brasil WITH PASSWORD 'troque-esta-senha';
CREATE DATABASE ruas_brasil OWNER ruas_brasil;
ALTER USER ruas_brasil CREATEDB;  -- necessário para o banco de testes
```

**Opção C – SQLite (somente demonstração):** defina `DJANGO_DB_ENGINE=sqlite`
no `.env`. Não substitui a validação em PostgreSQL.

### 2. Ambiente virtual e dependências

Linux/macOS:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # ajuste POSTGRES_* e DJANGO_SECRET_KEY
```

Windows (PowerShell):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env   # ajuste POSTGRES_* e DJANGO_SECRET_KEY
```

> No Windows, use `POSTGRES_HOST=127.0.0.1` (não `localhost`): a tentativa via
> IPv6 pode deixar a conexão lenta.

Para gerar uma chave: `python -c "import secrets; print(secrets.token_urlsafe(50))"`.

### 3. Migrações, categorias, administrador e demonstração

```bash
python manage.py migrate
python manage.py carregar_categorias
python manage.py criar_admin seu_usuario --email voce@example.com   # pede a senha
python manage.py popular_demo                       # Lua Norte – "Vozes do Bairro" (pendente)
python manage.py popular_demo --quantidade 100 --aprovar-como seu_usuario   # opcional: 100 publicações fictícias
python manage.py runserver
```

- Portal: <http://127.0.0.1:8000/>
- Painel: <http://127.0.0.1:8000/painel/>

`criar_admin` valida a senha (mínimo de 12 caracteres, sem senhas comuns,
numéricas ou parecidas com o usuário). Use `--editor` para criar um editor
(grupo *Editores*) em vez de superusuário. Em automação, a senha pode vir de
`RUAS_ADMIN_PASSWORD`; ela nunca é aceita como argumento. **Nenhum comando cria
usuário com senha padrão.** Evite `createsuperuser` com
`DJANGO_SUPERUSER_PASSWORD`: nesse modo o Django não valida a força da senha.

## Administração do conteúdo

1. Entre em `/painel/` → **Materiais** → filtre por *Status: Pendente*.
2. Abra o material: edite título, descrição, categoria, texto alternativo e
   links. **Salvar não publica.**
3. Use **✓ Aprovar e publicar** ou **✕ Rejeitar** (formulários POST com CSRF,
   restritos à permissão `portal.avaliar_material`). O sistema registra quem
   avaliou, quando, e a data de publicação. Ações em lote também existem.
4. Rejeitar um material aprovado o retira do portal.
5. Bloqueios de login aparecem em **Controles de login**; excluir o registro
   desbloqueia a conta ou o IP.

**Duplicidades de artista.** Sem conta de artista no MVP, cada envio cria um
novo `Artista`, mesmo com nome ou e-mail iguais (coincidência não prova
identidade). Para consolidar: no material, escolha o cadastro correto no campo
*Artista* e exclua o registro que ficou sem materiais (a exclusão de artista com
materiais é bloqueada por `PROTECT`).

## Testes e CI

```bash
python manage.py test                 # usa PostgreSQL conforme o .env
coverage run manage.py test && coverage report
```

O workflow `.github/workflows/ci.yml` (Python 3.12 e serviço PostgreSQL 17)
instala as dependências e executa `makemigrations --check`, `check`,
`check --deploy`, `collectstatic` e os testes com cobertura (falha abaixo de 85 %).

**Resultados medidos neste ambiente (17/11/2026):**

| Ambiente | Resultado |
|---|---|
| Python 3.13.7 + PostgreSQL 17 (Docker), Windows 11 | 121 testes, todos passaram; cobertura 94 % (linhas + ramos) |
| Python 3.12.16 (container `python:3.12-slim`) + PostgreSQL 17, DEBUG=False, mesmas etapas do CI | 120 testes, todos passaram; cobertura 94 %; `check --deploy` sem avisos; `collectstatic` ok |
| Python 3.13.7 + SQLite | 120 testes, todos passaram |

As rodadas com 120 testes aconteceram antes da inclusão do teste de mensagem
única de link. O workflow ainda **não rodou no GitHub**, porque o repositório
não foi publicado.

## Segurança e privacidade

- **Senhas:** PBKDF2-HMAC-SHA256 do Django (salt aleatório, 1.000.000 de
  iterações no Django 5.2) e validadores configurados.
- **Limite de login:** 5 falhas em 15 min por conta (sem diferenciar
  maiúsculas) **ou** por IP bloqueiam por 15 min, inclusive com a senha
  correta. O controle fica na tabela `portal_controlelogin` do PostgreSQL e
  vale para todos os workers e servidores que compartilham o banco; a
  atualização usa `select_for_update` para não perder contagens em falhas
  simultâneas. O IP vem de `REMOTE_ADDR`; `X-Forwarded-For` só é usado se
  `DJANGO_TRUSTED_PROXY_COUNT` for maior que 0. Limitação: um atacante com
  muitos IPs consegue bloquear uma conta de propósito (o bloqueio por conta
  facilita essa negação de serviço).
- **Sessão:** expira após 30 min sem atividade (`SESSION_COOKIE_AGE=1800` +
  `SESSION_SAVE_EVERY_REQUEST`). Logout só por POST com CSRF, apagando a sessão.
- **Cookies:** HttpOnly e SameSite=Lax; `Secure` com DEBUG=False. Em produção
  também há HSTS e redirecionamento para HTTPS. HSTS para subdomínios e
  *preload* fica desligado por padrão (`DJANGO_HSTS_INCLUDE_SUBDOMAINS` e
  `DJANGO_HSTS_PRELOAD`), pois só quem administra o domínio pode decidir isso.
- **CSP:** `script-src 'self'`, sem scripts inline. O painel aceita
  `style-src 'unsafe-inline'` por causa de estilos inline do Django Admin.
- **Conteúdo do artista:** texto simples, escapado automaticamente (sem `safe`).
  Links só `http`/`https`, sem credenciais. O servidor **nunca acessa** as URLs
  enviadas.
- **Imagens:** só JPEG, PNG e WebP, detectados pelo conteúdo; até 5 MB e
  4096 × 4096 px; arquivos truncados são recusados. As imagens são reencodadas em WebP
  (EXIF/GPS removidos), com nome aleatório, em pasta **privada** sem rota
  pública. A view `/imagens/<id>/<imagem|miniatura>/` entrega a imagem apenas de material
  aprovado ou para staff com `view_material`; nos outros casos responde 404.
- **Confirmação de envio:** o id fica só na sessão de quem enviou; a URL não
  aceita identificador.
- **Dados pessoais:** o formulário não pede CPF, endereço nem data de nascimento.
  O e-mail aparece só no painel.
- **Configuração:** com DEBUG=False, falta de `DJANGO_SECRET_KEY` ou
  `DJANGO_ALLOWED_HOSTS` impede a inicialização. As páginas 404/500 são próprias e não mostram
  rastreamentos.

## Desempenho e medição de LCP

A página inicial faz 4 consultas fixas, qualquer que seja o número de
publicações (teste `test_inicio_sem_consultas_n_mais_1`), graças ao
`select_related`, à paginação de 10 itens e ao índice `(status, -publicado_em)`.
As miniaturas WebP têm 640 × 480 e `width`/`height` declarados; só a primeira usa
`fetchpriority="high"` e as demais usam `loading="lazy"`. A matéria usa imagem de até 1600 px.
A base de 100 publicações é criada com `popular_demo --quantidade 100`.

**A meta de LCP < 3 s não foi medida.** Procedimento:

1. Use a configuração de produção (Gunicorn, DEBUG=False, estáticos pelo proxy)
   e popule 100 publicações.
2. Aqueça o servidor: carregue a página inicial 3 vezes e descarte esses resultados.
3. No Chrome DevTools → *Network*: marque **Disable cache** e crie um perfil
   personalizado com **4000 kbit/s de download, 1000 kbit/s de upload e 150 ms de
   latência**.
4. Em *Performance*, recarregue e anote o **LCP**. Repita 5 vezes, com cache
   vazio a cada vez.
5. Informe a **mediana** das 5 medições. Lighthouse CLI com
   `--throttling-method=devtools` e os mesmos parâmetros é uma alternativa.

## Produção

1. Variáveis: `DJANGO_DEBUG=False`, `DJANGO_SECRET_KEY` (secreta e longa),
   `DJANGO_ALLOWED_HOSTS=seu.dominio`,
   `DJANGO_CSRF_TRUSTED_ORIGINS=https://seu.dominio`, `POSTGRES_*`,
   `DJANGO_PRIVATE_MEDIA_ROOT=/var/lib/ruas-brasil/private_media`,
   `DJANGO_STATIC_ROOT=/var/www/ruas-brasil/static` e
   `DJANGO_TRUSTED_PROXY_COUNT=1` (atrás de um único Nginx).
2. `pip install -r requirements.txt`, `python manage.py migrate`,
   `python manage.py collectstatic --noinput` e `python manage.py check --deploy`.
3. Gunicorn (por exemplo, como serviço systemd):
   `gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 3 --timeout 30`
4. Nginx com HTTPS (certificado Let's Encrypt, por exemplo):

```nginx
server {
    listen 443 ssl http2;
    server_name seu.dominio;
    client_max_body_size 6m;                  # imagem de 5 MB + campos
    location /static/ { alias /var/www/ruas-brasil/static/; expires 7d; }
    # NÃO exponha DJANGO_PRIVATE_MEDIA_ROOT: as imagens passam pela aplicação.
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;   # sobrescreve o valor do cliente
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
server { listen 80; server_name seu.dominio; return 301 https://$host$request_uri; }
```

5. **Backups:** `pg_dump -Fc ruas_brasil > ruas-AAAAMMDD.dump` (diário, com
   rotação e cópia fora do servidor) **e** cópia da pasta de uploads privados
   (`rsync`/`tar`). Teste a restauração com `pg_restore` periodicamente. Banco e
   uploads precisam ser restaurados juntos.

**Custos e limites não medidos.** Não há preços de hospedagem aqui. Os custos
dependem de: uma VM pequena (ou PaaS) para Gunicorn e Nginx; PostgreSQL
(local ou gerenciado); disco para uploads e backups (as imagens fictícias da demo
ocupam cerca de 22 KB por material, somando imagem e miniatura; fotos reais devem
ocupar bem mais, mas esse valor não foi medido); domínio;
e certificado (gratuito com Let's Encrypt). A capacidade em requisições por
segundo não foi medida.

## Decisões, limitações e pendências

- As imagens são servidas pelo Django (`FileResponse`) para garantir a autorização.
  Em tráfego alto, troque por `X-Accel-Redirect` do Nginx, mantendo a checagem na view.
- Imagens aprovadas usam `Cache-Control: private, max-age=600`: depois de uma
  rejeição, uma cópia pode continuar no cache do navegador de quem já viu por até 10 minutos.
- A troca da imagem pelo painel não está disponível (exigiria repetir a validação). O
  caminho é pedir um novo envio.
- A busca usa `icontains`: ignora maiúsculas, mas **diferencia acentos**
  ("musica" não encontra "Música"). Sem índice textual, o que basta para centenas de registros.
- O navegador não preserva o arquivo após um erro de validação; a página pede que a imagem
  seja selecionada de novo.
- Os contadores de visualizações e cliques são agregados, sem dados pessoais, e
  não filtram robôs (são indicativos, não métricas auditáveis).
- Não há e-mail de notificação ao artista; o protocolo serve para contato manual.
- A acessibilidade foi verificada por automação (capturas em
  `docs/capturas/relatorio-capturas.json`: sem rolagem horizontal em 320 px e 640 px,
  alvos com pelo menos 44 px, foco no resumo de erros) e pelos contrastes
  calculados no CSS. **Falta testar com leitor de tela e com pessoas usuárias.**
- O LCP não foi medido; a validação com o parceiro não foi realizada.
#   r u a s - b r a s i l  
 