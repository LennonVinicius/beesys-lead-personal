import math
import re
from statistics import mean

GOOGLE_AI_SOURCES = [
    {
        "title": "Google Search Central — Recursos de IA e seu site",
        "url": "https://developers.google.com/search/docs/appearance/ai-features?hl=pt-BR",
    },
    {
        "title": "Google Search Central — Otimização para recursos generativos",
        "url": "https://developers.google.com/search/docs/fundamentals/ai-optimization-guide",
    },
]


def _bool(v):
    return v is True or v == 1 or str(v).lower() in {"true", "1", "yes"}


def _pct(rows, predicate):
    if not rows:
        return 0.0
    return round(100 * sum(1 for r in rows if predicate(r)) / len(rows), 1)


def _num_avg(rows, key):
    vals=[]
    for r in rows:
        try:
            if r.get(key) is not None:
                vals.append(float(r[key]))
        except Exception:
            pass
    return round(mean(vals), 1) if vals else None


def _segment(row):
    text = f"{row.get('category') or ''} {row.get('name') or ''}".lower()
    groups = {
        "Beleza e cuidados": ["barber", "barbear", "salon", "salão", "cabele", "beauty", "nail", "manicure", "estética", "aesthetic", "spa"],
        "Saúde": ["clinic", "clínic", "dent", "doctor", "méd", "medic", "health", "fisio", "psico", "nutri"],
        "Alimentação": ["restaurant", "restaurante", "cafe", "café", "bar", "food", "pizza", "lanch"],
        "Varejo": ["shop", "store", "loja", "market", "retail", "boutique"],
        "Serviços": ["office", "service", "serviço", "repair", "oficina", "academ", "fitness", "pet"],
    }
    for label, words in groups.items():
        if any(w in text for w in words):
            return label
    return "Outros negócios"


def _metrics(rows):
    return {
        "total": len(rows),
        "website_pct": _pct(rows, lambda r: bool(r.get("website"))),
        "functional_site_pct": _pct(rows, lambda r: _bool(r.get("site_functional"))),
        "booking_pct": _pct(rows, lambda r: _bool(r.get("has_booking"))),
        "manual_booking_pct": _pct(rows, lambda r: _bool(r.get("manual_booking_detected"))),
        "catalog_pct": _pct(rows, lambda r: _bool(r.get("has_catalog"))),
        "whatsapp_pct": _pct(rows, lambda r: _bool(r.get("has_whatsapp"))),
        "instagram_pct": _pct(rows, lambda r: _bool(r.get("has_instagram"))),
        "structured_data_pct": _pct(rows, lambda r: _bool(r.get("has_structured_data"))),
        "online_presence_avg": _num_avg(rows, "presence_completeness_score"),
        "digital_maturity_avg": _num_avg(rows, "digital_maturity_score"),
        "ai_readiness_avg": _num_avg(rows, "ai_search_readiness_score"),
        "rating_avg": _num_avg(rows, "rating"),
        "reviews_avg": _num_avg(rows, "reviews"),
    }


def build_business_report(lead, peers, job=None):
    peers = [p for p in peers if p.get("business_key") != lead.get("business_key")]
    all_rows = peers + [lead]
    segment = _segment(lead)
    segment_rows = [r for r in all_rows if _segment(r) == segment]
    area = _metrics(all_rows)
    segment_m = _metrics(segment_rows)

    maturity = float(lead.get("digital_maturity_score") or 0)
    maturity_values = sorted(float(r.get("digital_maturity_score") or 0) for r in all_rows)
    outperformed = sum(v < maturity for v in maturity_values)
    percentile = round(100 * outperformed / max(1, len(maturity_values)), 1)
    rank = 1 + sum(v > maturity for v in maturity_values)

    gaps=[]
    if not lead.get("website"):
        gaps.append({"severity":"high","title":"Sem site próprio identificado","detail":f"{area['website_pct']}% da base analisada neste raio possui site identificado."})
    elif not _bool(lead.get("site_functional")):
        gaps.append({"severity":"high","title":"Site com problema de funcionamento","detail":f"{area['functional_site_pct']}% dos negócios analisados têm site funcional identificado."})
    if not _bool(lead.get("has_booking")):
        gaps.append({"severity":"medium","title":"Sem agendamento online identificado","detail":f"{area['booking_pct']}% da base do raio já possui agendamento online identificado."})
    if not _bool(lead.get("has_catalog")):
        gaps.append({"severity":"medium","title":"Sem catálogo ou serviços online identificados","detail":f"{area['catalog_pct']}% dos negócios analisados apresentam catálogo, menu ou serviços online."})
    if not _bool(lead.get("has_whatsapp")):
        gaps.append({"severity":"low","title":"WhatsApp não identificado no site","detail":f"{area['whatsapp_pct']}% da base analisada apresenta integração ou link de WhatsApp."})

    ai_alert = None
    if not lead.get("website") or not _bool(lead.get("site_functional")):
        ai_alert = {
            "level": "high",
            "title": "Alerta de competitividade na busca com IA",
            "message": (
                "Sem um site próprio, funcional e indexável, o negócio tem menos superfície digital própria para aparecer como "
                "link de suporte em experiências como AI Overviews e AI Mode. O Google informa que páginas precisam estar "
                "indexadas e elegíveis para a Pesquisa para serem usadas como links nessas experiências. Isso não significa "
                "desaparecer automaticamente do Google — o Perfil da Empresa continua importante —, mas aumenta a dependência "
                "de plataformas de terceiros e reduz o controle sobre a presença digital."
            ),
            "sources": GOOGLE_AI_SOURCES,
        }

    return {
        "lead": lead,
        "context": {
            "job_id": job.get("id") if job else None,
            "query_text": job.get("query_text") if job else None,
            "radius_m": job.get("radius_m") if job else None,
            "center_display_name": job.get("center_display_name") if job else None,
            "sample_size": len(all_rows),
            "segment": segment,
            "segment_sample_size": len(segment_rows),
        },
        "area_metrics": area,
        "segment_metrics": segment_m,
        "benchmark": {"digital_maturity_rank": rank, "sample_size": len(all_rows), "percentile": percentile},
        "gaps": gaps,
        "ai_search_alert": ai_alert,
        "disclaimer": "Os percentuais representam a base de estabelecimentos encontrada e analisada nesta busca pelas fontes configuradas. Não são um censo oficial de todos os negócios da região.",
    }
