from datetime import datetime, timedelta

import requests

from providers import haversine_m

DAY_MAP={0:'Mo',1:'Tu',2:'We',3:'Th',4:'Fr',5:'Sa',6:'Su'}

def _minutes(hhmm):
    try:
        h,m=hhmm.split(':',1);return int(h)*60+int(m)
    except Exception:return None

def likely_open_at(opening_hours_text, dt):
    """Best-effort parser for common OSM opening_hours strings.

    Returns True/False only when a simple rule can be interpreted; otherwise
    returns None so the planner never invents certainty.
    """
    text=(opening_hours_text or '').strip()
    if not text:return None
    low=text.lower()
    if '24/7' in low:return True
    day=DAY_MAP.get(dt.weekday()); nowm=dt.hour*60+dt.minute
    for chunk in text.split(';'):
        chunk=chunk.strip()
        if not chunk:continue
        parts=chunk.split()
        if len(parts)<2:continue
        days=' '.join(parts[:-1]);hours=parts[-1]
        day_match=False
        if day in days:day_match=True
        for rng in days.split(','):
            rng=rng.strip()
            if '-' in rng:
                a,b=rng.split('-',1)
                order=['Mo','Tu','We','Th','Fr','Sa','Su']
                if a in order and b in order and day in order:
                    ai,bi,di=order.index(a),order.index(b),order.index(day)
                    if ai<=bi and ai<=di<=bi:day_match=True
                    elif ai>bi and (di>=ai or di<=bi):day_match=True
        if not day_match:continue
        for hrng in hours.split(','):
            if '-' not in hrng:continue
            a,b=hrng.split('-',1);am,bm=_minutes(a),_minutes(b)
            if am is None or bm is None:continue
            if am<=bm and am<=nowm<=bm:return True
            if am>bm and (nowm>=am or nowm<=bm):return True
        return False
    return None

ORS_BASE = "https://api.heigit.org/openrouteservice/v2"


def _haversine_distance_matrix(points):
    n = len(points)
    m = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            d = haversine_m(points[i][0], points[i][1], points[j][0], points[j][1])
            m[i][j] = m[j][i] = d
    return m


def _fallback_duration_matrix(points, profile):
    distances = _haversine_distance_matrix(points)
    # Fator de malha viária + velocidade média urbana conservadora.
    speed_mps = 4.2 if profile == "driving-car" else 1.25
    road_factor = 1.28 if profile == "driving-car" else 1.18
    return [[(d * road_factor) / speed_mps for d in row] for row in distances]


def ors_matrix(points, profile, api_key, metric="duration"):
    coords = [[lon, lat] for lat, lon in points]
    r = requests.post(
        f"{ORS_BASE}/matrix/{profile}",
        json={"locations": coords, "metrics": [metric]},
        headers={"Authorization": api_key, "Content-Type": "application/json"},
        timeout=35,
    )
    r.raise_for_status()
    data = r.json()
    return data.get("durations") if metric == "duration" else data.get("distances")


def build_duration_matrix(points, profile="driving-car", ors_key=None):
    if ors_key:
        try:
            matrix = ors_matrix(points, profile, ors_key, "duration")
            if matrix:
                return matrix, "openrouteservice"
        except Exception:
            pass
    return _fallback_duration_matrix(points, profile), "estimativa local"


def build_matrix(points, profile="driving-car", ors_key=None):
    """Compatibilidade: matriz de duração em segundos."""
    return build_duration_matrix(points, profile, ors_key)


def optimize_order(points, profile="driving-car", ors_key=None, return_to_start=False):
    if len(points) <= 1:
        return [], None
    matrix, _ = build_duration_matrix(points, profile, ors_key)
    remaining = set(range(1, len(points)))
    order, cur = [], 0
    while remaining:
        nxt = min(remaining, key=lambda j: matrix[cur][j] if matrix[cur][j] is not None else 1e12)
        order.append(nxt)
        remaining.remove(nxt)
        cur = nxt
    return order, matrix


def _lead_expected_value(lead, default_mrr=89.90):
    try:
        prob = float(lead.get("conversion_probability") or 0) / 100.0
    except Exception:
        prob = 0.0
    try:
        mrr = float(lead.get("estimated_mrr") or default_mrr)
    except Exception:
        mrr = float(default_mrr)
    return max(0.0, prob * mrr)


