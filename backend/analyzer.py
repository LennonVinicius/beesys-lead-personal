import ipaddress
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from db import get_cached_site_analysis, set_cached_site_analysis

UA = "Mozilla/5.0 (compatible; BeeSysLeadSearch/0.3; +local business website audit)"
ANALYSIS_VERSION = "6.0"

BOOKING_WORDS = [
    "agendar", "agendamento", "agende", "agenda online", "marcar horário", "marcar horario",
    "reservar", "reserva", "booking", "appointment", "book now", "schedule", "horários disponíveis",
]
MANUAL_BOOKING_PATTERNS = {
    "WhatsApp": [
        r"agend\w*.{0,45}whats", r"marc\w*.{0,45}whats", r"hor[aá]rio.{0,45}whats",
        r"whats.{0,45}agend", r"cham\w*.{0,30}whats",
    ],
    "Instagram/Direct": [
        r"agend\w*.{0,45}direct", r"marc\w*.{0,45}direct", r"cham\w*.{0,30}direct",
        r"direct.{0,45}agend", r"instagram.{0,45}agend",
    ],
    "Telefone": [r"agend\w*.{0,45}telefone", r"marc\w*.{0,45}telefone", r"ligue.{0,45}agend"],
}
BOOKING_PROVIDERS = {
    "Trinks": ["trinks.com", "trinks.", "use.trinks"],
    "Gendo": ["gendo.com.br", "gendo."],
    "Booksy": ["booksy.com", "booksy."],
    "Fresha": ["fresha.com", "fresha."],
    "AgendaPro": ["agendapro.com", "agendapro."],
    "Calendly": ["calendly.com", "calendly."],
    "Setmore": ["setmore.com", "setmore."],
    "SimplyBook": ["simplybook.me", "simplybook."],
    "Mindbody": ["mindbodyonline.com", "mindbody."],
    "Zenoti": ["zenoti.com", "zenoti."],
    "Reservio": ["reservio.com", "reservio."],
    "Doctoralia": ["doctoralia.com.br", "doctoralia."],
}
CATALOG_WORDS = [
    "catálogo", "catalogo", "catalog", "produtos", "products", "serviços", "servicos",
    "services", "cardápio", "cardapio", "menu", "loja", "shop", "e-commerce", "ecommerce",
    "portfólio", "portfolio", "preços", "precos", "tabela de preços", "tabela de precos",
]
CONTACT_WORDS = ["contato", "fale conosco", "mensagem", "enviar", "telefone", "email", "e-mail"]
TECH_SIGNATURES = {
    "WordPress": ["wp-content", "wp-includes", "wordpress"],
    "Wix": ["wixstatic.com", "wix.com", "wix-code"],
    "Shopify": ["cdn.shopify.com", "shopify"],
    "Nuvemshop": ["nuvemshop.com.br", "tiendanube.com"],
    "Squarespace": ["squarespace.com", "static1.squarespace.com"],
    "Webflow": ["webflow.com", "website-files.com"],
    "Next.js": ["/_next/", "__next_data__"],
    "React": ["reactroot", "data-reactroot"],
}
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)

DECISION_PATTERNS = [
    re.compile(r"(?:fundador(?:a)?|propriet[aá]ri[oa]|s[oó]ci[oa]|diretor(?:a)?|ceo|respons[aá]vel)\s*[:\-–]?\s*([A-ZÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇ][A-Za-zÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇáàâãéèêíïóôõöúç]+(?:\s+[A-ZÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇ][A-Za-zÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇáàâãéèêíïóôõöúç]+){1,3})", re.I),
    re.compile(r"([A-ZÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇ][A-Za-zÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇáàâãéèêíïóôõöúç]+(?:\s+[A-ZÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇ][A-Za-zÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇáàâãéèêíïóôõöúç]+){1,3})\s*[—–\-:,]+\s*(?:fundador(?:a)?|propriet[aá]ri[oa]|s[oó]ci[oa]|diretor(?:a)?|ceo)", re.I),
]


def _decision_maker_candidates(text):
    text = " ".join((text or "").split())[:400_000]
    out = []
    seen = set()
    for pattern in DECISION_PATTERNS:
        for match in pattern.finditer(text):
            name = (match.group(1) or "").strip(" -–—,:.")
            key = name.lower()
            if len(name.split()) < 2 or key in seen or len(name) > 80:
                continue
            seen.add(key)
            context = text[max(0, match.start()-80): min(len(text), match.end()+80)]
            role_match = re.search(r"fundador(?:a)?|propriet[aá]ri[oa]|s[oó]ci[oa]|diretor(?:a)?|ceo|respons[aá]vel", context, re.I)
            out.append({"name": name, "role": role_match.group(0) if role_match else None, "confidence": 62})
            if len(out) >= 5:
                return out
    return out


