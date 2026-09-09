import re
import unicodedata
from collections import Counter

# Grandes redes que normalmente exigem negociação corporativa/franqueadora e
# têm menor eficiência para prospecção presencial local. A lista é deliberadamente
# conservadora: o sistema rebaixa/oculta essas redes, mas pode incluí-las se o
# usuário ativar a opção na busca.
LARGE_CHAIN_PATTERNS = [
    "mcdonald", "burger king", "subway", "starbucks", "kfc", "habib", "giraffas",
    "outback", "coco bambu", "carrefour", "assai", "atacadao", "extra mercado",
    "pao de acucar", "droga raia", "drogasil", "pague menos", "drogaria sao paulo",
    "drogaria pacheco", "ultrafarma", "ipanema drogarias", "smart fit", "bluefit",
    "renner", "riachuelo", "c&a", "centauro", "casas bahia", "magazine luiza",
    "americanas", "kalunga", "cobasi", "petz", "leroy merlin", "tok stok",
]

LOCAL_FOCUS_HINTS = [
    "barbear", "barber", "salao", "salão", "cabele", "manicure", "nail", "estetica", "estética",
    "papelaria", "boutique", "atelier", "studio", "clínica", "clinica", "odonto", "dent",
    "fisio", "psico", "nutri", "pet shop", "oficina", "assistencia", "assistência",
    "loja", "mercearia", "padaria", "cafeteria", "academia", "escola", "curso",
]


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9 ]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def normalized_brand_name(name: str) -> str:
    text = _norm(name)
    # Remove sufixos comuns de filial/unidade para identificar repetições.
    text = re.sub(r"\b(unidade|loja|filial|shopping|sjc|centro|[0-9]{1,3})\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def is_known_large_chain(name: str, website: str = "") -> bool:
    blob = f"{_norm(name)} {_norm(website)}"
    return any(pattern in blob for pattern in LARGE_CHAIN_PATTERNS)


def annotate_target_fit(rows):
    rows = rows or []
    counts = Counter(normalized_brand_name(r.get("name")) for r in rows if r.get("name"))
    for row in rows:
        brand = normalized_brand_name(row.get("name"))
        repeats = counts.get(brand, 1)
        known_chain = is_known_large_chain(row.get("name"), row.get("website"))
        size = str(row.get("company_size_estimate") or "")
        blob = _norm(f"{row.get('name','')} {row.get('category','')}")
        local_hint = any(_norm(x) in blob for x in LOCAL_FOCUS_HINTS)

        large = bool(known_chain or repeats >= 5 or size in {"Grande/rede", "Rede/grande"})
        if large:
            fit, reason = 8, "Grande rede ou marca com várias unidades; menor prioridade para abordagem local."
        elif repeats >= 3:
            fit, reason = 45, "Possível rede regional; pode exigir contato com um decisor fora da unidade."
        elif local_hint:
            fit, reason = 95, "Perfil compatível com prospecção local de pequeno ou médio negócio."
        else:
            fit, reason = 78, "Negócio aparentemente local; manter no ranking comercial."

        row["is_large_chain"] = large
        row["target_fit_score"] = fit
        row["target_fit_reason"] = reason
        if not row.get("pitch_variant"):
            stable = sum(ord(ch) for ch in str(row.get("business_key") or row.get("name") or ""))
            row["pitch_variant"] = "A" if stable % 2 == 0 else "B"
    return rows
