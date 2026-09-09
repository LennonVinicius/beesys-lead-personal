from datetime import datetime, timezone

APPOINTMENT_HINTS = [
    "barber", "barbear", "salão", "salao", "beauty", "beleza", "estética", "estetica",
    "clinic", "clínica", "clinica", "dent", "psico", "fisio", "terapia", "spa", "nail",
    "manicure", "cabele", "hair", "academia", "fitness", "personal", "pet", "veter",
]
FOOD_HINTS = ["restaurant", "restaurante", "cafeter", "pizza", "hamburg", "bar", "food", "padaria", "bakery", "lanch"]
RETAIL_HINTS = ["shop", "loja", "market", "mercado", "farmácia", "farmacia", "store", "boutique", "varejo"]

PIPELINE_BOOST = {
    "NEW": 0,
    "PRIORITY": 4,
    "ROUTE_PLANNED": 2,
    "VISITED": 1,
    "INTERESTED": 12,
    "DEMO": 16,
    "PROPOSAL": 18,
    "CLIENT": -100,
    "LOST": -100,
    "DO_NOT_CONTACT": -100,
}


def infer_profile(row, requested="Auto"):
    if requested and requested != "Auto":
        return requested
    blob = f"{row.get('name','')} {row.get('category','')}".lower()
    if any(x in blob for x in APPOINTMENT_HINTS):
        return "Agenda/Serviços"
    if any(x in blob for x in FOOD_HINTS):
        return "Alimentação"
    if any(x in blob for x in RETAIL_HINTS):
        return "Varejo"
    return "Geral"


def _num(value, cast=float):
    try:
        return cast(value) if value is not None else None
    except Exception:
        return None


def digital_maturity(row, profile="Geral"):
    if not row.get("website"):
        score = 5 if (row.get("phone") or row.get("has_whatsapp")) else 0
        if row.get("has_instagram") or row.get("has_facebook"):
            score += 5
        return min(100, score)
    score = 15
    if row.get("site_functional"):
        score += 20
    if row.get("site_https"):
        score += 8
    if row.get("site_mobile"):
        score += 12
    quality = _num(row.get("site_quality_score"), int)
    if quality is not None:
        score += round(quality * 0.15)
    if row.get("has_contact_form") or row.get("has_whatsapp"):
        score += 7
    if row.get("has_instagram") or row.get("has_facebook"):
        score += 5
    if row.get("has_catalog"):
        score += 8 if profile in {"Alimentação", "Varejo"} else 5
    if row.get("has_booking"):
        score += 18 if profile == "Agenda/Serviços" else 8
    return min(100, int(score))


def opportunity_score(row, profile_request="Auto"):
    """Quanto o lead parece precisar da BeeSys / ter gap digital acionável."""
    profile = infer_profile(row, profile_request)
    row["score_profile"] = profile
    row["digital_maturity_score"] = digital_maturity(row, profile)

    score = 0
    reasons = []
    website = bool(row.get("website"))
    site_ok = row.get("site_functional")
    has_booking = row.get("has_booking")
    has_catalog = row.get("has_catalog")

    if not website:
        score += 28
        reasons.append("Sem site (+28)")
    elif site_ok is False:
        score += 23
        reasons.append("Site indisponível/com problema (+23)")
    elif (row.get("site_quality_score") or 0) < 45:
        score += 15
        reasons.append("Site funcional, mas fraco (+15)")
    else:
        reasons.append("Site funcional")

    booking_weight = 25 if profile == "Agenda/Serviços" else 12
    if row.get("manual_booking_detected"):
        score += min(booking_weight, 22)
        channel = row.get("manual_booking_channel") or "mensagens"
        reasons.append(f"Agenda manual detectada via {channel} (+{min(booking_weight, 22)})")
    elif not website or has_booking is False:
        score += booking_weight
        reasons.append(f"Sem agendamento online detectado (+{booking_weight})")
    elif has_booking is True:
        provider = row.get("booking_provider")
        reasons.append(f"Já possui agendamento{f' via {provider}' if provider else ''}")

    catalog_weight = 15 if profile in {"Alimentação", "Varejo"} else 8
    if not website or has_catalog is False:
        score += catalog_weight
        reasons.append(f"Sem catálogo/serviços online detectados (+{catalog_weight})")

    if website and site_ok:
        if row.get("site_mobile") is False:
            score += 6
            reasons.append("Site pouco preparado para celular (+6)")
        if row.get("site_https") is False:
            score += 3
            reasons.append("Site sem HTTPS (+3)")
        ms = _num(row.get("site_response_ms"), int)
        if ms and ms > 5000:
            score += 4
            reasons.append("Site lento (>5s) (+4)")
        if row.get("has_contact_form") is False and not row.get("has_whatsapp"):
            score += 3
            reasons.append("Poucos canais de conversão no site (+3)")

    if row.get("competitor_detected"):
        score -= 12
        reasons.append(f"Já usa concorrente: {row.get('competitor_name') or 'detectado'} (-12)")

    # Um negócio com reputação/movimento prova que o gap digital tem valor comercial.
    rating = _num(row.get("rating"), float)
    reviews = _num(row.get("reviews"), int)
    if rating is not None and rating >= 4.5:
        score += 6
        reasons.append(f"Boa reputação: {rating:.1f}/5 (+6)")
    if reviews is not None:
        if reviews >= 200:
            score += 9
            reasons.append(f"Alta movimentação: {reviews} avaliações (+9)")
        elif reviews >= 80:
            score += 7
            reasons.append(f"Boa movimentação: {reviews} avaliações (+7)")
        elif reviews >= 25:
            score += 4
            reasons.append(f"Movimentação relevante: {reviews} avaliações (+4)")

    if row.get("phone") or row.get("has_whatsapp"):
        score += 4
        reasons.append("Contato disponível (+4)")

    if row.get("do_not_contact") or (row.get("pipeline_status") in {"CLIENT", "LOST", "DO_NOT_CONTACT"}):
        score = 0
        reasons.append("Fora da prospecção ativa")

    return max(0, min(100, int(score))), reasons


