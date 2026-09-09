import math
from collections import Counter

LABEL_POSITIVE = {"CLIENT"}
LABEL_NEGATIVE = {"LOST"}

FEATURES = [
    "no_website",
    "site_problem",
    "no_booking",
    "manual_booking",
    "no_catalog",
    "strong_rating",
    "many_reviews",
    "has_whatsapp",
    "competitor",
    "appointment_profile",
]


def _truthy(value):
    return value is True or value == 1 or str(value).lower() in {"true", "1", "yes"}


def feature_vector(row):
    profile = (row.get("score_profile") or "").lower()
    rating = row.get("rating")
    reviews = row.get("reviews")
    try:
        rating = float(rating) if rating is not None else None
    except Exception:
        rating = None
    try:
        reviews = int(reviews) if reviews is not None else None
    except Exception:
        reviews = None

    return {
        "no_website": not bool(row.get("website")),
        "site_problem": bool(row.get("website")) and row.get("site_functional") is False,
        "no_booking": row.get("has_booking") is False,
        "manual_booking": _truthy(row.get("manual_booking_detected")),
        "no_catalog": row.get("has_catalog") is False,
        "strong_rating": rating is not None and rating >= 4.4,
        "many_reviews": reviews is not None and reviews >= 50,
        "has_whatsapp": _truthy(row.get("has_whatsapp")),
        "competitor": _truthy(row.get("competitor_detected")),
        "appointment_profile": "agenda" in profile or "servi" in profile,
    }


def train_conversion_model(rows, min_samples=8):
    """
    Bernoulli Naive Bayes simples, calculado apenas com CLIENT vs LOST.
    Funciona sem dependências de ML e só é ativado quando há histórico suficiente.
    """
    labelled = []
    for row in rows:
        status = row.get("pipeline_status") or "NEW"
        if status in LABEL_POSITIVE:
            labelled.append((feature_vector(row), 1))
        elif status in LABEL_NEGATIVE:
            labelled.append((feature_vector(row), 0))

    total = len(labelled)
    positives = sum(y for _, y in labelled)
    negatives = total - positives
    if total < int(min_samples) or positives == 0 or negatives == 0:
        return {
            "ready": False,
            "samples": total,
            "positives": positives,
            "negatives": negatives,
            "reason": "São necessários ao menos alguns CLIENT e LOST para aprender com segurança.",
        }

    # Priors com suavização de Laplace.
    prior_pos = (positives + 1) / (total + 2)
    prior_neg = (negatives + 1) / (total + 2)

    counts = {f: {1: Counter(), 0: Counter()} for f in FEATURES}
    for vector, label in labelled:
        for feat in FEATURES:
            counts[feat][label][bool(vector[feat])] += 1

    conditional = {}
    for feat in FEATURES:
        conditional[feat] = {}
        for label, n_label in ((1, positives), (0, negatives)):
            true_count = counts[feat][label][True]
            # Bernoulli likelihood com suavização.
            p_true = (true_count + 1) / (n_label + 2)
            conditional[feat][label] = p_true

    return {
        "ready": True,
        "samples": total,
        "positives": positives,
        "negatives": negatives,
        "prior_pos": prior_pos,
        "prior_neg": prior_neg,
        "conditional": conditional,
    }


def predict_conversion_probability(row, model, fallback_probability=None):
    if fallback_probability is None:
        fallback_probability = 0.18
    if not model or not model.get("ready"):
        return float(fallback_probability), []

    vector = feature_vector(row)
    log_pos = math.log(max(model["prior_pos"], 1e-9))
    log_neg = math.log(max(model["prior_neg"], 1e-9))
    explanations = []

    for feat in FEATURES:
        value = bool(vector[feat])
        p_pos_true = model["conditional"][feat][1]
        p_neg_true = model["conditional"][feat][0]
        p_pos = p_pos_true if value else 1 - p_pos_true
        p_neg = p_neg_true if value else 1 - p_neg_true
        log_pos += math.log(max(p_pos, 1e-9))
        log_neg += math.log(max(p_neg, 1e-9))

        if value:
            lift = (p_pos_true + 1e-6) / (p_neg_true + 1e-6)
            if lift >= 1.35:
                explanations.append((lift, f"{feat} apareceu mais entre clientes convertidos"))
            elif lift <= 0.74:
                explanations.append((1 / max(lift, 1e-6), f"{feat} apareceu mais entre leads perdidos"))

    # Stable logistic from two log likelihoods.
    delta = max(-40, min(40, log_pos - log_neg))
    probability = 1 / (1 + math.exp(-delta))
    explanations.sort(key=lambda x: x[0], reverse=True)
    return probability, [text for _, text in explanations[:3]]


def fallback_probability_from_scores(row):
    opportunity = float(row.get("opportunity_score") or row.get("score") or 0)
    potential = float(row.get("commercial_potential_score") or 0)
    stage = row.get("pipeline_status") or "NEW"
    stage_bonus = {
        "NEW": 0.00,
        "PRIORITY": 0.03,
        "ROUTE_PLANNED": 0.01,
        "VISITED": 0.02,
        "INTERESTED": 0.15,
        "DEMO": 0.28,
        "PROPOSAL": 0.40,
    }.get(stage, 0.0)
    # Heurística conservadora até existir histórico real.
    base = 0.03 + (opportunity / 100) * 0.11 + (potential / 100) * 0.12 + stage_bonus
    return max(0.02, min(0.80, base))


def apply_learning(rows, model):
    for row in rows:
        fallback = fallback_probability_from_scores(row)
        probability, why = predict_conversion_probability(row, model, fallback)
        row["conversion_probability"] = round(probability * 100, 1)
        row["learning_reasons"] = why
        row["learning_model_ready"] = bool(model and model.get("ready"))
    return rows
