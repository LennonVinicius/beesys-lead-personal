from statistics import mean

GOOGLE_AI_SOURCES = [
    {
        "title": "Google Search Central — Recursos de IA e seu site",
        "url": "https://developers.google.com/search/docs/appearance/ai-features?hl=pt-BR",
    },
    {
        "title": "Google Search Central — Otimização para recursos generativos",
        "url": "https://developers.google.com/search/docs/fundamentals/ai-optimization-guide?hl=pt-br",
    },
    {
        "title": "Google Search Central — Dados estruturados para negócios locais",
        "url": "https://developers.google.com/search/docs/appearance/structured-data/local-business?hl=pt-BR",
    },
    {
        "title": "Google Search Central — Relatórios de performance em IA generativa",
        "url": "https://developers.google.com/search/blog/2026/06/gen-ai-performance-reports",
    },
]


def _bool(v):
    return v is True or v == 1 or str(v).lower() in {"true", "1", "yes"}


def _pct(rows, predicate):
    if not rows:
        return 0.0
    return round(100 * sum(1 for r in rows if predicate(r)) / len(rows), 1)


def _num_avg(rows, key):
    vals = []
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
        "Alimentação": ["restaurant", "restaurante", "cafe", "café", "bar", "food", "pizza", "lanch", "padaria"],
        "Varejo": ["shop", "store", "loja", "market", "retail", "boutique", "papelaria", "mercearia"],
        "Serviços": ["office", "service", "serviço", "repair", "oficina", "academ", "fitness", "pet", "assistência", "assistencia"],
    }
    for label, words in groups.items():
        if any(w in text for w in words):
            return label
    return "Outros negócios"


def _metrics(rows):
    rows = rows or []
    total=len(rows)
    def counts(key, known_when=None):
        if known_when is None:
            known=rows
        else:
            known=[r for r in rows if known_when(r)]
        yes=sum(1 for r in known if _bool(r.get(key)))
        return {"yes":yes,"no":max(0,len(known)-yes),"known":len(known),"unknown":max(0,total-len(known))}
    site_identified=sum(1 for r in rows if bool(r.get("website")))
    functional=counts("site_functional",lambda r: bool(r.get("website")) and r.get("site_functional") is not None)
    booking=counts("has_booking",lambda r: bool(r.get("website")) and r.get("has_booking") is not None)
    catalog=counts("has_catalog",lambda r: bool(r.get("website")) and r.get("has_catalog") is not None)
    whatsapp=counts("has_whatsapp",lambda r: bool(r.get("website")) and r.get("has_whatsapp") is not None)
    structured=counts("has_structured_data",lambda r: bool(r.get("website")) and r.get("has_structured_data") is not None)
    def kpct(c): return round(100*c["yes"]/max(1,c["known"]),1) if c["known"] else 0.0
    return {
        "total": total,
        "website_pct": round(100*site_identified/max(1,total),1) if total else 0.0,
        "website_identified_count":site_identified,"website_not_identified_count":max(0,total-site_identified),
        "functional_site_pct": kpct(functional),"functional_site_counts":functional,
        "booking_pct": kpct(booking),"booking_counts":booking,
        "manual_booking_pct": _pct(rows, lambda r: _bool(r.get("manual_booking_detected"))),
        "catalog_pct": kpct(catalog),"catalog_counts":catalog,
        "whatsapp_pct": kpct(whatsapp),"whatsapp_counts":whatsapp,
        "instagram_pct": _pct(rows, lambda r: _bool(r.get("has_instagram"))),
        "structured_data_pct": kpct(structured),"structured_data_counts":structured,
        "local_business_schema_pct": _pct(rows, lambda r: _bool(r.get("has_local_business_schema"))),
        "online_presence_avg": _num_avg(rows, "presence_completeness_score"),
        "digital_maturity_avg": _num_avg(rows, "digital_maturity_score"),
        "ai_readiness_avg": _num_avg(rows, "ai_search_readiness_score"),
        "rating_avg": _num_avg(rows, "rating"),
        "reviews_avg": _num_avg(rows, "reviews"),
    }


def _dedupe(rows):
    out, seen = [], set()
    for row in rows or []:
        key = row.get("business_key")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(row)
    return out


def _benchmark(lead, rows):
    rows = _dedupe(rows)
    maturity = float(lead.get("digital_maturity_score") or 0)
    values = sorted(float(r.get("digital_maturity_score") or 0) for r in rows)
    if not values:
        return {"digital_maturity_rank": 1, "sample_size": 1, "percentile": 0.0}
    outperformed = sum(v < maturity for v in values)
    percentile = round(100 * outperformed / max(1, len(values)), 1)
    rank = 1 + sum(v > maturity for v in values)
    return {"digital_maturity_rank": rank, "sample_size": len(values), "percentile": percentile}