def _estimate_company_size(page_text, reviews=None):
    text = (page_text or "").lower()
    team_hits = len(re.findall(r"\b(equipe|profissionais|especialistas|barbeiros|cabeleireiros|dentistas|m[eé]dicos|colaboradores)\b", text))
    unit_hits = len(re.findall(r"\b(unidades?|filiais?|nossas lojas|endereços)\b", text))
    reviews = int(reviews or 0)
    if unit_hits >= 2 or reviews >= 500:
        return "Médio/grande"
    if team_hits >= 3 or reviews >= 120:
        return "Pequeno/médio"
    return "Pequeno"


def normalize_url(url):
    if not url:
        return None
    url = str(url).strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    return url




def _validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Somente URLs HTTP/HTTPS são permitidas")
    if parsed.username or parsed.password:
        raise ValueError("URL com credenciais não é permitida")
    host = (parsed.hostname or "").strip().lower()
    if not host or host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValueError("Host local não permitido")
    if parsed.port and parsed.port not in {80, 443}:
        raise ValueError("Porta não permitida na auditoria")
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"DNS inválido: {exc}")
    ips = {info[4][0].split("%", 1)[0] for info in infos}
    if not ips:
        raise ValueError("Host sem endereço IP")
    for value in ips:
        ip = ipaddress.ip_address(value)
        if not ip.is_global:
            raise ValueError("Endereço privado/reservado bloqueado pela proteção SSRF")
    return url


def _safe_fetch_html(url: str, max_redirects=5, max_bytes=2_000_000):
    session = requests.Session()
    session.trust_env = False
    current = _validate_public_url(url)
    headers = {
        "User-Agent": UA,
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.6",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
    }
    for _ in range(max_redirects + 1):
        r = session.get(current, headers=headers, timeout=(4, 9), allow_redirects=False, stream=True)
        if r.is_redirect or r.is_permanent_redirect:
            location = r.headers.get("location")
            r.close()
            if not location:
                raise ValueError("Redirecionamento sem destino")
            current = _validate_public_url(urljoin(current, location))
            continue
        ctype = (r.headers.get("content-type") or "").lower()
        chunks = []
        size = 0
        for chunk in r.iter_content(chunk_size=65536):
            if not chunk:
                continue
            size += len(chunk)
            if size > max_bytes:
                chunks.append(chunk[: max(0, max_bytes - (size - len(chunk)))])
                break
            chunks.append(chunk)
        body = b"".join(chunks)
        encoding = r.encoding or "utf-8"
        try:
            text = body.decode(encoding, errors="replace")
        except LookupError:
            text = body.decode("utf-8", errors="replace")
        final = r.url or current
        status = r.status_code
        r.close()
        return {"url": final, "status": status, "content_type": ctype, "text": text}
    raise ValueError("Muitos redirecionamentos")

def _contains_any(blob, words):
    return any(w in blob for w in words)


def _detect_provider(blob):
    for name, signatures in BOOKING_PROVIDERS.items():
        if any(sig in blob for sig in signatures):
            return name
    return None


def _detect_tech(blob):
    found = []
    for name, signatures in TECH_SIGNATURES.items():
        if any(sig in blob for sig in signatures):
            found.append(name)
    return ", ".join(found[:4]) if found else None


def _manual_booking(text):
    text = (text or "").lower()
    for channel, patterns in MANUAL_BOOKING_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I | re.S)
            if match:
                start = max(0, match.start() - 80)
                end = min(len(text), match.end() + 80)
                evidence = " ".join(text[start:end].split())
                return True, channel, evidence[:260]
    return False, None, None


def _quality_score(result):
    if not result.get("site_functional"):
        return 0
    score = 35
    if result.get("site_https"):
        score += 10
    if result.get("site_mobile"):
        score += 15
    if result.get("site_response_ms") is not None:
        ms = result["site_response_ms"]
        if ms <= 1200:
            score += 12
        elif ms <= 2500:
            score += 8
        elif ms <= 5000:
            score += 3
    if result.get("site_title"):
        score += 5
    if result.get("site_description"):
        score += 5
    if result.get("has_contact_form") or result.get("has_whatsapp"):
        score += 8
    if result.get("has_catalog"):
        score += 5
    if result.get("has_booking"):
        score += 5
    return min(100, score)


