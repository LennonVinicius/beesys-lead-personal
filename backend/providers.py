import math
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from typing import Iterable
from urllib.parse import urlparse

import requests

UA = "BeeSysLeadSearch/0.2 (+local lead research app)"
NOMINATIM = "https://nominatim.openstreetmap.org"
OVERPASS_SERVERS = [
    # Instâncias públicas globais. O código tenta a próxima quando houver
    # timeout/429/5xx. Overpass é apenas fallback/best-effort no modo automático.
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]


class ProviderTemporaryError(RuntimeError):
    """Falha temporária de um provedor externo; a aplicação pode usar fallback."""


def _request(method, url, attempts=3, **kwargs):
    last = None
    for attempt in range(max(1, int(attempts))):
        try:
            r = requests.request(method, url, **kwargs)
            if r.status_code in {429, 500, 502, 503, 504} and attempt < attempts - 1:
                retry_after = r.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 0.8 * (2 ** attempt)
                except Exception:
                    delay = 0.8 * (2 ** attempt)
                time.sleep(min(delay, 6))
                continue
            r.raise_for_status()
            return r
        except Exception as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(min(0.8 * (2 ** attempt), 6))
    raise last


def geocode_place(query: str):
    r = _request("GET",
        f"{NOMINATIM}/search",
        params={"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "br"},
        headers={"User-Agent": UA},
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    if not data:
        return None
    return {"lat": float(data[0]["lat"]), "lon": float(data[0]["lon"]), "display_name": data[0].get("display_name", query)}


def _osm_category(tags: dict):
    for key in ("shop", "amenity", "healthcare", "office", "craft", "tourism", "leisure"):
        if tags.get(key):
            return f"{key}:{tags[key]}"
    return "establishment"


def search_osm(
    lat: float,
    lon: float,
    radius_m: int,
    max_results: int = 1000,
    request_timeout: int = 35,
):
    """Busca estabelecimentos no OpenStreetMap via Overpass.

    As instâncias públicas do Overpass podem ficar sobrecarregadas. Por isso:
    - a consulta evita `amenity=*` genérico, que produz respostas enormes;
    - tenta mais de uma instância;
    - 429/5xx/timeouts são tratados como falha temporária;
    - o chamador pode fazer fallback para Geoapify sem derrubar o Streamlit.
    """
    radius_m = max(50, int(radius_m))
    max_results = max(1, int(max_results))

    # Mantemos categorias comerciais/serviços mais úteis para prospecção. A
    # antiga consulta a todo `amenity=*` era pesada e aumentava muito os 504.
    query = f"""
    [out:json][timeout:28];
    (
      nwr(around:{radius_m},{lat},{lon})["name"]["shop"];
      nwr(around:{radius_m},{lat},{lon})["name"]["office"];
      nwr(around:{radius_m},{lat},{lon})["name"]["craft"];
      nwr(around:{radius_m},{lat},{lon})["name"]["healthcare"];
      nwr(around:{radius_m},{lat},{lon})["name"]["amenity"~"restaurant|cafe|fast_food|bar|pub|pharmacy|clinic|doctors|dentist|veterinary|bank|marketplace|car_rental|car_wash|fuel|cinema|nightclub"];
      nwr(around:{radius_m},{lat},{lon})["name"]["tourism"~"hotel|guest_house|hostel|motel"];
      nwr(around:{radius_m},{lat},{lon})["name"]["leisure"~"fitness_centre|sports_centre"];
    );
    out center tags;
    """

    errors = []
    data = None
    headers = {
        "User-Agent": UA,
        "Accept": "application/json",
    }

    for endpoint in OVERPASS_SERVERS:
        try:
            # Uma tentativa por servidor é melhor do que repetir várias vezes no
            # mesmo servidor congestionado. Se falhar, partimos para o próximo.
            r = requests.post(
                endpoint,
                data={"data": query},
                headers=headers,
                timeout=(8, max(15, int(request_timeout))),
            )
            if r.status_code in {429, 500, 502, 503, 504}:
                errors.append(f"{endpoint}: HTTP {r.status_code}")
                continue
            r.raise_for_status()
            payload = r.json()
            if not isinstance(payload, dict):
                errors.append(f"{endpoint}: resposta inválida")
                continue
            data = payload
            break
        except requests.Timeout:
            errors.append(f"{endpoint}: timeout")
        except requests.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            errors.append(f"{endpoint}: HTTP {status}" if status else f"{endpoint}: {type(exc).__name__}")
        except ValueError:
            errors.append(f"{endpoint}: JSON inválido")
        except Exception as exc:
            errors.append(f"{endpoint}: {type(exc).__name__}")

    if data is None:
        detail = "; ".join(errors[-3:]) or "instâncias públicas indisponíveis"
        raise ProviderTemporaryError(
            "OpenStreetMap/Overpass está temporariamente indisponível. "
            f"Detalhes: {detail}"
        )

    excluded_amenities = {
        "bench", "parking", "parking_entrance", "bicycle_parking", "waste_basket", "drinking_water",
        "toilets", "post_box", "telephone", "atm", "recycling", "charging_station", "shelter", "clock",
        "fountain", "fire_station", "police", "townhall", "courthouse", "place_of_worship", "community_centre",
    }
    rows = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        if tags.get("amenity") in excluded_amenities and not any(tags.get(k) for k in ("shop", "office", "craft")):
            continue
        name = tags.get("name")
        if not name:
            continue
        if el.get("type") == "node":
            plat, plon = el.get("lat"), el.get("lon")
        else:
            center = el.get("center") or {}
            plat, plon = center.get("lat"), center.get("lon")
        if plat is None or plon is None:
            continue
        if haversine_m(lat, lon, float(plat), float(plon)) > radius_m * 1.02:
            continue
        source_id = f"{el.get('type')}:{el.get('id')}"
        website = tags.get("website") or tags.get("contact:website") or tags.get("url")
        phone = tags.get("phone") or tags.get("contact:phone") or tags.get("mobile") or tags.get("contact:mobile")
        social_blob = " ".join(str(tags.get(k) or "") for k in ("contact:instagram", "contact:facebook", "contact:whatsapp"))
        rows.append({
            "business_key": f"osm:{source_id}", "provider": "OpenStreetMap", "source_id": source_id,
            "name": name, "address": _format_osm_address(tags),
            "city_name": tags.get("addr:city") or tags.get("addr:municipality"),
            "state_name": tags.get("addr:state"),
            "district_name": tags.get("addr:suburb") or tags.get("addr:district") or tags.get("addr:neighbourhood"),
            "lat": float(plat), "lon": float(plon),
            "category": _osm_category(tags), "phone": phone, "website": website, "rating": None, "reviews": None,
            "maps_url": f"https://www.openstreetmap.org/{el.get('type')}/{el.get('id')}",
            "open_now": None, "opening_hours_text": tags.get("opening_hours"),
            "has_whatsapp": bool(tags.get("contact:whatsapp") or "whatsapp" in social_blob.lower()),
            "raw": el,
        })

    return dedupe_businesses(rows)[:max_results]


def _format_osm_address(tags):
    parts = []
    street = tags.get("addr:street")
    number = tags.get("addr:housenumber")
    if street:
        parts.append(f"{street}, {number}" if number else street)
    for key in ("addr:suburb", "addr:city", "addr:state"):
        if tags.get(key):
            parts.append(tags[key])
    return " - ".join(parts)


def search_google(lat: float, lon: float, radius_m: int, api_key: str, terms: Iterable[str], pages_per_term=3):
    endpoint = "https://places.googleapis.com/v1/places:searchText"
    field_mask = ",".join([
        "places.id", "places.displayName", "places.formattedAddress", "places.location", "places.websiteUri",
        "places.rating", "places.userRatingCount", "places.nationalPhoneNumber", "places.primaryTypeDisplayName",
        "places.types", "places.googleMapsUri", "places.businessStatus", "places.regularOpeningHours",
        "places.currentOpeningHours", "nextPageToken",
    ])
    headers = {"Content-Type": "application/json", "X-Goog-Api-Key": api_key, "X-Goog-FieldMask": field_mask}
    by_id = {}
    for term in terms:
        term = term.strip()
        if not term:
            continue
        token = None
        for _ in range(max(1, min(int(pages_per_term), 3))):
            body = {
                "textQuery": term, "languageCode": "pt-BR", "regionCode": "BR", "pageSize": 20,
                "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": float(radius_m)}},
            }
            if token:
                body["pageToken"] = token
            r = _request("POST", endpoint, json=body, headers=headers, timeout=30)
            data = r.json()
            for p in data.get("places", []):
                loc = p.get("location") or {}
                plat, plon = loc.get("latitude"), loc.get("longitude")
                if plat is None or plon is None or haversine_m(lat, lon, float(plat), float(plon)) > radius_m * 1.02:
                    continue
                pid = p.get("id")
                if not pid:
                    continue
                name_obj = p.get("displayName") or {}
                cat_obj = p.get("primaryTypeDisplayName") or {}
                current_hours = p.get("currentOpeningHours") or {}
                regular_hours = p.get("regularOpeningHours") or {}
                hours_text = current_hours.get("weekdayDescriptions") or regular_hours.get("weekdayDescriptions") or []
                by_id[pid] = {
                    "business_key": f"google:{pid}", "provider": "Google Places", "source_id": pid,
                    "name": name_obj.get("text") or pid, "address": p.get("formattedAddress"),
                    "lat": float(plat), "lon": float(plon), "category": cat_obj.get("text") or ", ".join((p.get("types") or [])[:3]),
                    "phone": p.get("nationalPhoneNumber"), "website": p.get("websiteUri"), "rating": p.get("rating"),
                    "reviews": p.get("userRatingCount"), "maps_url": p.get("googleMapsUri"),
                    "business_status": p.get("businessStatus"), "open_now": current_hours.get("openNow"),
                    "opening_hours_text": " | ".join(hours_text) if hours_text else None, "raw": p,
                }
            token = data.get("nextPageToken")
            if not token:
                break
            time.sleep(1.0)
    return dedupe_businesses(list(by_id.values()))