def commercial_potential(row):
    """Chance de o estabelecimento ter movimento/porte e valer esforço comercial."""
    score = 20
    reasons = []
    rating = _num(row.get("rating"), float)
    reviews = _num(row.get("reviews"), int)

    if rating is not None:
        if rating >= 4.6:
            score += 18
            reasons.append("Reputação muito forte")
        elif rating >= 4.2:
            score += 13
            reasons.append("Boa reputação")
        elif rating >= 3.8:
            score += 7
        elif rating < 3.2:
            score -= 10
            reasons.append("Reputação baixa")

    if reviews is not None:
        if reviews >= 300:
            score += 30
            reasons.append("Volume de avaliações muito alto")
        elif reviews >= 120:
            score += 24
            reasons.append("Volume de avaliações alto")
        elif reviews >= 50:
            score += 18
            reasons.append("Bom volume de avaliações")
        elif reviews >= 15:
            score += 10
        elif reviews < 5:
            score -= 5

    if row.get("phone") or row.get("has_whatsapp"):
        score += 7
    if row.get("has_instagram"):
        score += 6
    if row.get("has_facebook"):
        score += 3
    if row.get("open_now") is True:
        score += 4

    size = row.get("company_size_estimate")
    if size == "Médio/grande":
        score += 10
        reasons.append("Porte estimado médio/grande")
    elif size == "Pequeno/médio":
        score += 6
        reasons.append("Porte estimado pequeno/médio")

    status = row.get("pipeline_status") or "NEW"
    boost = PIPELINE_BOOST.get(status, 0)
    if boost > 0:
        score += boost
        reasons.append(f"Sinal positivo no funil: {status}")
    elif boost < 0:
        score = 0

    if row.get("do_not_contact"):
        score = 0
    return max(0, min(100, int(score))), reasons


def finalize_visit_priority(row):
    opportunity = float(row.get("opportunity_score") or row.get("score") or 0)
    potential = float(row.get("commercial_potential_score") or 0)
    probability = _num(row.get("conversion_probability"), float)
    if probability is None:
        probability = 15.0

    priority = 0.46 * opportunity + 0.34 * potential + 0.20 * probability
    status = row.get("pipeline_status") or "NEW"
    if status == "INTERESTED":
        priority += 8
    elif status == "DEMO":
        priority += 10
    elif status == "PROPOSAL":
        priority += 12
    if row.get("open_now") is False:
        priority -= 8
    elif row.get("open_now") is True:
        priority += 3
    if row.get("visited") and status in {"NEW", "VISITED"}:
        priority -= 12
    if row.get("do_not_contact") or status in {"CLIENT", "LOST", "DO_NOT_CONTACT"}:
        priority = 0
    row["visit_priority_score"] = max(0, min(100, int(round(priority))))
    return row["visit_priority_score"]