def optimize_priority_route(origin, candidates, profile="driving-car", ors_key=None, return_to_start=False,
                            score_weight=0.42, distance_weight=0.22, open_weight=0.10, value_weight=0.26):
    """Ordena equilibrando prioridade de visita, valor esperado, deslocamento e horário."""
    if not candidates:
        return [], None, None
    points = [origin] + [(r["lat"], r["lon"]) for r in candidates]
    matrix, engine = build_duration_matrix(points, profile, ors_key)
    remaining = set(range(1, len(points)))
    order, cur = [], 0
    vals = [v for row in matrix for v in row if v is not None and v > 0 and v < 1e11]
    max_cost = max(vals) if vals else 1.0
    expected_values = [_lead_expected_value(r) for r in candidates]
    max_value = max(expected_values) if expected_values else 1.0
    max_value = max(max_value, 0.01)

    while remaining:
        best, best_utility = None, -1e9
        for idx in remaining:
            lead = candidates[idx - 1]
            priority_norm = max(0.0, min(1.0, float(lead.get("visit_priority_score") or lead.get("score") or 0) / 100.0))
            travel = matrix[cur][idx]
            travel_norm = min(1.0, (travel if travel is not None else max_cost) / max_cost)
            open_norm = 1.0 if lead.get("open_now") is True else (-0.55 if lead.get("open_now") is False else 0.10)
            value_norm = expected_values[idx - 1] / max_value
            status = lead.get("pipeline_status") or "NEW"
            stage_bonus = {"INTERESTED": 0.10, "DEMO": 0.14, "PROPOSAL": 0.16, "PRIORITY": 0.05}.get(status, 0.0)
            utility = (
                score_weight * priority_norm
                + value_weight * value_norm
                - distance_weight * travel_norm
                + open_weight * open_norm
                + stage_bonus
            )
            if utility > best_utility:
                best_utility, best = utility, idx
        order.append(best)
        remaining.remove(best)
        cur = best

    return [candidates[i - 1] for i in order], matrix, engine


def plan_timed_route(origin, candidates, profile="driving-car", ors_key=None, start_time=None,
                     available_minutes=240, visit_minutes=15, max_stops=12, return_to_start=False):
    """
    Planeja rota respeitando janela de tempo. Cada lead recebe horário estimado de chegada,
    deslocamento e valor esperado. A seleção é gulosa por valor/prioridade/custo.
    """
    if not candidates:
        return {"ordered": [], "schedule": [], "matrix_engine": None, "used_minutes": 0}
    ordered_all, matrix, engine = optimize_priority_route(origin, candidates, profile, ors_key, return_to_start)
    index_by_key = {r["business_key"]: i + 1 for i, r in enumerate(candidates)}
    if start_time is None:
        start_time = datetime.now()
    current_time = start_time
    current_idx = 0
    used_seconds = 0.0
    chosen, schedule = [], []

    for lead in ordered_all:
        if len(chosen) >= int(max_stops):
            break
        idx = index_by_key[lead["business_key"]]
        travel_s = matrix[current_idx][idx] if matrix and matrix[current_idx][idx] is not None else 0
        stop_s = float(visit_minutes) * 60
        reserve_return = matrix[idx][0] if return_to_start and matrix and matrix[idx][0] is not None else 0
        if used_seconds + travel_s + stop_s + reserve_return > float(available_minutes) * 60:
            continue
        arrival = current_time + timedelta(seconds=travel_s)
        departure = arrival + timedelta(seconds=stop_s)
        expected_value = _lead_expected_value(lead)
        schedule.append({
            "business_key": lead["business_key"],
            "name": lead.get("name"),
            "arrival": arrival,
            "departure": departure,
            "travel_minutes": round(travel_s / 60, 1),
            "visit_minutes": int(visit_minutes),
            "expected_mrr_value": round(expected_value, 2),
            "conversion_probability": lead.get("conversion_probability"),
            "visit_priority_score": lead.get("visit_priority_score"),
        })
        chosen.append(lead)
        used_seconds += travel_s + stop_s
        current_time = departure
        current_idx = idx

    if return_to_start and chosen:
        back_s = matrix[current_idx][0] if matrix and matrix[current_idx][0] is not None else 0
        used_seconds += back_s
    return {
        "ordered": chosen,
        "schedule": schedule,
        "matrix_engine": engine,
        "used_minutes": round(used_seconds / 60, 1),
    }