def _presence_completeness(result):
    checks = [
        bool(result.get("website")),
        result.get("site_functional") is True,
        result.get("site_mobile") is True,
        bool(result.get("has_whatsapp")),
        bool(result.get("has_instagram")),
        bool(result.get("has_facebook")),
        bool(result.get("has_catalog")),
        bool(result.get("has_booking")),
        bool(result.get("has_contact_form")),
        bool(result.get("emails_found")),
    ]
    return int(round(sum(checks) / len(checks) * 100))


def analyze_site(url: str, use_cache=True, cache_days=14):
    url = normalize_url(url)
    result = {
        "website": url, "site_functional": False, "site_status": None, "site_response_ms": None,
        "site_https": None, "site_mobile": None, "has_booking": False, "has_catalog": False,
        "has_whatsapp": False, "has_contact_form": False, "has_instagram": False, "has_facebook": False,
        "instagram_url": None, "facebook_url": None, "whatsapp_url": None, "emails_found": [],
        "site_title": None, "site_description": None, "site_quality_score": 0, "booking_provider": None,
        "competitor_detected": False, "competitor_name": None, "manual_booking_detected": False,
        "manual_booking_channel": None, "manual_booking_evidence": None, "tech_stack": None,
        "presence_completeness_score": 0, "site_error": None, "analysis_version": ANALYSIS_VERSION,
        "last_analyzed_at": datetime.now(timezone.utc).isoformat(), "analysis_cached": False,
        "decision_maker_candidates": [], "company_size_estimate": None,
        "has_structured_data": False, "has_local_business_schema": False, "robots_noindex": False,
        "ai_search_readiness_score": 0,
    }
    if not url:
        return result
    try:
        _validate_public_url(url)
    except Exception as exc:
        result["site_error"] = f"Bloqueado: {str(exc)[:220]}"
        return result

    if use_cache:
        cached = get_cached_site_analysis(url, max_age_days=cache_days)
        if cached and cached.get("analysis_version") == ANALYSIS_VERSION:
            cached["analysis_cached"] = True
            return cached

    result["site_https"] = urlparse(url).scheme.lower() == "https"
    start = time.perf_counter()
    try:
        fetched = _safe_fetch_html(url)
        final_url = _validate_public_url(fetched["url"])
        result["website"] = final_url
        result["site_response_ms"] = int((time.perf_counter() - start) * 1000)
        result["site_status"] = fetched["status"]
        result["site_https"] = final_url.lower().startswith("https://")
        ctype = fetched["content_type"]
        html = fetched["text"][:2_000_000]
        result["site_functional"] = 200 <= fetched["status"] < 400 and ("html" in ctype or "<html" in html.lower())
        if not html:
            result["site_quality_score"] = _quality_score(result)
            result["presence_completeness_score"] = _presence_completeness(result)
            set_cached_site_analysis(url, result)
            return result

        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else None
        desc_tag = soup.find("meta", attrs={"name": re.compile("description", re.I)})
        desc = (desc_tag.get("content") or "").strip() if desc_tag else None
        result["site_title"] = title[:300] if title else None
        result["site_description"] = desc[:500] if desc else None

        # Sinais técnicos úteis para relatórios de prontidão para busca com IA.
        json_ld = soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)})
        result["has_structured_data"] = bool(json_ld)
        schema_blob = " ".join(tag.get_text(" ", strip=True) for tag in json_ld).lower()
        result["has_local_business_schema"] = any(token in schema_blob for token in (
            '"@type":"localbusiness"', '"@type": "localbusiness"', 'localbusiness', 'organization', 'store'
        ))
        robots_meta = soup.find("meta", attrs={"name": re.compile(r"robots", re.I)})
        robots_content = (robots_meta.get("content") or "").lower() if robots_meta else ""
        result["robots_noindex"] = "noindex" in robots_content

        raw_page_text = " ".join(soup.stripped_strings)[:600_000]
        page_text = raw_page_text.lower()
        result["decision_maker_candidates"] = _decision_maker_candidates(raw_page_text)
        result["company_size_estimate"] = _estimate_company_size(raw_page_text)
        viewport = soup.find("meta", attrs={"name": re.compile("viewport", re.I)})
        result["site_mobile"] = bool(viewport)

        links, raw_hrefs = [], []
        for a in soup.find_all("a", href=True):
            href = (a.get("href") or "").strip()
            label = " ".join(a.stripped_strings)
            absolute = urljoin(final_url, href)
            raw_hrefs.append(absolute)
            links.append((absolute + " " + label).lower())
        link_blob = " ".join(links)[:600_000]
        html_lower = html.lower()[:1_500_000]
        combined = page_text + " " + link_blob + " " + html_lower

        provider = _detect_provider(combined)
        manual, manual_channel, manual_evidence = _manual_booking(page_text + " " + link_blob)
        result["booking_provider"] = provider
        result["has_booking"] = bool(provider) or (_contains_any(combined, BOOKING_WORDS) and not manual)
        result["competitor_detected"] = bool(provider)
        result["competitor_name"] = provider
        result["manual_booking_detected"] = bool(manual and not provider)
        result["manual_booking_channel"] = manual_channel if result["manual_booking_detected"] else None
        result["manual_booking_evidence"] = manual_evidence if result["manual_booking_detected"] else None
        result["has_catalog"] = _contains_any(combined, CATALOG_WORDS)

        for href in raw_hrefs:
            low = href.lower()
            if not result["whatsapp_url"] and any(x in low for x in ("wa.me/", "api.whatsapp.com", "whatsapp://", "whatsapp.com/send")):
                result["whatsapp_url"] = href
            if not result["instagram_url"] and "instagram.com" in low:
                result["instagram_url"] = href
            if not result["facebook_url"] and ("facebook.com" in low or "fb.com" in low):
                result["facebook_url"] = href
        result["has_whatsapp"] = bool(result["whatsapp_url"])
        result["has_instagram"] = bool(result["instagram_url"])
        result["has_facebook"] = bool(result["facebook_url"])
        result["emails_found"] = sorted(set(EMAIL_RE.findall(html)))[:8]

        forms = soup.find_all("form")
        has_form_controls = any(f.find(["input", "textarea", "button"]) for f in forms)
        result["has_contact_form"] = bool(has_form_controls and (_contains_any(page_text, CONTACT_WORDS) or len(forms) > 0))
        result["tech_stack"] = _detect_tech(combined)
        result["site_quality_score"] = _quality_score(result)
        result["presence_completeness_score"] = _presence_completeness(result)
        readiness = 0
        if result.get("site_functional"): readiness += 35
        if result.get("site_mobile"): readiness += 10
        if result.get("site_https"): readiness += 10
        if result.get("site_title"): readiness += 8
        if result.get("site_description"): readiness += 7
        if result.get("has_structured_data"): readiness += 12
        if result.get("has_local_business_schema"): readiness += 10
        if not result.get("robots_noindex"): readiness += 8
        result["ai_search_readiness_score"] = min(100, readiness)
        set_cached_site_analysis(url, result)
        return result
    except Exception as exc:
        result["site_response_ms"] = int((time.perf_counter() - start) * 1000)
        result["site_error"] = str(exc)[:240]
        result["site_quality_score"] = 0
        result["presence_completeness_score"] = _presence_completeness(result)
        # Não cacheia bloqueios/erros transitórios agressivamente.
        if "SSRF" not in str(exc) and "privado" not in str(exc).lower():
            set_cached_site_analysis(url, result)
        return result