def build_business_report(lead, peers, job=None, city_peers=None, district_peers=None):
    radius_rows = _dedupe((peers or []) + [lead])
    city_rows = _dedupe((city_peers or radius_rows) + [lead])
    district_rows = _dedupe((district_peers or radius_rows) + [lead])
    segment = _segment(lead)

    radius_segment = [r for r in radius_rows if _segment(r) == segment]
    city_segment = [r for r in city_rows if _segment(r) == segment]
    district_segment = [r for r in district_rows if _segment(r) == segment]

    area = _metrics(radius_rows)
    segment_m = _metrics(radius_segment)
    city_m = _metrics(city_rows)
    city_segment_m = _metrics(city_segment)
    district_m = _metrics(district_rows)
    district_segment_m = _metrics(district_segment)

    gaps = []
    if not lead.get("website"):
        gaps.append({"severity": "high", "title": "Sem site próprio identificado", "detail": f"{area['website_pct']}% dos negócios analisados neste raio já possuem site identificado; entre negócios do mesmo segmento, são {segment_m['website_pct']}%."})
    elif not _bool(lead.get("site_functional")):
        gaps.append({"severity": "high", "title": "Site com problema de funcionamento", "detail": f"{area['functional_site_pct']}% da amostra do raio apresenta site funcional identificado."})
    if not _bool(lead.get("has_booking")):
        gaps.append({"severity": "medium", "title": "Sem agendamento online identificado", "detail": f"{segment_m['booking_pct']}% dos negócios do mesmo segmento no raio já possuem agendamento online identificado."})
    if not _bool(lead.get("has_catalog")):
        gaps.append({"severity": "medium", "title": "Sem catálogo ou serviços online identificados", "detail": f"{segment_m['catalog_pct']}% dos negócios semelhantes na região apresentam catálogo, menu ou serviços online."})
    if not _bool(lead.get("has_whatsapp")):
        gaps.append({"severity": "low", "title": "WhatsApp não identificado no site", "detail": f"{area['whatsapp_pct']}% da amostra regional possui integração ou link de WhatsApp identificado."})
    if lead.get("website") and not _bool(lead.get("has_structured_data")):
        gaps.append({"severity": "low", "title": "Dados estruturados não identificados", "detail": f"{area['structured_data_pct']}% da amostra analisada utiliza dados estruturados identificáveis no site."})

    readiness = int(lead.get("ai_search_readiness_score") or 0)
    ai_risk = (not lead.get("website")) or (lead.get("site_functional") is False) or _bool(lead.get("robots_noindex")) or readiness < 50
    ai_alert = None
    if ai_risk:
        ai_alert = {
            "level": "high",
            "title": "Risco de perder competitividade na busca com IA",
            "message": (
                "O Google afirma que AI Overviews e AI Mode usam os sistemas centrais da Pesquisa e conteúdo recuperado do índice do Google. "
                "Para uma página aparecer como link de suporte nessas experiências, ela precisa estar indexada e elegível para aparecer na Pesquisa. "
                "Em 2026, o Google também passou a oferecer relatórios específicos de visibilidade em recursos de IA generativa no Search Console. "
                "Um negócio sem site próprio funcional não desaparece automaticamente do Google — o Perfil da Empresa continua relevante para buscas locais —, "
                "mas possui menos conteúdo próprio rastreável, indexável e controlável para competir nessas experiências. Site acessível, conteúdo útil, dados locais atualizados "
                "e informações estruturadas coerentes fortalecem a presença digital sem depender de supostos 'hacks de IA'."
            ),
            "sources": GOOGLE_AI_SOURCES,
        }

    comparisons = [
        {"key": "radius", "label": "Negócios no raio", "sample_size": len(radius_rows), "metrics": area},
        {"key": "radius_segment", "label": "Mesmo segmento no raio", "sample_size": len(radius_segment), "metrics": segment_m},
        {"key": "city", "label": "Cidade", "sample_size": len(city_rows), "metrics": city_m},
        {"key": "city_segment", "label": "Mesmo segmento na cidade", "sample_size": len(city_segment), "metrics": city_segment_m},
        {"key": "district", "label": "Bairro/área da cidade", "sample_size": len(district_rows), "metrics": district_m},
        {"key": "district_segment", "label": "Mesmo segmento no bairro/área", "sample_size": len(district_segment), "metrics": district_segment_m},
    ]

    return {
        "lead": lead,
        "context": {
            "job_id": job.get("id") if job else None,
            "query_text": job.get("query_text") if job else None,
            "radius_m": job.get("radius_m") if job else None,
            "center_display_name": job.get("center_display_name") if job else None,
            "sample_size": len(radius_rows),
            "segment": segment,
            "segment_sample_size": len(radius_segment),
            "city_name": lead.get("city_name") or ((job or {}).get("config") or {}).get("city_name"),
            "district_name": lead.get("district_name") or ((job or {}).get("config") or {}).get("district_name"),
        },
        "area_metrics": area,
        "segment_metrics": segment_m,
        "city_metrics": city_m,
        "city_segment_metrics": city_segment_m,
        "district_metrics": district_m,
        "district_segment_metrics": district_segment_m,
        "comparisons": comparisons,
        "benchmark": _benchmark(lead, radius_rows),
        "city_benchmark": _benchmark(lead, city_rows),
        "segment_benchmark": _benchmark(lead, radius_segment),
        "gaps": gaps,
        "ai_search_alert": ai_alert,
        "disclaimer": "Os percentuais representam a amostra encontrada e analisada pelas fontes configuradas no BeeSys Lead Search. Não constituem censo oficial nem métrica de ranking do Google.",
    }
