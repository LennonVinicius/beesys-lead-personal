
## Atualização de usabilidade — busca e rotas

- Resultados de cada processamento agora têm atalhos para **Todos**, **Prioritários**, **Sem site**, **Sem agenda**, **Agenda manual**, **Não visitados** e **Negócios locais**.
- O botão **Ver todos** abre todos os estabelecimentos do processamento selecionado, sem aplicar o filtro comercial padrão.
- A página **Rotas** permite escolher explicitamente qual processamento/busca será usado como fonte da rota.
- Ao selecionar um processamento, a origem é ajustada para o centro daquela busca e apenas os estabelecimentos daquela área entram na seleção.
- A rota mantém seleção manual, remoção temporária, descarte, fixação e reordenação de paradas.

# BeeSys Lead Search

Aplicação full stack de prospecção local da BeeSys, com frontend React/Vite/TypeScript e backend FastAPI/Python.

## Arquitetura

- `frontend/` — React + Vite + TypeScript + Tailwind, deploy na Vercel ou Netlify.
- `backend/` — FastAPI + Python, deploy no Render.
- Supabase — PostgreSQL + Auth.
- Geoapify/OSM/Foursquare — descoberta de estabelecimentos.
- Gemini/OpenRouter/OpenAI — enriquecimento opcional por IA.

## Funcionalidades principais

### Busca e priorização
- Escolha de cidade/endereço ou ponto diretamente no mapa.
- Raio de busca configurável.
- Geoapify, OpenStreetMap e Foursquare.
- Campanha, território e ICP configuráveis.
- Perfil de score: Auto, Agenda/Serviços, Varejo, Alimentação ou Geral.
- MRR padrão configurável.
- Grandes redes ficam fora da busca por padrão e recebem baixa aderência comercial.
- Ranking combina oportunidade digital, potencial comercial, probabilidade, aderência ao perfil BeeSys e contexto do CRM.
- Origem/confiança dos dados e sinais de presença digital.
- Busca incremental, snapshots e reanálise programável.

### Central Hoje
- Próximas ações.
- Follow-ups vencidos e do dia.
- Leads quentes parados.
- Metas atuais.
- Acesso rápido a rota, CRM e ações comerciais.

### CRM completo
- Responsável.
- Contato e telefone.
- Próxima ação.
- Notas.
- Motivo de perda.
- Não contatar.
- MRR estimado.
- Histórico de atividades.
- Ligações, WhatsApp, visitas, demos, e-mail, propostas, follow-ups e observações.
- Objeções estruturadas.
- Next Best Action.
- Aging do lead.
- Mensagem pós-visita.
- Histórico de evolução do estabelecimento.

### Modo Rua
- Ações rápidas: Visitado, Responsável não estava, Interessado, Demo, Proposta, Cliente e Sem interesse.
- Registro de objeção e observação.
- Ditado por voz no navegador quando suportado.
- Check-in/localização do usuário.
- Próximo destino e oportunidades próximas.
- Replanejamento do restante da rota.

### Planejador de rota
- Carro ou a pé.
- Tempo disponível.
- Duração média por visita.
- Número máximo de paradas.
- Estratégias: Equilibrado, Mais vendas prováveis, Mais visitas possíveis, Menor deslocamento e Manual.
- Definição de início e destino final.
- Voltar ao ponto inicial.
- Adicionar estabelecimentos manualmente.
- Remover somente da rota sem apagar do CRM.
- Descartar permanentemente com ação separada.
- Fixar paradas obrigatórias.
- Arrastar e soltar a ordem.
- Recalcular depois das alterações.
- Salvar rota do dia.
- Explicação dos estabelecimentos omitidos.
- Valor esperado aproximado de cada parada.

### Metas
- Diárias e semanais.
- Leads encontrados.
- Contatos.
- Visitas.
- Interessados.
- Demos.
- Propostas.
- Clientes.
- MRR.

### Inteligência artificial
- Gemini, OpenRouter e OpenAI.
- Modo Auto ou desativado.
- Modelos configuráveis pela interface.
- Score mínimo para usar IA.
- Limite diário de chamadas.
- Orçamento diário.
- Registro de tokens, custo estimado e erros.
- IA é complementar; regras Python continuam funcionando sem IA.

### Dashboard avançado
- Funil completo.
- Conversão por campanha.
- Conversão por fonte.
- Objeções e motivos de perda.
- Teste A/B de pitches.
- Sinais presentes nos leads que estão convertendo.
- Uso/custo de IA e provedores.
- Resultado financeiro por campanha.

### Territórios e ICP
- Territórios por cidade/bairro/coordenadas.
- Responsável por território.
- Perfis de cliente ideal configuráveis.
- Inclusões/exclusões por termos e aderência mínima.
- Foco em pequenos e médios negócios locais.

### Relatório do estabelecimento
Cada estabelecimento possui um relatório interno e pode gerar uma versão pública compartilhável.

Comparações disponíveis:
- negócios no raio;
- mesmo segmento no raio;
- cidade;
- mesmo segmento na cidade;
- bairro/área da cidade;
- mesmo segmento no bairro/área.

Métricas incluem:
- site identificado;
- site funcional;
- agendamento online;
- catálogo/serviços;
- WhatsApp;
- Instagram;
- dados estruturados;
- maturidade digital;
- prontidão para busca com IA;
- posição e percentil na amostra.