def _no_site_result(row):
    return {
        "site_functional": False,
        "site_status": None,
        "site_response_ms": None,
        "site_https": None,
        "site_mobile": None,
        "has_booking": False,
        "has_catalog": False,
        "has_whatsapp": bool(row.get("has_whatsapp")),
        "has_contact_form": False,
        "has_instagram": False,
        "has_facebook": False,
        "instagram_url": None,
        "facebook_url": None,
        "whatsapp_url": None,
        "emails_found": [],
        "site_title": None,
        "site_description": None,
        "site_quality_score": 0,
        "booking_provider": None,
        "competitor_detected": False,
        "competitor_name": None,
        "manual_booking_detected": False,
        "manual_booking_channel": None,
        "manual_booking_evidence": None,
        "tech_stack": None,
        "presence_completeness_score": 0,
        "analysis_version": ANALYSIS_VERSION,
        "last_analyzed_at": datetime.now(timezone.utc).isoformat(),
        "analysis_cached": False,
        "decision_maker_candidates": [],
        "company_size_estimate": None,
    }


def analyze_many(rows, max_workers=8, progress_cb=None, force_refresh=False, cache_days=14):
    with ThreadPoolExecutor(max_workers=max(1, min(int(max_workers), 12))) as pool:
        futures = {}
        for i, row in enumerate(rows):
            if row.get("analysis_cached") and not force_refresh:
                continue
            if row.get("website"):
                futures[pool.submit(analyze_site, row["website"], not force_refresh, cache_days)] = i
            else:
                row.update(_no_site_result(row))
        total = len(futures)
        done = 0
        for fut in as_completed(futures):
            idx = futures[fut]
            rows[idx].update(fut.result())
            done += 1
            if progress_cb:
                progress_cb(done, total)
        if progress_cb and total == 0:
            progress_cb(1, 1)
    return rows
