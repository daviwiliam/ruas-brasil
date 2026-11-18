# Checklist de autorrevisão

Marcado apenas o que foi verificado no código e nos testes desta entrega.

## Fluxo
- [x] Envio válido cria material `pendente` (`test_envio_valido_cria_material_pendente_e_redireciona`)
- [x] Editar no painel não publica (`test_editar_apresentacao_nao_aprova`)
- [x] Aprovar e rejeitar só via POST, com CSRF e permissão (`PainelAvaliacaoTests`)
- [x] O serviço também checa a permissão (`test_sem_permissao_o_servico_recusa`)
- [x] Pendente e rejeitado dão 404 na matéria, na imagem, na miniatura, na busca e na listagem
- [x] A confirmação não aceita id na URL e não aparece para outra sessão

## Dados e integridade
- [x] CheckConstraints de status e datas testadas no PostgreSQL (`RestricoesDeEstadoTests`)
- [x] `PROTECT` em artista, categoria e avaliador
- [x] Migração versionada e `makemigrations --check` limpo

## Segurança
- [x] PBKDF2-SHA256 e validadores de senha; `criar_admin` chama `validate_password`
- [x] Limite de login por conta e IP, com expiração (testes com `mock` do relógio)
- [x] `X-Forwarded-For` ignorado sem proxy confiável
- [x] Logout por POST e sessão removida do banco
- [x] Escape de HTML no título, no nome, na descrição, no alt e na busca
- [x] Links só http/https; o servidor não acessa as URLs enviadas
- [x] Imagens falsas, GIF/BMP/TIFF, mais de 5 MB, mais de 4096 px e truncadas recusadas; EXIF removido
- [x] `.env`, uploads, banco local e cobertura no `.gitignore`
- [x] `check --deploy` sem avisos (2 silenciados com justificativa: HSTS de subdomínios e preload)

## Acessibilidade (verificação automatizada; falta teste humano)
- [x] Link "Pular para o conteúdo" é o primeiro foco
- [x] Rótulos persistentes, `aria-describedby`, `aria-invalid` e resumo de erros focado
- [x] Status com texto e símbolo (◷ ✓ ✕)
- [x] Sem rolagem horizontal em 320 px e 640 px; alvos de pelo menos 44 px nas páginas verificadas
- [ ] Teste com leitor de tela (NVDA, VoiceOver)
- [ ] Teste com pessoas usuárias e com o parceiro

## Desempenho
- [x] Número de consultas constante na página inicial (`assertNumQueries(4)`)
- [ ] LCP medido conforme o procedimento do README

## CI
- [x] Workflow escrito e reproduzido localmente em Python 3.12
- [ ] Execução verde no GitHub Actions (depende de publicar o repositório)
