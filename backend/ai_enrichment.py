import json
import os
import re
from typing import Dict

import requests

from db import ai_usage_today, record_ai_usage

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

DEFAULT_MODELS = {
    "OpenAI": "gpt-5.6-luna",
    "Gemini": "gemini-3.7-flash",
    "OpenRouter": "openrouter/free",
}


def _extract_json(text):
    text = (text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return None
    return None


def _facts(row):
    return {
        "name": row.get("name"), "category": row.get("category"), "rating": row.get("rating"),
        "reviews": row.get("reviews"), "website": row.get("website"), "site_functional": row.get("site_functional"),
        "site_quality_score": row.get("site_quality_score"), "site_mobile": row.get("site_mobile"),
        "site_https": row.get("site_https"), "has_booking": row.get("has_booking"),
        "booking_provider": row.get("booking_provider"), "manual_booking_detected": row.get("manual_booking_detected"),
        "manual_booking_channel": row.get("manual_booking_channel"), "manual_booking_evidence": row.get("manual_booking_evidence"),
        "has_catalog": row.get("has_catalog"), "has_whatsapp": row.get("has_whatsapp"),
        "has_instagram": row.get("has_instagram"), "has_facebook": row.get("has_facebook"),
        "competitor_detected": row.get("competitor_detected"), "competitor_name": row.get("competitor_name"),
        "tech_stack": row.get("tech_stack"), "site_title": row.get("site_title"),
        "site_description": row.get("site_description"), "emails_found": row.get("emails_found"),
        "decision_maker_candidates": row.get("decision_maker_candidates"),
        "opportunity_score": row.get("opportunity_score") or row.get("score"),
        "commercial_potential_score": row.get("commercial_potential_score"), "pipeline_status": row.get("pipeline_status"),
        "visit_notes": row.get("notes"), "estimated_mrr": row.get("estimated_mrr"),
        "data_confidence": row.get("data_confidence"),
    }


def _prompt(row):
    return f"""
Você é um analista de prospecção B2B da BeeSys. Avalie APENAS os fatos fornecidos e nunca invente nomes, números, cargo, proprietário ou serviço.
A BeeSys oferece software de gestão, agendamento e presença digital para pequenos negócios.

FATOS DO LEAD:
{json.dumps(_facts(row), ensure_ascii=False)}

Retorne SOMENTE JSON válido com estas chaves:
- ai_summary: resumo factual em até 2 frases.
- why_approach: por que vale ou não vale abordar, em até 2 frases.
- sales_pitch: fala presencial curta, específica e não agressiva.
- priority_adjustment: inteiro entre -10 e 10; use 0 quando não houver justificativa.
- decision_maker: objeto com name, role e confidence (0-100). Se não houver evidência, name e role devem ser null e confidence 0.
- likely_objection: possível objeção baseada SOMENTE nos fatos; null se não houver base.
- warnings: lista curta com limitações dos dados.
Não transforme inferência em fato. Se a informação não existe, use null.
""".strip()


def _normalize_result(parsed):
    if not isinstance(parsed, dict):
        return {}
    try:
        parsed["priority_adjustment"] = max(-10, min(10, int(parsed.get("priority_adjustment") or 0)))
    except Exception:
        parsed["priority_adjustment"] = 0
    dm = parsed.get("decision_maker")
    if not isinstance(dm, dict):
        dm = {"name": None, "role": None, "confidence": 0}
    try:
        dm["confidence"] = max(0, min(100, int(dm.get("confidence") or 0)))
    except Exception:
        dm["confidence"] = 0
    parsed["decision_maker"] = dm
    if not isinstance(parsed.get("warnings"), list):
        parsed["warnings"] = []
    return parsed


def _pricing_cost(provider, model, input_tokens, output_tokens):
    """Preços são configuráveis para não embutir valores que mudam com o tempo.
    AI_PRICING_JSON usa USD por 1M tokens:
    {"OpenAI":{"modelo":{"input":0.0,"output":0.0}}}
    """
    try:
        pricing = json.loads(os.getenv("AI_PRICING_JSON") or "{}")
        item = ((pricing.get(provider) or {}).get(model) or {})
        return (float(input_tokens or 0) * float(item.get("input") or 0) +
                float(output_tokens or 0) * float(item.get("output") or 0)) / 1_000_000
    except Exception:
        return 0.0


def _call_openai(prompt, api_key, model):
    r = requests.post(
        OPENAI_RESPONSES_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "input": prompt}, timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    text = data.get("output_text")
    if not text:
        chunks = []
        for item in data.get("output") or []:
            for content in item.get("content") or []:
                if isinstance(content.get("text"), str): chunks.append(content["text"])
        text = "\n".join(chunks)
    usage = data.get("usage") or {}
    return _normalize_result(_extract_json(text)), {
        "input_tokens": int(usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
    }


def _call_openrouter(prompt, api_key, model):
    r = requests.post(
        OPENROUTER_CHAT_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                 "HTTP-Referer": "https://beesys.com.br", "X-Title": "BeeSys Lead Search"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}},
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    text = (((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
    usage = data.get("usage") or {}
    return _normalize_result(_extract_json(text)), {
        "input_tokens": int(usage.get("prompt_tokens") or 0),
        "output_tokens": int(usage.get("completion_tokens") or 0),
        "reported_cost_usd": float(usage.get("cost") or 0),
    }


def _call_gemini(prompt, api_key, model):
    url = f"{GEMINI_BASE_URL}/{model}:generateContent"
    r = requests.post(
        url, headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}},
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    parts = ((((data.get("candidates") or [{}])[0].get("content") or {}).get("parts")) or [])
    text = "\n".join(p.get("text", "") for p in parts if isinstance(p, dict))
    usage = data.get("usageMetadata") or {}
    return _normalize_result(_extract_json(text)), {
        "input_tokens": int(usage.get("promptTokenCount") or 0),
        "output_tokens": int(usage.get("candidatesTokenCount") or 0),
    }


def available_providers(keys: Dict[str, str]):
    out = []
    if keys.get("Gemini"): out.append("Gemini")
    if keys.get("OpenRouter"): out.append("OpenRouter")
    if keys.get("OpenAI"): out.append("OpenAI")
    return out


def _policy_block_reason(row, policy):
    policy = policy or {}
    min_score = int(policy.get("min_score") or 0)
    if int(row.get("visit_priority_score") or row.get("score") or 0) < min_score:
        return f"score abaixo de {min_score}"
    usage = ai_usage_today()
    call_limit = int(policy.get("daily_call_limit") or 0)
    if call_limit > 0 and usage["calls"] >= call_limit:
        return "limite diário de chamadas atingido"
    budget = float(policy.get("daily_budget_usd") or 0)
    if budget > 0 and usage["cost_usd"] >= budget:
        return "orçamento diário de IA atingido"
    return None


def enrich_lead(row, provider="Auto", keys=None, models=None, policy=None):
    keys = keys or {}
    models = {**DEFAULT_MODELS, **(models or {})}
    blocked = _policy_block_reason(row, policy)
    if blocked:
        return {"ai_skipped_reason": blocked}
    prompt = _prompt(row)
    order = available_providers(keys) if provider == "Auto" else [provider]
    errors = []
    for current in order:
        key = keys.get(current)
        if not key: continue
        model = models[current]
        try:
            if current == "Gemini": result, usage = _call_gemini(prompt, key, model)
            elif current == "OpenRouter": result, usage = _call_openrouter(prompt, key, model)
            elif current == "OpenAI": result, usage = _call_openai(prompt, key, model)
            else: continue
            cost = float(usage.get("reported_cost_usd") or 0) or _pricing_cost(current, model, usage.get("input_tokens"), usage.get("output_tokens"))
            record_ai_usage(current, model, row.get("business_key"), usage.get("input_tokens"), usage.get("output_tokens"), cost, True)
            if result:
                result["ai_provider_used"] = current
                result["ai_model_used"] = model
                result["ai_usage"] = {**usage, "estimated_cost_usd": cost}
                return result
        except Exception as exc:
            record_ai_usage(current, model, row.get("business_key"), 0, 0, 0, False, str(exc))
            errors.append(f"{current}: {str(exc)[:160]}")
    return {"ai_errors": errors} if errors else {}


def enrich_many(rows, provider="Auto", keys=None, models=None, limit=20, progress_cb=None, policy=None):
    done = 0
    targets = [r for r in rows if (r.get("score") or r.get("opportunity_score") or 0) > 0][: max(0, int(limit))]
    for row in targets:
        result = enrich_lead(row, provider=provider, keys=keys, models=models, policy=policy)
        if result:
            if result.get("ai_skipped_reason"):
                row["ai_skipped_reason"] = result["ai_skipped_reason"]
            elif result.get("ai_errors"):
                row["ai_error"] = "; ".join(result["ai_errors"])
            else:
                row["ai_summary"] = result.get("ai_summary") or row.get("ai_summary")
                row["why_approach"] = result.get("why_approach") or row.get("why_approach")
                row["sales_pitch"] = result.get("sales_pitch") or row.get("sales_pitch")
                row["ai_priority_adjustment"] = result.get("priority_adjustment", 0)
                row["ai_warnings"] = result.get("warnings") or []
                row["ai_provider_used"] = result.get("ai_provider_used")
                row["ai_model_used"] = result.get("ai_model_used")
                row["likely_objection"] = result.get("likely_objection")
                dm = result.get("decision_maker") or {}
                if dm.get("name") and int(dm.get("confidence") or 0) >= 50:
                    row["decision_maker_name"] = dm.get("name")
                    row["decision_maker_role"] = dm.get("role")
                    row["decision_maker_confidence"] = int(dm.get("confidence") or 0)
                if row.get("ai_priority_adjustment"):
                    row["visit_priority_score"] = max(0, min(100, int(row.get("visit_priority_score") or row.get("score") or 0) + int(row["ai_priority_adjustment"])))
        done += 1
        if progress_cb: progress_cb(done, len(targets))
    return rows
