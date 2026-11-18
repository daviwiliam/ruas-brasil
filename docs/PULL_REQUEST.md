# MVP do Ruas Brasil: envio, curadoria e portal público

## Resumo
Primeira versão do portal editorial. O artista envia o material pelo
formulário público, o material fica **pendente**, a equipe editorial edita e
aprova ou rejeita no painel, e só o que foi aprovado aparece no portal.

## O que entra
- **RF01 – Envio** (`/enviar/`): validação por campo, resumo de erros
  acessível, protocolo não sequencial e confirmação "Aguardando avaliação"
  ligada à sessão de quem enviou.
- **RF02 – Avaliação** (`/painel/`): botões Aprovar e Rejeitar separados (POST + CSRF),
  permissão `portal.avaliar_material`, registro de avaliador e datas, e edição
  da apresentação sem publicar.
- **RF03 – Consulta**: página inicial com 10 itens por página em ordem de publicação,
  filtro por categoria e matéria completa. Pendentes e rejeitados respondem 404,
  inclusive para as imagens.
- **RF04 – Busca** por título e nome artístico, sem diferenciar maiúsculas,
  só em publicações aprovadas.
- Extras: ranking "Mais acessadas" e contadores agregados de visualizações e cliques.
- Imagens validadas pelo conteúdo, reencodadas em WebP sem metadados,
  guardadas em pasta privada e entregues por uma view com autorização.
- Segurança: limite de login por conta ou IP guardado no banco, sessão de 30 min,
  CSP sem scripts inline, configuração de produção que exige segredo e hosts.
- Comandos `carregar_categorias`, `popular_demo` (dados fictícios, sem
  usuários) e `criar_admin` (valida a senha).
- CI no GitHub Actions com PostgreSQL 17 e Python 3.12.

## Como testar
```bash
docker compose up -d
pip install -r requirements-dev.txt && cp .env.example .env
python manage.py migrate && python manage.py carregar_categorias
python manage.py criar_admin editor && python manage.py popular_demo
python manage.py runserver
coverage run manage.py test && coverage report
```

## Evidências (locais, não do GitHub)
- 121 testes passando com PostgreSQL 17 (Python 3.13.7) e cobertura de 94 %.
- As etapas do CI reproduzidas no container `python:3.12-slim` passaram
  (120 testes naquela rodada).
- Capturas reais em `docs/capturas/` (Chrome headless via Playwright).
- **Ainda não houve execução no GitHub Actions**: anexar o link da execução
  depois do primeiro push.

## Fora do escopo / pendências
Ver a seção "Decisões, limitações e pendências" do README. Destaques: LCP não
medido, busca diferencia acentos, falta teste com leitor de tela e falta validação
com o parceiro.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
