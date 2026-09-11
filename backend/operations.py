import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from db import (
    _conn, _execute, _decode_business, get_business, list_businesses, load_followups,
    load_goals, goal_progress, load_business_snapshots, get_search_job,
    latest_search_job_for_business, load_job_businesses, list_businesses_by_city,
    list_businesses_by_district, add_activity, update_crm, create_followup,
)
from reporting import build_business_report


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def audit(actor_email: str, action: str, entity_type: str, entity_id: str | None = None, details: Any = None):
    with _conn() as conn:
        _execute(
            conn,
            "INSERT INTO audit_logs(actor_email,action,entity_type,entity_id,details_json,created_at) VALUES(?,?,?,?,?,?)",
            (actor_email or None, action, entity_type, entity_id, json.dumps(details or {}, ensure_ascii=False), _now()),
        )
        conn.commit()


def list_audit_logs(limit: int = 300):
    with _conn() as conn:
        rows = _execute(conn, "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?", (int(limit),)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["details"] = json.loads(d.pop("details_json") or "{}")
        except Exception:
            d["details"] = {}
        out.append(d)
    return out


def field_evidence(lead: dict) -> list[dict]:
    provider = lead.get("provider") or "Fonte externa"
    confidence = int(lead.get("data_confidence") or 55)
    items = []
    def add(field, label, value, source, conf, status="known"):
        items.append({"field": field, "label": label, "value": value, "source": source, "confidence": int(conf), "status": status})
    add("name", "Nome", lead.get("name"), provider, max(confidence, 70))
    add("address", "Endereço", lead.get("address"), provider, confidence, "known" if lead.get("address") else "unknown")
    add("phone", "Telefone", lead.get("phone") or lead.get("contact_phone"), provider, confidence, "known" if (lead.get("phone") or lead.get("contact_phone")) else "unknown")
    add("website", "Site", lead.get("website"), provider, confidence, "known" if lead.get("website") else "not_found")
    if lead.get("website"):
        add("site_functional", "Site funcional", lead.get("site_functional"), "Auditoria BeeSys", 92 if lead.get("site_functional") is not None else 50, "known" if lead.get("site_functional") is not None else "unknown")
        add("booking", "Agendamento online", lead.get("has_booking"), "Auditoria BeeSys", 88, "known")
        add("catalog", "Catálogo/serviços", lead.get("has_catalog"), "Auditoria BeeSys", 82, "known")
        add("structured", "Dados estruturados", lead.get("has_structured_data"), "Auditoria BeeSys", 90, "known")
    if lead.get("decision_maker_name"):
        add("decision_maker", "Possível decisor", lead.get("decision_maker_name"), "Site/IA", int(lead.get("decision_maker_confidence") or 55), "inferred")
    return items


def lead_pains(lead: dict) -> list[dict]:
    pains = []
    def p(code, label, severity, evidence): pains.append({"code": code, "label": label, "severity": severity, "evidence": evidence})
    if not lead.get("website"):
        p("NO_WEBSITE", "Sem site próprio", "high", "Nenhum site próprio foi identificado nas fontes consultadas.")
    elif lead.get("site_functional") is False:
        p("SITE_PROBLEM", "Site com problema", "high", "O site foi identificado, mas não respondeu como página funcional na auditoria.")
    if lead.get("manual_booking_detected"):
        p("MANUAL_BOOKING", "Agendamento manual", "high", lead.get("manual_booking_evidence") or "Há sinais de agendamento por WhatsApp, direct ou telefone.")
    elif not lead.get("has_booking"):
        p("NO_BOOKING", "Sem agenda online", "medium", "Não foi identificado fluxo de agendamento online.")
    if not lead.get("has_catalog"):
        p("NO_CATALOG", "Sem catálogo/serviços online", "medium", "Não foi identificado catálogo, menu ou página clara de serviços.")
    if lead.get("website") and not lead.get("has_structured_data"):
        p("NO_STRUCTURED_DATA", "Sem dados estruturados identificados", "low", "A auditoria não identificou marcação estruturada no site.")
    if lead.get("competitor_detected"):
        p("COMPETITOR", f"Usa {lead.get('competitor_name') or 'outro sistema'}", "info", "O negócio já entende o valor de software; a abordagem deve focar diferenciais e dores do sistema atual.")
    return pains


def next_best_action(lead: dict) -> dict:
    if lead.get("do_not_contact") or lead.get("pipeline_status") == "DO_NOT_CONTACT":
        return {"action": "NONE", "label": "Não contatar", "reason": "Lead marcado para não receber novas abordagens.", "priority": 0}
    status = lead.get("pipeline_status") or "NEW"
    next_at = lead.get("next_action_at")
    if status == "CLIENT":
        return {"action": "ONBOARD", "label": "Acompanhar cliente", "reason": "Lead convertido. Priorize onboarding e sucesso inicial.", "priority": 30}
    if status == "PROPOSAL":
        return {"action": "FOLLOW_UP", "label": "Retomar proposta", "reason": "Há proposta em aberto; reduzir o tempo até a resposta.", "priority": 96, "due_at": next_at}
    if status == "DEMO":
        return {"action": "FOLLOW_UP", "label": "Follow-up da demonstração", "reason": "Reforce a dor discutida e avance para proposta.", "priority": 92, "due_at": next_at}
    if status == "INTERESTED":
        return {"action": "DEMO", "label": "Agendar demonstração", "reason": "O lead demonstrou interesse; o melhor próximo passo é uma demo objetiva.", "priority": 90, "due_at": next_at}
    if status == "VISITED":
        return {"action": "FOLLOW_UP", "label": "Definir próximo passo", "reason": "Já houve visita; evite o lead esfriar sem uma ação marcada.", "priority": 82, "due_at": next_at}
    if status == "LOST":
        return {"action": "REVIEW_LATER", "label": "Reavaliar futuramente", "reason": lead.get("lost_reason") or "Oportunidade encerrada; reavaliar somente se o contexto mudar.", "priority": 15}
    if int(lead.get("visit_priority_score") or 0) >= 75:
        return {"action": "VISIT", "label": "Visitar", "reason": "Alta prioridade comercial e boa aderência ao perfil BeeSys.", "priority": int(lead.get("visit_priority_score") or 75)}
    if lead.get("phone") or lead.get("has_whatsapp"):
        return {"action": "CONTACT", "label": "Fazer primeiro contato", "reason": "Existe canal de contato; valide o decisor e a principal dor antes da visita.", "priority": int(lead.get("visit_priority_score") or 55)}
    return {"action": "RESEARCH", "label": "Completar informações", "reason": "Faltam dados de contato ou sinais suficientes para priorizar uma visita.", "priority": 40}


def enrich_lead(lead: dict) -> dict:
    if not lead:
        return lead
    lead = dict(lead)
    lead["pains"] = lead_pains(lead)
    lead["next_best_action"] = next_best_action(lead)
    lead["field_evidence"] = field_evidence(lead)
    last = lead.get("last_contact_at") or lead.get("first_seen_at")
    aging = None
    if last:
        try:
            dt = datetime.fromisoformat(last)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            aging = max(0, (datetime.now(timezone.utc) - dt).days)
        except Exception:
            pass
    lead["aging_days"] = aging
    if aging is None:
        lead["aging_label"] = "Sem histórico"
    elif aging >= 60:
        lead["aging_label"] = "Muito parado"
    elif aging >= 30:
        lead["aging_label"] = "Precisa de ação"
    elif aging >= 14:
        lead["aging_label"] = "Esfriando"
    else:
        lead["aging_label"] = "Atual"
    # reputação simples, sem inventar leitura de reviews que não temos.
    rating, reviews = lead.get("rating"), int(lead.get("reviews") or 0)
    if rating is not None:
        lead["reputation_insight"] = f"Nota {float(rating):.1f} com {reviews} avaliações registradas na fonte disponível."
    else:
        lead["reputation_insight"] = "A fonte atual não forneceu nota/reviews suficientes para analisar reputação."
    return lead


def today_workspace(actor_email: str = "") -> dict:
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    followups = load_followups("PENDING", 1000)
    due = [f for f in followups if str(f.get("due_at") or "")[:10] <= today]
    leads = list_businesses(2000)
    actions = []
    for l in leads:
        if actor_email and l.get("assigned_to") and l.get("assigned_to").lower() != actor_email.lower():
            continue
        a = next_best_action(l)
        if a["action"] != "NONE":
            actions.append({"lead": enrich_lead(l), "action": a})
    actions.sort(key=lambda x: (x["action"].get("priority") or 0), reverse=True)
    goals = []
    for g in load_goals(True, 100):
        if str(g.get("start_at") or "")[:10] <= today <= str(g.get("end_at") or "")[:10]:
            g = dict(g)
            g["progress"] = goal_progress(g["metric"], g["start_at"], g["end_at"])
            goals.append(g)
    with _conn() as conn:
        routes = _execute(conn, "SELECT * FROM routes WHERE route_date=? AND status NOT IN ('CANCELED') ORDER BY created_at DESC", (today,)).fetchall()
    return {"date": today, "due_followups": due[:30], "next_actions": actions[:40], "goals": goals, "routes": [dict(r) for r in routes]}


def create_public_report(business_key: str, job_id: int | None, actor_email: str, expires_days: int = 30):
    token = secrets.token_urlsafe(24)
    created = _now()
    expires = (datetime.now(timezone.utc) + timedelta(days=max(1, min(365, expires_days)))).isoformat()
    with _conn() as conn:
        _execute(conn, "INSERT INTO public_reports(token,business_key,job_id,active,created_by,created_at,expires_at) VALUES(?,?,?,?,?,?,?)",
                 (token, business_key, job_id, 1, actor_email or None, created, expires))
        conn.commit()
    audit(actor_email, "CREATE_PUBLIC_REPORT", "business", business_key, {"token": token, "job_id": job_id, "expires_at": expires})
    return {"token": token, "expires_at": expires}


def get_public_report(token: str):
    with _conn() as conn:
        row = _execute(conn, "SELECT * FROM public_reports WHERE token=? AND active=1", (token,)).fetchone()
    if not row:
        return None
    row = dict(row)
    if row.get("expires_at"):
        try:
            if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
                return None
        except Exception:
            pass
    lead = get_business(row["business_key"])
    if not lead:
        return None
    job = get_search_job(row.get("job_id")) if row.get("job_id") else latest_search_job_for_business(row["business_key"])
    cfg = (job or {}).get("config") or {}
    city = lead.get("city_name") or cfg.get("city_name")
    district = lead.get("district_name") or cfg.get("district_name")
    peers = load_job_businesses(job["id"], 5000) if job else list_businesses_by_city(city, 5000)
    if not peers:
        peers = [lead]
    report = build_business_report(
        enrich_lead(lead), peers, job,
        city_peers=list_businesses_by_city(city, 5000),
        district_peers=list_businesses_by_district(city, district, 5000),
    )
    report["public"] = {"token": token, "expires_at": row.get("expires_at")}
    report["evolution"] = business_evolution(row["business_key"])
    report["solution_map"]={
        "NO_WEBSITE":"Página própria BeeSys com conteúdo rastreável e marca do negócio",
        "SITE_PROBLEM":"Reestruturação da presença própria e página funcional",
        "MANUAL_BOOKING":"Agenda BeeSys para disponibilidade, confirmações e menos troca manual de mensagens",
        "NO_BOOKING":"Agendamento online BeeSys integrado ao fluxo do estabelecimento",
        "NO_CATALOG":"Catálogo/serviços BeeSys para apresentar oferta antes do contato",
        "NO_STRUCTURED_DATA":"Melhoria de estrutura e dados do negócio na presença própria",
        "COMPETITOR":"Comparação orientada a dores reais, sem migração forçada",
    }
    return report


def build_post_visit_message(lead: dict, notes: str = "") -> str:
    name = lead.get("contact_name") or ""
    greeting = f"Olá, {name}!" if name else "Olá!"
    pain = (lead_pains(lead) or [{}])[0].get("label")
    if lead.get("pipeline_status") == "PROPOSAL":
        body = "Passando para saber se conseguiu analisar a proposta da BeeSys e se ficou alguma dúvida."
    elif lead.get("pipeline_status") in {"INTERESTED", "DEMO"}:
        body = "Como conversamos, posso te mostrar de forma rápida como a BeeSys organiza agenda, atendimento e presença digital no dia a dia."
    else:
        body = "Obrigado pelo tempo na nossa conversa. Separei os pontos que identificamos para facilitar o próximo contato."
    if pain:
        body += f" Um dos pontos que vimos foi: {pain.lower()}."
    if notes:
        body += f" {notes.strip()}"
    return f"{greeting} Aqui é da BeeSys. {body} Se fizer sentido, combinamos o melhor horário para continuar."


def business_evolution(business_key: str) -> dict:
    lead = enrich_lead(get_business(business_key) or {})
    snaps = load_business_snapshots(business_key, 100)
    decoded = []
    for s in snaps:
        d = dict(s)
        try: d["snapshot"] = json.loads(d.get("snapshot_json") or "{}")
        except Exception: d["snapshot"] = {}
        decoded.append(d)
    baseline = decoded[-1]["snapshot"] if decoded else None
    current = {k: lead.get(k) for k in ["website","site_functional","has_booking","has_catalog","has_whatsapp","digital_maturity_score","ai_search_readiness_score","pipeline_status"]}
    changes = []
    if baseline:
        for k,v in current.items():
            if baseline.get(k) != v:
                changes.append({"field": k, "before": baseline.get(k), "after": v})
    return {"lead": lead, "baseline": baseline, "current": current, "changes": changes, "snapshots": decoded[:20]}


def schedule_reanalysis(business_key: str, days: int = 30):
    due = (datetime.now(timezone.utc) + timedelta(days=max(1, min(365, days)))).isoformat()
    with _conn() as conn:
        _execute(conn, "UPDATE businesses SET next_reanalysis_at=? WHERE business_key=?", (due, business_key))
        conn.commit()
    return due


def due_reanalysis(limit: int = 20):
    now = _now()
    with _conn() as conn:
        rows = _execute(conn, "SELECT * FROM businesses WHERE next_reanalysis_at IS NOT NULL AND next_reanalysis_at<=? AND COALESCE(website,'')<>'' ORDER BY next_reanalysis_at LIMIT ?", (now, int(limit))).fetchall()
    return [_decode_business(r) for r in rows]


def mark_reanalyzed(business_key: str, next_days: int = 60):
    now = _now(); nxt=(datetime.now(timezone.utc)+timedelta(days=next_days)).isoformat()
    with _conn() as conn:
        _execute(conn, "UPDATE businesses SET last_reanalysis_at=?,next_reanalysis_at=? WHERE business_key=?", (now,nxt,business_key))
        conn.commit()


def create_route_record(payload: dict, plan: dict, actor_email: str) -> dict:
    now = _now(); route_date = payload.get("route_date") or datetime.now(timezone.utc).date().isoformat()
    geometry = plan.get("geometry")
    summary = {k: plan.get(k) for k in ["used_minutes","matrix_engine","distance_m","duration_s"]}
    with _conn() as conn:
        if hasattr(conn, 'execute') and 'psycopg' in conn.__class__.__module__:
            row = _execute(conn, """INSERT INTO routes(name,route_date,status,owner_email,campaign_name,strategy,mode,origin_lat,origin_lon,origin_label,end_lat,end_lon,end_label,available_minutes,visit_minutes,max_stops,geometry_json,summary_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id""",
                           (payload.get("name") or f"Rota {route_date}",route_date,"PLANNED",actor_email or None,payload.get("campaign_name"),payload.get("strategy") or "balanced",payload.get("mode") or "driving-car",payload["origin_lat"],payload["origin_lon"],payload.get("origin_label"),payload.get("end_lat"),payload.get("end_lon"),payload.get("end_label"),payload.get("available_minutes",240),payload.get("visit_minutes",15),payload.get("max_stops",12),json.dumps(geometry,ensure_ascii=False),json.dumps(summary,ensure_ascii=False),now,now)).fetchone()
            route_id = row["id"]
        else:
            cur = _execute(conn, """INSERT INTO routes(name,route_date,status,owner_email,campaign_name,strategy,mode,origin_lat,origin_lon,origin_label,end_lat,end_lon,end_label,available_minutes,visit_minutes,max_stops,geometry_json,summary_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                           (payload.get("name") or f"Rota {route_date}",route_date,"PLANNED",actor_email or None,payload.get("campaign_name"),payload.get("strategy") or "balanced",payload.get("mode") or "driving-car",payload["origin_lat"],payload["origin_lon"],payload.get("origin_label"),payload.get("end_lat"),payload.get("end_lon"),payload.get("end_label"),payload.get("available_minutes",240),payload.get("visit_minutes",15),payload.get("max_stops",12),json.dumps(geometry,ensure_ascii=False),json.dumps(summary,ensure_ascii=False),now,now))
            route_id = cur.lastrowid
        fixed=set(payload.get("fixed_business_keys") or [])
        for i, stop in enumerate(plan.get("schedule") or []):
            _execute(conn, "INSERT INTO route_stops(route_id,business_key,position,status,fixed,notes,travel_minutes,arrival_at,departure_at,expected_mrr_value,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                     (route_id,stop["business_key"],i+1,"SELECTED",1 if stop["business_key"] in fixed else 0,"",stop.get("travel_minutes"),str(stop.get("arrival") or ""),str(stop.get("departure") or ""),stop.get("expected_mrr_value"),now,now))
        conn.commit()
    audit(actor_email,"CREATE_ROUTE","route",str(route_id),{"stops":len(plan.get("schedule") or [])})
    return get_route(route_id)


def get_route(route_id: int) -> dict | None:
    with _conn() as conn:
        route = _execute(conn,"SELECT * FROM routes WHERE id=?",(route_id,)).fetchone()
        if not route: return None
        stops = _execute(conn,"""SELECT s.*,b.name,b.address,b.lat,b.lon,b.visit_priority_score,b.pipeline_status,b.why_approach,b.estimated_mrr,b.conversion_probability,b.open_now,b.notes AS lead_notes,b.assigned_to,b.campaign_name
          FROM route_stops s JOIN businesses b ON b.business_key=s.business_key WHERE s.route_id=? ORDER BY s.position""",(route_id,)).fetchall()
    out=dict(route)
    for k in ("geometry_json","summary_json"):
        try: out[k[:-5]]=json.loads(out.get(k) or "null")
        except Exception: out[k[:-5]]=None
    out["stops"]=[dict(s) for s in stops]
    return out


def list_routes(limit: int = 100):
    with _conn() as conn:
        rows=_execute(conn,"SELECT * FROM routes ORDER BY route_date DESC,created_at DESC LIMIT ?",(int(limit),)).fetchall()
    return [dict(r) for r in rows]


def update_route_stops(route_id: int, stops: list[dict], actor_email: str = ""):
    now=_now()
    with _conn() as conn:
        existing={r["business_key"]:dict(r) for r in _execute(conn,"SELECT * FROM route_stops WHERE route_id=?",(route_id,)).fetchall()}
        keep=set()
        for i,st in enumerate(stops):
            key=st["business_key"];keep.add(key)
            if key in existing:
                _execute(conn,"UPDATE route_stops SET position=?,status=?,fixed=?,removal_reason=?,notes=?,updated_at=? WHERE route_id=? AND business_key=?",
                         (i+1,st.get("status","SELECTED"),1 if st.get("fixed") else 0,st.get("removal_reason"),st.get("notes") or "",now,route_id,key))
            else:
                _execute(conn,"INSERT INTO route_stops(route_id,business_key,position,status,fixed,removal_reason,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                         (route_id,key,i+1,st.get("status","SELECTED"),1 if st.get("fixed") else 0,st.get("removal_reason"),st.get("notes") or "",now,now))
        for key in existing:
            if key not in keep:
                _execute(conn,"UPDATE route_stops SET status='REMOVED',removal_reason=COALESCE(removal_reason,'Removido desta rota'),updated_at=? WHERE route_id=? AND business_key=?",(now,route_id,key))
        _execute(conn,"UPDATE routes SET updated_at=? WHERE id=?",(now,route_id));conn.commit()
    audit(actor_email,"UPDATE_ROUTE","route",str(route_id),{"stops":len(stops)})
    return get_route(route_id)


def update_route_stop_status(route_id: int, business_key: str, status: str, reason: str = "", actor_email: str = ""):
    with _conn() as conn:
        _execute(conn,"UPDATE route_stops SET status=?,removal_reason=?,updated_at=? WHERE route_id=? AND business_key=?",(status,reason or None,_now(),route_id,business_key));conn.commit()
    audit(actor_email,"ROUTE_STOP_STATUS","route",str(route_id),{"business_key":business_key,"status":status,"reason":reason})
    return get_route(route_id)


def create_territory(data: dict, actor_email: str):
    now=_now()
    with _conn() as conn:
        if 'psycopg' in conn.__class__.__module__:
            row=_execute(conn,"""INSERT INTO territories(name,city_name,district_name,assigned_to,center_lat,center_lon,radius_m,polygon_json,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?) RETURNING id""",
                         (data.get("name"),data.get("city_name"),data.get("district_name"),data.get("assigned_to"),data.get("center_lat"),data.get("center_lon"),data.get("radius_m"),json.dumps(data.get("polygon"),ensure_ascii=False) if data.get("polygon") else None,1,now,now)).fetchone();tid=row['id']
        else:
            cur=_execute(conn,"""INSERT INTO territories(name,city_name,district_name,assigned_to,center_lat,center_lon,radius_m,polygon_json,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                         (data.get("name"),data.get("city_name"),data.get("district_name"),data.get("assigned_to"),data.get("center_lat"),data.get("center_lon"),data.get("radius_m"),json.dumps(data.get("polygon"),ensure_ascii=False) if data.get("polygon") else None,1,now,now));tid=cur.lastrowid
        conn.commit()
    audit(actor_email,"CREATE_TERRITORY","territory",str(tid),data)
    return tid


def list_territories(active_only: bool = True):
    with _conn() as conn:
        rows=_execute(conn,"SELECT * FROM territories"+(" WHERE active=1" if active_only else "")+" ORDER BY name").fetchall()
    out=[]
    for r in rows:
        d=dict(r)
        try:d['polygon']=json.loads(d.get('polygon_json') or 'null')
        except Exception:d['polygon']=None
        out.append(d)
    return out


def upsert_icp(data: dict, actor_email: str):
    name=(data.get('name') or '').strip()
    if not name: raise ValueError('Nome do ICP é obrigatório')
    now=_now(); cfg=json.dumps(data.get('config') or {},ensure_ascii=False)
    with _conn() as conn:
        _execute(conn,"""INSERT INTO icp_profiles(name,config_json,active,created_at,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET config_json=excluded.config_json,active=1,updated_at=excluded.updated_at""",(name,cfg,1,now,now));conn.commit()
    audit(actor_email,"UPSERT_ICP","icp",name,data.get('config') or {})
    return name


def list_icps():
    with _conn() as conn:
        rows=_execute(conn,"SELECT * FROM icp_profiles WHERE active=1 ORDER BY name").fetchall()
    out=[]
    for r in rows:
        d=dict(r)
        try:d['config']=json.loads(d.get('config_json') or '{}')
        except Exception:d['config']={}
        out.append(d)
    return out


def record_provider_usage(provider: str, operation: str, units: float = 1, result_count: int = 0, details: dict | None = None):
    try:
        with _conn() as conn:
            _execute(conn, "INSERT INTO provider_usage(provider,operation,units,result_count,details_json,created_at) VALUES(?,?,?,?,?,?)",
                     (provider, operation, float(units), int(result_count), json.dumps(details or {}, ensure_ascii=False), _now()))
            conn.commit()
    except Exception:
        # Observabilidade nunca deve interromper a busca principal.
        return


def provider_usage_summary(days: int = 30):
    cutoff=(datetime.now(timezone.utc)-timedelta(days=max(1,int(days)))).isoformat()
    with _conn() as conn:
        rows=_execute(conn, """SELECT provider,operation,COUNT(*) calls,COALESCE(SUM(units),0) units,COALESCE(SUM(result_count),0) results
          FROM provider_usage WHERE created_at>=? GROUP BY provider,operation ORDER BY calls DESC""", (cutoff,)).fetchall()
    return [dict(r) for r in rows]


def export_full() -> dict:
    tables=['businesses','activities','objections','followups','goals','search_jobs','search_job_items','ai_usage','business_snapshots','routes','route_stops','territories','icp_profiles','audit_logs','provider_usage']
    out={"exported_at":_now(),"version":1,"tables":{}}
    with _conn() as conn:
        for t in tables:
            try: rows=_execute(conn,f'SELECT * FROM {t}').fetchall();out['tables'][t]=[dict(r) for r in rows]
            except Exception: out['tables'][t]=[]
    return out


def campaign_financials():
    with _conn() as conn:
        rows=_execute(conn,"""SELECT COALESCE(campaign_name,'Sem campanha') name,COUNT(*) leads,
          SUM(CASE WHEN pipeline_status='VISITED' OR visited=1 THEN 1 ELSE 0 END) visits,
          SUM(CASE WHEN pipeline_status IN ('INTERESTED','DEMO','PROPOSAL','CLIENT') THEN 1 ELSE 0 END) positives,
          SUM(CASE WHEN pipeline_status='CLIENT' THEN 1 ELSE 0 END) clients,
          COALESCE(SUM(CASE WHEN pipeline_status='CLIENT' THEN estimated_mrr ELSE 0 END),0) mrr
          FROM businesses GROUP BY COALESCE(campaign_name,'Sem campanha') ORDER BY clients DESC,leads DESC""").fetchall()
    return [dict(r) for r in rows]