def _norm_text(value):
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _domain(url):
    if not url:
        return None
    try:
        host = urlparse(url if "://" in url else "https://" + url).netloc.lower()
        return host.removeprefix("www.") or None
    except Exception:
        return None


def _phone(value):
    digits = re.sub(r"\D", "", value or "")
    return digits[-10:] if len(digits) >= 10 else digits or None


def dedupe_businesses(rows):
    """Remove duplicatas fortes por domínio/telefone e duplicatas próximas por nome."""
    kept = []
    by_domain = {}
    by_phone = {}
    for row in rows:
        dom, ph = _domain(row.get("website")), _phone(row.get("phone"))
        duplicate_idx = by_domain.get(dom) if dom else None
        if duplicate_idx is None and ph:
            duplicate_idx = by_phone.get(ph)
        if duplicate_idx is None:
            n1 = _norm_text(row.get("name"))
            for i, old in enumerate(kept):
                if haversine_m(row["lat"], row["lon"], old["lat"], old["lon"]) <= 70:
                    n2 = _norm_text(old.get("name"))
                    if n1 and n2 and SequenceMatcher(None, n1, n2).ratio() >= 0.88:
                        duplicate_idx = i
                        break
        if duplicate_idx is not None:
            old = kept[duplicate_idx]
            # Mantém o registro mais rico.
            for key in ("website", "phone", "address", "rating", "reviews", "maps_url", "opening_hours_text", "open_now"):
                if old.get(key) in (None, "", []) and row.get(key) not in (None, "", []):
                    old[key] = row[key]
            continue
        idx = len(kept)
        kept.append(row)
        if dom:
            by_domain[dom] = idx
        if ph:
            by_phone[ph] = idx
    return kept


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))

