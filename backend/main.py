import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from auth_api import get_current_user
from db import (
    add_activity, cancel_search_job, complete_followup, create_followup, create_goal,
    create_search_job, dashboard_summary, get_business, get_search_job, goal_progress,
    init_db, list_businesses, list_search_jobs, load_activities, load_followups, load_goals,
    load_job_businesses, update_crm, update_visit,
)
from jobs import process_search_job_batch
from providers import (
    ProviderTemporaryError, geocode_geoapify, merge_provider_rows, search_foursquare,
    search_geoapify, search_osm,
)
from reporting import build_business_report
from routing import plan_timed_route

app = FastAPI(title="BeeSys Lead Search API", version="1.0.0")
_ACTIVE_JOBS=set()
_ACTIVE_LOCK=threading.Lock()
origins = [x.strip() for x in (os.getenv("FRONTEND_ORIGINS") or "http://localhost:5173").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

GEOAPIFY_KEY = os.getenv("GEOAPIFY_API_KEY") or ""
FOURSQUARE_KEY = os.getenv("FOURSQUARE_API_KEY") or ""
GEMINI_KEY = os.getenv("GEMINI_API_KEY") or ""
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY") or ""
OPENAI_KEY = os.getenv("OPENAI_API_KEY") or ""

_AI_KEYS = {"Gemini": GEMINI_KEY, "OpenRouter": OPENROUTER_KEY, "OpenAI": OPENAI_KEY}
_AI_MODELS = {
    "Gemini": os.getenv("GEMINI_MODEL", "gemini-3.7-flash"),
    "OpenRouter": os.getenv("OPENROUTER_MODEL", "openrouter/free"),
    "OpenAI": os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
}

class SearchIn(BaseModel):
    query_text: str = "Área selecionada no mapa"
    lat: float
    lon: float
    radius_m: int = Field(1000, ge=100, le=15000)
    provider: Literal["auto", "geoapify", "osm", "foursquare"] = "auto"
    max_results: int = Field(300, ge=10, le=1000)
    auto_analyze: bool = True
    ai_provider: Literal["Desativada", "Auto", "Gemini", "OpenRouter", "OpenAI"] = "Desativada"
    score_profile: str = "Auto"
    campaign_name: str = "Prospecção geral"

class CRMIn(BaseModel):
    pipeline_status: str = "NEW"
    assigned_to: str = ""
    contact_name: str = ""
    contact_phone: str = ""
    next_action_at: Optional[str] = None
    notes: str = ""
    lost_reason: str = ""
    do_not_contact: bool = False
    estimated_mrr: float = 89.90

class ActivityIn(BaseModel):
    activity_type: str
    details: str = ""
    outcome: str = ""

class GoalIn(BaseModel):
    metric: str
    target: float
    start_at: str
    end_at: str
    period: str = "DAILY"
    label: str = ""

class RouteIn(BaseModel):
    origin_lat: float
    origin_lon: float
    business_keys: list[str]
    mode: Literal["driving-car", "foot-walking"] = "driving-car"
    available_minutes: int = 240
    visit_minutes: int = 15
    max_stops: int = 12


def _user_email(user):
    return (user.get("email") or "").lower()


def _discover(payload: SearchIn):
    groups=[]
    if payload.provider in {"auto", "geoapify"} and GEOAPIFY_KEY:
        groups.append(search_geoapify(payload.lat, payload.lon, payload.radius_m, GEOAPIFY_KEY, payload.max_results))
    if payload.provider == "osm" or (payload.provider == "auto" and (not groups or len(groups[0]) < 30)):
        try:
            groups.append(search_osm(payload.lat, payload.lon, payload.radius_m, payload.max_results))
        except ProviderTemporaryError:
            if not groups:
                raise
    if payload.provider == "foursquare":
        if not FOURSQUARE_KEY:
            raise HTTPException(400, "FOURSQUARE_API_KEY não configurada")
        groups.append(search_foursquare(payload.lat, payload.lon, payload.radius_m, FOURSQUARE_KEY, max_results=payload.max_results))
    if payload.provider == "geoapify" and not GEOAPIFY_KEY:
        raise HTTPException(400, "GEOAPIFY_API_KEY não configurada")
    rows = merge_provider_rows(*groups)[:payload.max_results]
    for r in rows:
        r["campaign_name"] = payload.campaign_name
    return rows


def _drain_job(job_id: int):
    with _ACTIVE_LOCK:
        if job_id in _ACTIVE_JOBS:
            return
        _ACTIVE_JOBS.add(job_id)
    try:
        for _ in range(1000):
            job = get_search_job(job_id)
            if not job or job.get("status") in {"DONE", "FAILED", "CANCELED"}:
                return
            process_search_job_batch(
                job_id,
                batch_size=int(os.getenv("JOB_BATCH_SIZE", "20")),
                ai_keys=_AI_KEYS,
                ai_models=_AI_MODELS,
                ai_policy={"min_score": int(os.getenv("AI_MIN_SCORE", "60"))},
            )
            time.sleep(0.05)
    except Exception:
        return
    finally:
        with _ACTIVE_LOCK:
            _ACTIVE_JOBS.discard(job_id)

def _recovery_loop():
    while True:
        try:
            for job in list_search_jobs(50):
                if job.get("status") in {"RUNNING", "QUEUED"}:
                    threading.Thread(target=_drain_job,args=(int(job["id"]),),daemon=True).start()
        except Exception:
            pass
        time.sleep(8)

@app.on_event("startup")
def startup():
    init_db()
    threading.Thread(target=_recovery_loop,daemon=True).start()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/geocode")
def geocode(q: str = Query(min_length=2), user=Depends(get_current_user)):
    result = geocode_geoapify(q, GEOAPIFY_KEY)
    if not result:
        raise HTTPException(404, "Local não encontrado")
    return result

@app.post("/api/searches")
def create_search(payload: SearchIn, user=Depends(get_current_user)):
    try:
        rows = _discover(payload)
    except ProviderTemporaryError as exc:
        raise HTTPException(503, str(exc))
    center={"lat":payload.lat,"lon":payload.lon,"display_name":payload.query_text}
    config={
        "auto_analyze": payload.auto_analyze,
        "ai_provider": payload.ai_provider,
        "score_profile": payload.score_profile,
        "cache_days": 14,
        "ai_limit_per_batch": 8,
    }
    job_id=create_search_job(payload.query_text, center, payload.radius_m, payload.provider, rows, config, _user_email(user))
    threading.Thread(target=_drain_job, args=(job_id,), daemon=True).start()
    return {"job_id":job_id,"discovered":len(rows)}

@app.get("/api/searches")
def searches(limit:int=30, user=Depends(get_current_user)):
    return list_search_jobs(limit)

@app.get("/api/searches/{job_id}")
def search_detail(job_id:int, user=Depends(get_current_user)):
    job=get_search_job(job_id)
    if not job: raise HTTPException(404,"Busca não encontrada")
    job["results"]=load_job_businesses(job_id, limit=1000)
    return job

@app.post("/api/searches/{job_id}/cancel")
def search_cancel(job_id:int, user=Depends(get_current_user)):
    cancel_search_job(job_id); return {"ok":True}

@app.get("/api/leads")
def leads(limit:int=300,status:Optional[str]=None,min_score:Optional[int]=None,search:Optional[str]=None,user=Depends(get_current_user)):
    return list_businesses(limit,status,min_score,search)

@app.get("/api/leads/{business_key:path}")
def lead_detail(business_key:str, user=Depends(get_current_user)):
    lead=get_business(business_key)
    if not lead: raise HTTPException(404,"Estabelecimento não encontrado")
    lead["activities"]=load_activities(business_key,100)
    return lead

@app.patch("/api/leads/{business_key:path}")
def lead_update(business_key:str,payload:CRMIn,user=Depends(get_current_user)):
    if not get_business(business_key): raise HTTPException(404,"Estabelecimento não encontrado")
    update_crm(
        business_key, pipeline_status=payload.pipeline_status, assigned_to=payload.assigned_to,
        contact_name=payload.contact_name, contact_phone=payload.contact_phone, next_action_at=payload.next_action_at,
        notes=payload.notes, do_not_contact=payload.do_not_contact, lost_reason=payload.lost_reason,
        estimated_mrr=payload.estimated_mrr, actor_email=_user_email(user),
    )
    add_activity(business_key,"CRM_UPDATE",payload.notes,payload.pipeline_status,_user_email(user))
    return get_business(business_key)

@app.post("/api/leads/{business_key:path}/activities")
def activity(business_key:str,payload:ActivityIn,user=Depends(get_current_user)):
    add_activity(business_key,payload.activity_type,payload.details,payload.outcome,_user_email(user)); return {"ok":True}

@app.post("/api/leads/{business_key:path}/visit")
def visit(business_key:str, notes:str="", user=Depends(get_current_user)):
    update_visit(business_key,True,notes); add_activity(business_key,"VISIT",notes,"VISITED",_user_email(user)); return {"ok":True}

@app.get("/api/reports/business/{business_key:path}")
def business_report(business_key:str, job_id:int, user=Depends(get_current_user)):
    lead=get_business(business_key); job=get_search_job(job_id)
    if not lead or not job: raise HTTPException(404,"Relatório não encontrado")
    return build_business_report(lead, load_job_businesses(job_id,5000), job)

@app.get("/api/dashboard")
def dashboard(user=Depends(get_current_user)):
    return dashboard_summary()

@app.get("/api/followups")
def followups(user=Depends(get_current_user)):
    return load_followups("PENDING",1000)

@app.post("/api/followups/{followup_id}/complete")
def followup_complete(followup_id:int,user=Depends(get_current_user)):
    complete_followup(followup_id); return {"ok":True}

@app.get("/api/goals")
def goals(user=Depends(get_current_user)):
    out=[]
    for g in load_goals(True,200):
        g["progress"]=goal_progress(g["metric"],g["start_at"],g["end_at"])
        out.append(g)
    return out

@app.post("/api/goals")
def goal_create(payload:GoalIn,user=Depends(get_current_user)):
    return {"id":create_goal(payload.metric,payload.target,payload.start_at,payload.end_at,payload.period,payload.label)}

@app.post("/api/routes/plan")
def route_plan(payload:RouteIn,user=Depends(get_current_user)):
    leads=[get_business(k) for k in payload.business_keys]
    leads=[x for x in leads if x]
    return plan_timed_route((payload.origin_lat,payload.origin_lon), leads, payload.mode, None,
                            datetime.now(), payload.available_minutes,payload.visit_minutes,payload.max_stops,False)