def route_geometry(points_ordered, profile="driving-car", ors_key=None):
    if len(points_ordered) < 2:
        return None
    if ors_key:
        try:
            coords = [[lon, lat] for lat, lon in points_ordered]
            r = requests.post(
                f"{ORS_BASE}/directions/{profile}/geojson",
                json={"coordinates": coords, "instructions": False},
                headers={"Authorization": ors_key, "Content-Type": "application/json"},
                timeout=40,
            )
            r.raise_for_status()
            data = r.json()
            feat = data["features"][0]
            summary = (feat.get("properties") or {}).get("summary", {})
            line = [[lat, lon] for lon, lat in feat["geometry"]["coordinates"]]
            return {"line": line, "distance_m": summary.get("distance"), "duration_s": summary.get("duration"), "provider": "openrouteservice"}
        except Exception:
            pass

    coords = ";".join(f"{lon},{lat}" for lat, lon in points_ordered)
    base = "https://routing.openstreetmap.de/routed-foot/route/v1/driving" if profile == "foot-walking" else "https://router.project-osrm.org/route/v1/driving"
    try:
        r = requests.get(f"{base}/{coords}", params={"overview": "full", "geometries": "geojson", "steps": "false"}, timeout=40)
        r.raise_for_status()
        route = r.json()["routes"][0]
        line = [[lat, lon] for lon, lat in route["geometry"]["coordinates"]]
        return {"line": line, "distance_m": route.get("distance"), "duration_s": route.get("duration"), "provider": "OSRM público"}
    except Exception:
        return {"line": [[lat, lon] for lat, lon in points_ordered], "distance_m": None, "duration_s": None, "provider": "linha aproximada"}


def _weights_for_strategy(strategy: str):
    strategy=(strategy or 'balanced').lower()
    if strategy in {'sales','mais-vendas','more-sales'}:
        return dict(score_weight=0.44,distance_weight=0.10,open_weight=0.10,value_weight=0.36)
    if strategy in {'visits','mais-visitas','more-visits'}:
        return dict(score_weight=0.24,distance_weight=0.46,open_weight=0.10,value_weight=0.20)
    if strategy in {'distance','mais-proximos','nearest'}:
        return dict(score_weight=0.15,distance_weight=0.65,open_weight=0.08,value_weight=0.12)
    return dict(score_weight=0.38,distance_weight=0.26,open_weight=0.10,value_weight=0.26)


def geoapify_route_geometry(points_ordered, profile='driving-car', api_key=None):
    if not api_key or len(points_ordered)<2:
        return None
    mode='walk' if profile=='foot-walking' else 'drive'
    try:
        waypoints='|'.join(f'{lat},{lon}' for lat,lon in points_ordered)
        r=requests.get('https://api.geoapify.com/v1/routing',params={
            'waypoints':waypoints,'mode':mode,'type':'balanced','lang':'pt-BR','apiKey':api_key
        },timeout=40)
        r.raise_for_status();data=r.json();feat=(data.get('features') or [None])[0]
        if not feat:return None
        props=feat.get('properties') or {};geom=feat.get('geometry') or {}
        coords=[]
        raw=geom.get('coordinates') or []
        # Geoapify returns MultiLineString for multi-leg routes.
        if geom.get('type')=='MultiLineString':
            for line in raw:
                for lon,lat,*_ in line: coords.append([lat,lon])
        elif geom.get('type')=='LineString':
            for lon,lat,*_ in raw: coords.append([lat,lon])
        distance=props.get('distance');duration=props.get('time')
        return {'line':coords,'distance_m':distance,'duration_s':duration,'provider':'Geoapify'}
    except Exception:
        return None