GEOAPIFY_PLACES_URL = "https://api.geoapify.com/v2/places"
FOURSQUARE_SEARCH_URL = "https://places-api.foursquare.com/places/search"

# Categorias amplas para prospecção local. O Geoapify aceita categorias-pai.
GEOAPIFY_DEFAULT_CATEGORIES = [
    "commercial",
    "catering",
    "healthcare",
    "service",
    "accommodation",
    "leisure.fitness_centre",
    "education",
]


def _first_nonempty(obj, keys):
    for key in keys:
        value = obj.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def search_geoapify(lat: float, lon: float, radius_m: int, api_key: str, max_results: int = 500, categories=None):
    if not api_key:
        raise ValueError("GEOAPIFY_API_KEY ausente")
    categories = categories or GEOAPIFY_DEFAULT_CATEGORIES
    per_category = max(20, min(100, int(max_results / max(len(categories), 1)) + 10))

    def fetch_category(category):
        params = {
            "categories": category,
            "filter": f"circle:{lon},{lat},{int(radius_m)}",
            "bias": f"proximity:{lon},{lat}",
            "limit": per_category,
            "lang": "pt",
            "apiKey": api_key,
        }
        r = _request("GET", GEOAPIFY_PLACES_URL, params=params, headers={"User-Agent": UA}, timeout=35)
        return r.json().get("features") or []

    features = []
    with ThreadPoolExecutor(max_workers=min(3, len(categories))) as pool:
        futures = {pool.submit(fetch_category, cat): cat for cat in categories}
        for fut in as_completed(futures):
            try:
                features.extend(fut.result())
            except Exception:
                # Uma categoria não derruba a busca inteira; outras fontes/categorias ainda podem retornar leads.
                continue

    rows = []
    for feature in features:
        props = feature.get("properties") or {}
        geom = feature.get("geometry") or {}
        coords = geom.get("coordinates") or []
        plon = props.get("lon") if props.get("lon") is not None else (coords[0] if len(coords) >= 2 else None)
        plat = props.get("lat") if props.get("lat") is not None else (coords[1] if len(coords) >= 2 else None)
        if plat is None or plon is None:
            continue
        name = props.get("name") or props.get("address_line1")
        if not name:
            continue
        place_id = props.get("place_id") or props.get("datasource", {}).get("raw", {}).get("osm_id") or f"{plat}:{plon}:{name}"
        contact = props.get("contact") or {}
        datasource_raw = (props.get("datasource") or {}).get("raw") or {}
        website = _first_nonempty(contact, ["website"]) or _first_nonempty(datasource_raw, ["website", "contact:website", "url"])
        phone = _first_nonempty(contact, ["phone"]) or _first_nonempty(datasource_raw, ["phone", "contact:phone", "mobile", "contact:mobile"])
        categories_value = props.get("categories") or []
        rows.append({
            "business_key": f"geoapify:{place_id}", "provider": "Geoapify", "source_id": str(place_id),
            "name": name, "address": props.get("formatted") or props.get("address_line2") or props.get("street"),
            "city_name": props.get("city") or props.get("municipality") or props.get("county"),
            "state_name": props.get("state"),
            "district_name": props.get("suburb") or props.get("district") or props.get("city_district"),
            "lat": float(plat), "lon": float(plon),
            "category": ", ".join(categories_value[:3]) if isinstance(categories_value, list) else str(categories_value),
            "phone": phone, "website": website, "rating": None, "reviews": None,
            "maps_url": f"https://www.openstreetmap.org/?mlat={plat}&mlon={plon}#map=18/{plat}/{plon}",
            "open_now": None, "opening_hours_text": _first_nonempty(datasource_raw, ["opening_hours"]),
            "data_confidence": 85, "source_notes": "Geoapify Places", "raw": feature,
        })
    return dedupe_businesses(rows)[: int(max_results)]


