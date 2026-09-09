import time
from db import (
    claim_search_job_batch,
    finish_search_job_item,
    get_search_job,
    hydrate_saved_state,
    load_history,
    recover_stale_search_job_items,
    upsert_businesses,
)
from analyzer import analyze_many
from learning import apply_learning, train_conversion_model
from scoring import apply_scores, finalize_visit_priorities
from ai_enrichment import enrich_many
from targeting import annotate_target_fit


_MODEL_CACHE = {"loaded_at": 0.0, "model": None}


def _conversion_model(ttl_seconds=90):
    now = time.monotonic()
    if _MODEL_CACHE["model"] is None or now - _MODEL_CACHE["loaded_at"] > ttl_seconds:
        _MODEL_CACHE["model"] = train_conversion_model(load_history(10000))
        _MODEL_CACHE["loaded_at"] = now
    return _MODEL_CACHE["model"]


def invalidate_learning_cache():
    _MODEL_CACHE["loaded_at"] = 0.0
    _MODEL_CACHE["model"] = None


def process_search_job_batch(job_id, batch_size=10, ai_keys=None, ai_models=None, ai_policy=None):
    job = get_search_job(job_id)
    if not job or job.get("status") in {"DONE", "FAILED", "CANCELED"}:
        return job
    config = job.get("config") or {}
    recover_stale_search_job_items(job_id, older_minutes=10)
    items = claim_search_job_batch(job_id, limit=max(1, int(batch_size)))
    if not items:
        return get_search_job(job_id)

    try:
        rows = [item.get("raw") or {} for item in items]
        hydrate_saved_state(rows, analysis_max_age_days=int(config.get("cache_days") or 14))

        analyze_enabled = bool(config.get("auto_analyze", True))
        if analyze_enabled:
            targets = [r for r in rows if r.get("_job_analyze", True)]
            if targets:
                analyze_many(
                    targets,
                    max_workers=min(6, max(1, len(targets))),
                    force_refresh=bool(config.get("force_refresh", False)),
                    cache_days=int(config.get("cache_days") or 14),
                )

        annotate_target_fit(rows)
        apply_scores(rows, config.get("score_profile") or "Auto")
        model = _conversion_model()
        apply_learning(rows, model)
        finalize_visit_priorities(rows)

        ai_provider = config.get("ai_provider") or "Desativada"
        ai_limit_per_batch = min(len(rows), int(config.get("ai_limit_per_batch") or len(rows)))
        if ai_provider != "Desativada" and ai_limit_per_batch > 0 and any((ai_keys or {}).values()):
            rows.sort(key=lambda x: x.get("visit_priority_score") or 0, reverse=True)
            enrich_many(
                rows,
                provider=ai_provider,
                keys=ai_keys or {},
                models=ai_models or {},
                limit=ai_limit_per_batch,
                policy=ai_policy or {},
            )
            finalize_visit_priorities(rows)

        upsert_businesses(rows)
        by_key = {r.get("business_key"): r for r in rows}
        for item in items:
            key = item.get("business_key")
            result = by_key.get(key)
            if result is None:
                finish_search_job_item(item["id"], error="Item não processado")
            else:
                finish_search_job_item(item["id"], result=result)
    except Exception as exc:
        # Evita itens eternamente em PROCESSING se um lote falhar.
        for item in items:
            finish_search_job_item(item["id"], error=str(exc))
        raise
    return get_search_job(job_id)
