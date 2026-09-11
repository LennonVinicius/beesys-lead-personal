import hashlib
import hmac
import ipaddress
import json
import socket
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

from db import _conn, _execute, list_webhooks


def _now():
    return datetime.now(timezone.utc).isoformat()


def validate_webhook_url(url: str) -> str:
    p=urlparse((url or '').strip())
    if p.scheme!='https' or not p.hostname:
        raise ValueError('Webhook deve usar uma URL HTTPS pública')
    host=p.hostname.lower()
    if host in {'localhost','127.0.0.1','::1'} or host.endswith('.local'):
        raise ValueError('Host local não é permitido')
    try:
        infos=socket.getaddrinfo(host,p.port or 443,type=socket.SOCK_STREAM)
        for info in infos:
            ip=ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                raise ValueError('Webhook deve apontar para um endereço público')
    except socket.gaierror:
        raise ValueError('Não foi possível resolver o host do webhook')
    return url.strip()


def _delivery_row(webhook_id,event,payload):
    now=_now()
    with _conn() as conn:
        if 'psycopg' in conn.__class__.__module__:
            row=_execute(conn,"INSERT INTO webhook_deliveries(webhook_id,event_name,payload_json,status,attempts,created_at) VALUES(?,?,?,'PENDING',0,?) RETURNING id",(webhook_id,event,json.dumps(payload,ensure_ascii=False,default=str),now)).fetchone();did=row['id']
        else:
            cur=_execute(conn,"INSERT INTO webhook_deliveries(webhook_id,event_name,payload_json,status,attempts,created_at) VALUES(?,?,?,'PENDING',0,?)",(webhook_id,event,json.dumps(payload,ensure_ascii=False,default=str),now));did=cur.lastrowid
        conn.commit()
    return int(did)


def deliver_one(webhook: dict,event: str,payload: dict):
    delivery_id=_delivery_row(webhook['id'],event,payload)
    body=json.dumps({'event':event,'occurred_at':_now(),'data':payload},ensure_ascii=False,default=str,separators=(',',':')).encode('utf-8')
    headers={'Content-Type':'application/json','User-Agent':'BeeSys-Lead-Search/2.1'}
    secret=webhook.get('secret')
    if secret:
        headers['X-BeeSys-Signature']='sha256='+hmac.new(secret.encode(),body,hashlib.sha256).hexdigest()
    try:
        validate_webhook_url(webhook['url'])
        r=requests.post(webhook['url'],data=body,headers=headers,timeout=8,allow_redirects=False)
        ok=200 <= r.status_code < 300
        with _conn() as conn:
            _execute(conn,"UPDATE webhook_deliveries SET status=?,http_status=?,attempts=attempts+1,error=?,delivered_at=? WHERE id=?",('DELIVERED' if ok else 'FAILED',r.status_code,None if ok else f'HTTP {r.status_code}',_now() if ok else None,delivery_id));conn.commit()
        return ok
    except Exception as exc:
        with _conn() as conn:
            _execute(conn,"UPDATE webhook_deliveries SET status='FAILED',attempts=attempts+1,error=? WHERE id=?",(str(exc)[:500],delivery_id));conn.commit()
        return False


def dispatch_event(event: str,payload: dict):
    with _conn() as conn:
        rows=_execute(conn,"SELECT * FROM webhook_subscriptions WHERE active=1").fetchall()
    matched=[]
    for raw in rows:
        wh=dict(raw)
        try:events=json.loads(wh.get('events_json') or '[]')
        except Exception:events=[]
        if event not in events and '*' not in events:continue
        matched.append(wh)
    return [deliver_one(wh,event,payload) for wh in matched]


def list_deliveries(limit=100):
    with _conn() as conn:rows=_execute(conn,"SELECT d.*,w.name webhook_name FROM webhook_deliveries d JOIN webhook_subscriptions w ON w.id=d.webhook_id ORDER BY d.created_at DESC LIMIT ?",(int(limit),)).fetchall()
    return [dict(r) for r in rows]