def search_foursquare(lat: float, lon: float, radius_m: int, service_key: str, terms=None, max_results: int = 200):
    if not service_key:
        raise ValueError("FOURSQUARE_API_KEY ausente")
    terms = [t.strip() for t in (terms or ["barbearia", "salão", "clínica", "restaurante", "loja", "academia", "pet shop"]) if t.strip()]
    headers = {
        "Authorization": f"Bearer {service_key}",
        "Accept": "application/json",
        "X-Places-Api-Version": "2025-06-17",
    }
    rows = []
    per_term = min(50, max(10, int(max_results / max(len(terms), 1)) + 5))
    for term in terms:
        r = _request("GET",
            FOURSQUARE_SEARCH_URL,
            params={"query": term, "ll": f"{lat},{lon}", "radius": min(int(radius_m), 100000), "limit": per_term, "sort": "DISTANCE"},
            headers=headers,
            timeout=35,
        )
        data = r.json()
        results = data.get("results") or data.get("places") or []
        for p in results:
            pid = p.get("fsq_place_id") or p.get("fsq_id") or p.get("id")
            name = p.get("name")
            if not pid or not name:
                continue
            loc = p.get("location") or {}
            geocodes = p.get("geocodes") or {}
            main_geo = geocodes.get("main") or {}
            plat = p.get("latitude") if p.get("latitude") is not None else main_geo.get("latitude")
            plon = p.get("longitude") if p.get("longitude") is not None else main_geo.get("longitude")
            if plat is None or plon is None:
                continue
            if haversine_m(lat, lon, float(plat), float(plon)) > radius_m * 1.05:
                continue
            categories = p.get("categories") or []
            cat_names = [c.get("name") for c in categories if isinstance(c, dict) and c.get("name")]
            address = loc.get("formatted_address") or ", ".join(x for x in [loc.get("address"), loc.get("locality"), loc.get("region")] if x)
            rows.append({
                "business_key": f"foursquare:{pid}",
                "provider": "Foursquare",
                "source_id": str(pid),
                "name": name,
                "address": address,
                "city_name": loc.get("locality"),
                "state_name": loc.get("region"),
                "district_name": (loc.get("neighborhood") or [None])[0] if isinstance(loc.get("neighborhood"), list) else loc.get("neighborhood"),
                "lat": float(plat),
                "lon": float(plon),
                "category": ", ".join(cat_names[:3]),
                "phone": p.get("tel") or p.get("telephone"),
                "website": p.get("website"),
                "rating": p.get("rating"),
                "reviews": p.get("stats", {}).get("total_ratings") if isinstance(p.get("stats"), dict) else None,
                "maps_url": f"https://foursquare.com/v/{pid}",
                "open_now": (p.get("hours") or {}).get("open_now") if isinstance(p.get("hours"), dict) else None,
                "opening_hours_text": None,
                "data_confidence": 80,
                "source_notes": "Foursquare Places",
                "raw": p,
            })
    return dedupe_businesses(rows)[: int(max_results)]


def merge_provider_rows(*groups):
    """Une fontes diferentes e prefere dados mais ricos sem perder a origem primária."""
    flat = []
    for group in groups:
        flat.extend(group or [])
    return dedupe_businesses(flat)


def geocode_geoapify(query: str, api_key: str):
    if not api_key:
        return geocode_place(query)
    r = _request(
        "GET",
        "https://api.geoapify.com/v1/geocode/search",
        params={"text": query, "format": "json", "limit": 1, "filter": "countrycode:br", "apiKey": api_key},
        headers={"User-Agent": UA},
        timeout=20,
    )
    r.raise_for_status()
    data = r.json().get("results") or []
    if not data:
        return None
    first = data[0]
    return {
        "lat": float(first["lat"]),
        "lon": float(first["lon"]),
        "display_name": first.get("formatted") or query,
        "city_name": first.get("city") or first.get("municipality") or first.get("county"),
        "state_name": first.get("state"),
        "district_name": first.get("suburb") or first.get("district") or first.get("city_district"),
    }
