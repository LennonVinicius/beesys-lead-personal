# Checklist de deploy

## Backend — Render

- Root Directory: `backend/`
- Build: `pip install -r requirements.txt`
- Start: `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1`
- Configurar `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY` e `FRONTEND_ORIGINS`.
- Adicionar `GEOAPIFY_API_KEY` para busca principal.
- Adicionar chaves de IA apenas se quiser usar IA.
- Abrir `/health` depois do deploy e confirmar `status: ok`.

## Frontend — Vercel

- Root Directory: `frontend/`
- Framework: Vite
- Build: `npm run build`
- Output: `dist`
- Configurar `VITE_API_URL`, `VITE_SUPABASE_URL` e `VITE_SUPABASE_PUBLISHABLE_KEY` como Config.
- Fazer novo deploy depois de alterar variáveis Vite.

## Supabase

- Criar usuário em Authentication > Users.
- Usar Session Pooler no `DATABASE_URL` do Render quando necessário.
- Não colocar Secret/Service Role no frontend.

## Depois do primeiro deploy

1. Fazer login.
2. Abrir Dashboard.
3. Testar geocoding em Buscar Leads.
4. Criar uma busca pequena de 500 m.
5. Abrir um lead.
6. Registrar uma atividade e um follow-up.
7. Gerar relatório comparativo.
8. Criar link público do relatório.
9. Montar uma rota e remover uma parada.
10. Conferir tabelas no Supabase.
