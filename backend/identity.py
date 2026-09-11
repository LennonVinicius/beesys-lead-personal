import hashlib
import re
from urllib.parse import urlparse


def norm_text(value: str | None) -> str:
    text=(value or '').strip().lower()
    text=re.sub(r'[^a-z0-9à-ÿ]+',' ',text)
    return re.sub(r'\s+',' ',text).strip()


def norm_phone(value: str | None) -> str:
    digits=re.sub(r'\D+','',value or '')
    if digits.startswith('55') and len(digits) >= 12:
        digits=digits[2:]
    return digits[-11:]


def norm_domain(value: str | None) -> str:
    if not value:
        return ''
    raw=value.strip()
    if not re.match(r'^https?://',raw,re.I):
        raw='https://'+raw
    try:
        host=(urlparse(raw).hostname or '').lower()
    except Exception:
        return ''
    if host.startswith('www.'):
        host=host[4:]
    return host


def coordinate_bucket(lat, lon, precision=4) -> str:
    try:
        return f'{float(lat):.{precision}f},{float(lon):.{precision}f}'
    except Exception:
        return ''


def identity_material(row: dict) -> str:
    """Produces a provider-independent identity string.

    Strong signals (domain/phone) win. Otherwise combine normalized name +
    coarse coordinates/address so Geoapify/OSM/Foursquare can converge on the
    same local business without requiring identical provider IDs.
    """
    domain=norm_domain(row.get('website'))
    phone=norm_phone(row.get('phone') or row.get('contact_phone'))
    if domain:
        return f'domain:{domain}'
    if phone and len(phone) >= 10:
        return f'phone:{phone}'
    name=norm_text(row.get('name'))
    address=norm_text(row.get('address'))
    bucket=coordinate_bucket(row.get('lat'),row.get('lon'),4)
    if name and bucket:
        return f'namegeo:{name}|{bucket}'
    if name and address:
        return f'nameaddr:{name}|{address[:80]}'
    return f'fallback:{name}|{bucket}|{address[:80]}'


def identity_key(row: dict) -> str:
    material=identity_material(row)
    return 'biz:'+hashlib.sha256(material.encode('utf-8')).hexdigest()[:28]


def merge_source_keys(*values) -> list[str]:
    out=[]
    for value in values:
        if not value:
            continue
        if isinstance(value,str):
            vals=[value]
        else:
            vals=list(value)
        for item in vals:
            item=str(item).strip()
            if item and item not in out:
                out.append(item)
    return out