def plan_route_advanced(origin, candidates, profile='driving-car', ors_key=None, geoapify_key=None,
                        start_time=None, available_minutes=240, visit_minutes=15, max_stops=12,
                        return_to_start=False, strategy='balanced', end=None, fixed_business_keys=None,
                        preserve_order=False):
    """Planejador comercial editável.

    - `strategy` muda o peso entre valor comercial e deslocamento.
    - `fixed_business_keys` garante a inclusão de paradas marcadas como obrigatórias quando couberem.
    - `preserve_order` respeita a ordem enviada pelo usuário para rotas manuais.
    - `end` pode ser diferente da origem; o tempo final é reservado conservadoramente.
    """
    fixed=set(fixed_business_keys or [])
    candidates=[c for c in candidates if c and c.get('business_key')]
    if not candidates:return {'ordered':[],'schedule':[],'matrix_engine':None,'used_minutes':0,'geometry':None}
    if preserve_order:
        ordered_all=candidates
        points=[origin]+[(r['lat'],r['lon']) for r in candidates]
        matrix,engine=build_duration_matrix(points,profile,ors_key)
    else:
        weights=_weights_for_strategy(strategy)
        ordered_all,matrix,engine=optimize_priority_route(origin,candidates,profile,ors_key,return_to_start,**weights)
        if fixed:
            fixed_rows=[x for x in candidates if x['business_key'] in fixed]
            normal=[x for x in ordered_all if x['business_key'] not in fixed]
            # Fixos entram primeiro na seleção; usuário ainda pode reordenar no frontend.
            ordered_all=fixed_rows+normal
    idx={r['business_key']:i+1 for i,r in enumerate(candidates)}
    if start_time is None:start_time=datetime.now()
    current_time=start_time;current_idx=0;used_seconds=0.0;chosen=[];schedule=[];omitted=[]
    end_point=end or (origin if return_to_start else None)
    for lead in ordered_all:
        if len(chosen)>=int(max_stops):
            omitted.append({'business_key':lead['business_key'],'name':lead.get('name'),'reason':'Limite de paradas atingido'})
            continue
        i=idx[lead['business_key']]
        travel_s=matrix[current_idx][i] if matrix and matrix[current_idx][i] is not None else 0
        stop_s=float(visit_minutes)*60
        reserve=0
        if end_point:
            # estimativa local conservadora do último ponto até o destino final
            d=haversine_m(lead['lat'],lead['lon'],end_point[0],end_point[1])
            speed=4.2 if profile=='driving-car' else 1.25; factor=1.28 if profile=='driving-car' else 1.18
            reserve=d*factor/speed
        if used_seconds+travel_s+stop_s+reserve>float(available_minutes)*60:
            if lead['business_key'] in fixed:
                # parada obrigatória: remove limite de seleção, mas sinaliza excedente
                pass
            else:
                omitted.append({'business_key':lead['business_key'],'name':lead.get('name'),'reason':'Não cabe na janela de tempo configurada'})
                continue
        arrival=current_time+timedelta(seconds=travel_s);departure=arrival+timedelta(seconds=stop_s)
        open_at_arrival=likely_open_at(lead.get('opening_hours_text'),arrival)
        if open_at_arrival is False and lead['business_key'] not in fixed:
            omitted.append({'business_key':lead['business_key'],'name':lead.get('name'),'reason':'Provavelmente fechado no horário estimado de chegada'})
            continue
        schedule.append({'business_key':lead['business_key'],'name':lead.get('name'),'arrival':arrival.isoformat(),
            'departure':departure.isoformat(),'travel_minutes':round(travel_s/60,1),'visit_minutes':int(visit_minutes),
            'expected_mrr_value':round(_lead_expected_value(lead),2),'conversion_probability':lead.get('conversion_probability'),
            'visit_priority_score':lead.get('visit_priority_score'),'fixed':lead['business_key'] in fixed,
            'why_approach':lead.get('why_approach'),'open_now':lead.get('open_now'),'open_at_arrival':open_at_arrival,
            'opening_hours_text':lead.get('opening_hours_text'),'hours_warning':('Horário não pôde ser confirmado' if open_at_arrival is None else ('Fora do horário conhecido' if open_at_arrival is False else None))})
        chosen.append(lead);used_seconds+=travel_s+stop_s;current_time=departure;current_idx=i
    points=[origin]+[(x['lat'],x['lon']) for x in chosen]
    if end and (not points or points[-1]!=end):points.append(end)
    elif return_to_start and points[-1]!=origin:points.append(origin)
    geom=geoapify_route_geometry(points,profile,geoapify_key) or route_geometry(points,profile,ors_key)
    if geom and geom.get('duration_s') and not preserve_order:
        # tempo de direção da geometria é melhor para o total que a estimativa interna
        travel_total=float(geom.get('duration_s') or 0)
        used_minutes=round((travel_total+len(chosen)*visit_minutes*60)/60,1)
    else:used_minutes=round(used_seconds/60,1)
    chosen_keys={x['business_key'] for x in chosen}
    omitted_keys={x['business_key'] for x in omitted}
    for lead in candidates:
        if lead['business_key'] not in chosen_keys and lead['business_key'] not in omitted_keys:
            omitted.append({'business_key':lead['business_key'],'name':lead.get('name'),'reason':'Fora da seleção otimizada'})
    return {'ordered':chosen,'schedule':schedule,'omitted':omitted,'matrix_engine':engine,'used_minutes':used_minutes,
            'geometry':geom,'distance_m':(geom or {}).get('distance_m'),'duration_s':(geom or {}).get('duration_s'),
            'strategy':strategy,'exceeds_window':used_minutes>available_minutes}