def build_why_approach(row):
    if row.get("pipeline_status") in {"CLIENT", "LOST", "DO_NOT_CONTACT"} or row.get("do_not_contact"):
        return "Lead fora da prospecção ativa pelo status do CRM."
    strengths, gaps = [], []
    if (row.get("rating") or 0) >= 4.4:
        strengths.append(f"boa reputação ({float(row['rating']):.1f}/5)")
    if (row.get("reviews") or 0) >= 50:
        strengths.append(f"{int(row['reviews'])} avaliações")
    if row.get("manual_booking_detected"):
        gaps.append(f"o agendamento parece manual via {row.get('manual_booking_channel') or 'mensagens'}")
    elif row.get("has_booking") is False:
        gaps.append("não foi encontrado agendamento online")
    if not row.get("website"):
        gaps.append("não possui site identificado")
    elif not row.get("site_functional"):
        gaps.append("o site apresenta problema")
    elif (row.get("site_quality_score") or 0) < 50:
        gaps.append("o site tem baixa maturidade técnica")
    if row.get("has_catalog") is False:
        gaps.append("não foi encontrado catálogo/serviços online")
    if row.get("competitor_detected"):
        gaps.append(f"já usa {row.get('competitor_name')}, então a abordagem deve focar migração/diferenciais")
    left = ", ".join(strengths) if strengths else "há presença comercial identificável"
    right = "; ".join(gaps[:3]) if gaps else "a presença digital já é razoável"
    return f"Vale abordar porque {left}, enquanto {right}."


def build_sales_pitch(row):
    name = row.get("name") or "o negócio"
    variant = row.get("pitch_variant") or "A"
    if row.get("manual_booking_detected"):
        channel = row.get("manual_booking_channel") or "WhatsApp/direct"
        if variant == "B":
            return (
                f"Vi que {name} recebe bastante contato pelo {channel}. Hoje vocês sentem que perdem tempo organizando horários manualmente? "
                "A BeeSys foi pensada justamente para reduzir esse vai-e-volta sem afastar o cliente do WhatsApp."
            )
        return (
            f"Vi que {name} parece receber agendamentos pelo {channel}. A BeeSys pode organizar horários automaticamente "
            "sem tirar o contato direto com os clientes e reduzindo o vai-e-volta de mensagens."
        )
    if row.get("competitor_detected"):
        if variant == "B":
            return (
                f"Percebi que {name} já usa {row.get('competitor_name')}. O que vocês mais gostam e o que mais incomoda no sistema atual? "
                "Posso mostrar rapidamente onde a BeeSys é diferente e vocês comparam sem compromisso."
            )
        return (
            f"Percebi que {name} já usa {row.get('competitor_name')}. Eu mostraria a BeeSys comparando organização, "
            "personalização, relacionamento via WhatsApp e custo, sem pedir troca imediata."
        )
    if row.get("has_booking") is False:
        if variant == "B":
            return (
                f"Não encontrei uma agenda online clara de {name}. Vocês organizam os horários por mensagem hoje? "
                "Se sim, consigo te mostrar em poucos minutos como a BeeSys reduz esse trabalho."
            )
        return (
            f"Vi que {name} tem presença local, mas não encontrei um agendamento online claro. "
            "A BeeSys pode organizar horários e reduzir o vai-e-volta no WhatsApp sem tirar o contato direto com os clientes."
        )
    if not row.get("website") or not row.get("site_functional"):
        return (
            f"A oportunidade em {name} é melhorar a presença digital e concentrar serviços, contato e agendamento "
            "em uma experiência mais profissional para o cliente."
        )
    return f"Eu abordaria {name} mostrando como a BeeSys pode centralizar operação, atendimento e experiência do cliente em um só fluxo."


def score_business(row, profile_request="Auto"):
    # Compatibilidade: `score` continua sendo o score de oportunidade.
    score, reasons = opportunity_score(row, profile_request)
    row["opportunity_score"] = score
    row["score"] = score
    potential, potential_reasons = commercial_potential(row)
    row["commercial_potential_score"] = potential
    row["potential_reasons"] = potential_reasons
    finalize_visit_priority(row)
    return score, reasons


def apply_scores(rows, profile_request="Auto"):
    for row in rows:
        row["score"], row["score_reasons"] = score_business(row, profile_request)
        row["why_approach"] = build_why_approach(row)
        row["sales_pitch"] = build_sales_pitch(row)
    return rows


def finalize_visit_priorities(rows):
    for row in rows:
        finalize_visit_priority(row)
    return rows