Os percentuais exibem a amostra analisada e distinguem dados conhecidos de dados que não puderam ser verificados.

Também há:
- simulador de oportunidade financeira;
- lacunas encontradas;
- recomendações comerciais;
- impressão/salvar PDF pelo navegador;
- link público com token e validade configurável;
- evolução antes/depois para clientes ou reanálises futuras.

## Alerta de competitividade na busca com IA

Quando o negócio não possui site próprio funcional/indexável ou apresenta baixa prontidão técnica, o relatório mostra um alerta vermelho de competitividade. O texto é deliberadamente conservador: não afirma que a empresa desaparecerá do Google.

O alerta explica que experiências como AI Overviews e AI Mode usam conteúdo recuperado do índice da Pesquisa e que possuir conteúdo próprio rastreável, indexável e bem estruturado aumenta o controle do negócio sobre sua presença digital. O Perfil da Empresa continua relevante para busca local.

O `AI Search Readiness Score` é um indicador interno BeeSys, não uma métrica oficial do Google.

## Segurança e operação
- Supabase Auth.
- CORS restrito ao frontend configurado e previews do projeto Vercel.
- Proteção SSRF no analisador de sites.
- Pool de conexões PostgreSQL.
- Lock de migração e schema versionado.
- RLS habilitado nas tabelas internas quando PostgreSQL/Supabase é usado.
- Auditoria de ações.
- Exportação/backup JSON.
- Health check do backend e status dos provedores.
- Fila persistente de processamento.
- Reanálise automática em pequenos lotes.

## Render — backend

Root Directory:

```text
backend/
```

Build Command:

```bash
pip install -r requirements.txt
```

Start Command:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1
```

Variáveis principais:

```text
DATABASE_URL=
SUPABASE_URL=
SUPABASE_ANON_KEY=
FRONTEND_ORIGINS=https://SEU-PROJETO.vercel.app
GEOAPIFY_API_KEY=
GEMINI_API_KEY=
OPENROUTER_API_KEY=
OPENAI_API_KEY=
FOURSQUARE_API_KEY=
ORS_API_KEY=
```

Também são aceitas:

```text
SUPABASE_PUBLISHABLE_KEY=
FRONTEND_ORIGIN_REGEX=
GEMINI_MODEL=
OPENROUTER_MODEL=
OPENAI_MODEL=
JOB_BATCH_SIZE=20
DB_POOL_MAX=5
AUTH_REQUIRED=true
```

Por padrão o backend aceita previews Vercel cujo host começa com `beesys-lead-`. Se o projeto usar outro nome, configure `FRONTEND_ORIGIN_REGEX`.

## Vercel — frontend

Root Directory:

```text
frontend/
```

Framework Preset:

```text
Vite
```

Build Command:

```bash
npm run build
```

Output Directory:

```text
dist
```

Variáveis públicas:

```text
VITE_API_URL=https://SEU-BACKEND.onrender.com
VITE_SUPABASE_URL=https://SEU-PROJETO.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
```

As três variáveis acima são públicas por design. Não envie para a Vercel `DATABASE_URL`, chaves de IA, Geoapify, Supabase Secret/Service Role ou qualquer segredo do backend.

## Migração do banco

`init_db()` aplica migrações incrementais automaticamente. A migração usa advisory lock no PostgreSQL para evitar DDL concorrente durante deploys.

Não é necessário apagar o banco Supabase existente.

## Testes realizados neste pacote

- `python -m compileall backend`.
- Importação do FastAPI e registro das rotas.
- Smoke test local de API com SQLite para dashboard, CRM, atividades, objeções, follow-ups, metas, rotas, relatórios, relatório público, territórios, ICP e exportação.
- Transpilação sintática dos arquivos TypeScript/TSX com TypeScript 5.8.3.

O build npm completo depende do download das dependências externas e deve ser confirmado pela Vercel no primeiro deploy.

## Atualização visual e operacional

Esta versão também inclui uma revisão ampla de UX sem trocar a arquitetura React/Vite + FastAPI + Supabase:

- Dashboard executivo com menos ruído, funil e desempenho da equipe por conversão.
- Central Hoje com rota, follow-ups, leads quentes, aging e projeção de metas.
- Tema claro/escuro local.
- CRM com visual em cards ou tabela, favoritos, comparação lado a lado e filtros salvos no dispositivo.
- Tags automáticas, nível de confiança dos dados e indicador de atualização.
- Mapa com clusters simples, legenda e modo de oportunidade.
- Detalhe do lead reorganizado em Visão geral, Presença digital, Comercial, Histórico e Relatório.
- Linha do tempo do CRM e barra de ações rápidas no celular.
- Score com explicação visual baseada nos motivos reais armazenados no lead.
- Modo Rua com barra inferior para ações essenciais.
- Metas com projeção de ritmo.
- Rotas com valor esperado de MRR e comparação de tempo/paradas após recalcular.
- Relatório com quartil, radar de maturidade digital, aviso de amostra pequena, branding de impressão e links públicos com validade escolhida.

Favoritos e visões salvas são armazenados localmente no navegador nesta versão; não alteram o banco e, portanto, não exigem migração.
