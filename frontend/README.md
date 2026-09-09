# BeeSys Lead Search — Full Stack

Refatoração do Lead Search com frontend separado do processamento Python.

## Stack

### Frontend
- React + Vite + TypeScript
- Tailwind CSS v4
- TanStack React Query
- React Router
- Lucide React
- React Leaflet + OpenStreetMap
- Recharts
- Supabase Auth

### Backend
- FastAPI + Python
- PostgreSQL/Supabase
- Geoapify / OpenStreetMap / Foursquare
- auditoria de site e score BeeSys
- fila persistente de análise
- Gemini / OpenRouter / OpenAI opcionais

## Estrutura

```text
frontend/   -> Vercel ou Netlify
backend/    -> Render
Supabase    -> PostgreSQL + Auth
```

O frontend não acessa o PostgreSQL. Ele autentica no Supabase e chama o FastAPI com o token do usuário. O backend valida a sessão e acessa o banco pela `DATABASE_URL`.

## Novidades desta refatoração

- Streamlit removido da interface: não há rerun completo da tela a cada clique.
- Mapa interativo para selecionar diretamente o centro da prospecção.
- Raio configurável de 250 m a 10 km na interface.
- Busca por endereço ou por clique no mapa.
- Fila de processamento continua no backend sem bloquear o navegador.
- Relatório comparativo por estabelecimento e por busca/raio.
- Comparações dinâmicas de site, agendamento, catálogo, WhatsApp, dados estruturados e maturidade digital.
- Comparação da região e do mesmo segmento estimado.
- Alerta de competitividade para negócios sem site funcional, com explicação cuidadosa sobre AI Overviews/AI Mode.
- Relatório imprimível/salvável em PDF pelo navegador.
- CRM, metas, follow-ups, processamento e modo rua preservados no frontend novo.

## 1. Backend no Render

Crie um **Web Service** apontando o **Root Directory** para:

```text
backend
```

Build:

```bash
pip install -r requirements.txt
```

Start:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1
```

Variáveis mínimas:

```text
DATABASE_URL=postgresql://...pooler.supabase.com:5432/postgres
SUPABASE_URL=https://SEU_PROJETO.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
FRONTEND_ORIGINS=https://SEU-FRONTEND.vercel.app,https://SEU-DOMINIO
GEOAPIFY_API_KEY=...
AUTH_REQUIRED=true
```

Opcionais:

```text
FOURSQUARE_API_KEY=
GEMINI_API_KEY=
OPENROUTER_API_KEY=
OPENAI_API_KEY=
GEMINI_MODEL=gemini-3.7-flash
OPENROUTER_MODEL=openrouter/free
OPENAI_MODEL=gpt-5.6-luna
JOB_BATCH_SIZE=20
AI_MIN_SCORE=60
```

A migração do banco é automática e usa advisory lock para evitar o deadlock que ocorria durante inicializações simultâneas.

## 2. Frontend na Vercel

Importe o mesmo repositório e configure **Root Directory**:

```text
frontend
```

Framework: **Vite**.

Variáveis:

```text
VITE_API_URL=https://SEU-BACKEND.onrender.com
VITE_SUPABASE_URL=https://SEU_PROJETO.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
```

O arquivo `vercel.json` já contém o rewrite necessário para React Router.

## 3. Frontend no Netlify

Base directory:

```text
frontend
```

Build command:

```bash
npm run build
```

Publish directory:

```text
dist
```

Configure as mesmas três variáveis `VITE_*`. O `netlify.toml` já possui fallback de SPA.

## 4. Supabase Auth

No Supabase:

```text
Authentication -> Users -> Add user
```

Crie os usuários da equipe. O frontend usa login por e-mail/senha do Supabase.

## Relatórios comparativos

Todo relatório é calculado a partir dos estabelecimentos efetivamente encontrados e analisados naquela busca. Exemplo:

- percentual da base com site identificado;
- percentual com site funcional;
- percentual com agendamento online;
- percentual com catálogo/serviços online;
- percentual com WhatsApp identificado;
- percentual com dados estruturados;
- maturidade digital média;
- prontidão média para busca com IA;
- posição do lead dentro da amostra;
- comparação com negócios do mesmo segmento estimado.

A interface sempre informa que a base é uma **amostra encontrada pelas fontes configuradas**, e não um censo oficial do bairro.

## Busca com IA do Google

O alerta vermelho não afirma que um negócio sem site desaparecerá do Google. O texto segue a orientação oficial do Google: para uma página aparecer como link de suporte em AI Overviews ou AI Mode, ela precisa estar indexada e elegível para aparecer na Pesquisa. Um Perfil da Empresa continua relevante, mas um site próprio oferece ao negócio uma superfície própria, indexável e controlável para conteúdo, serviços e informações.

Referências usadas no texto do relatório:
- https://developers.google.com/search/docs/appearance/ai-features?hl=pt-BR
- https://developers.google.com/search/docs/fundamentals/ai-optimization-guide

## Desenvolvimento local

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload
```

Frontend:

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Frontend: `http://localhost:5173`
Backend: `http://localhost:8000`
