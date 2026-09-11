import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone


def clamp(value, lo=0.0, hi=100.0):
    try:
        return max(lo,min(hi,float(value)))
    except Exception:
        return lo


def product_fit(lead: dict) -> dict:
    """Rule-based product fit; intentionally explainable and provider-agnostic."""
    digital_gap=100-clamp(lead.get('digital_maturity_score') or 0)
    target=clamp(lead.get('target_fit_score') or 50)
    local_bonus=12 if not lead.get('is_large_chain') else -25
    agenda=35
    agenda += 28 if not lead.get('has_booking') else -12
    agenda += 18 if lead.get('manual_booking_detected') else 0
    agenda += 8 if lead.get('has_whatsapp') else 0
    agenda += 8 if any(x in (lead.get('category') or '').lower() for x in ('beauty','hair','barber','clinic','health','fitness','salão','barbear','clín')) else 0
    agenda += local_bonus + (target-50)*0.18

    subscription=28
    subscription += 12 if lead.get('website') else 0
    subscription += 10 if lead.get('has_catalog') else 0
    subscription += 10 if lead.get('has_whatsapp') else 0
    subscription += 8 if float(lead.get('reviews') or 0) >= 30 else 0
    subscription += local_bonus + (target-50)*0.12

    credit=20
    category=(lead.get('category') or '').lower()
    credit += 26 if any(x in category for x in ('retail','shop','store','commercial','loja','eletr','mobile','furniture','móveis')) else 0
    credit += 10 if lead.get('has_catalog') else 0
    credit += 8 if float(lead.get('reviews') or 0) >= 20 else 0
    credit += local_bonus + (target-50)*0.10
    return {
        'agenda': round(clamp(agenda)),
        'assinatura': round(clamp(subscription)),
        'crediario': round(clamp(credit)),
        'digital_gap': round(clamp(digital_gap)),
    }


def competitor_playbook(lead: dict) -> dict:
    name=(lead.get('competitor_name') or lead.get('booking_provider') or '').strip()
    lower=name.lower()
    if not name:
        if lead.get('manual_booking_detected'):
            return {
                'competitor':'Agenda manual',
                'angle':'Trocar trabalho operacional por confirmação e disponibilidade automáticas.',
                'questions':['Quantas mensagens por dia são só para marcar ou remarcar horário?','Quantos horários ficam vagos por falta de confirmação?'],
            }
        return {
            'competitor':'Nenhum sistema identificado',
            'angle':'Começar pela dor atual antes de apresentar funcionalidades.',
            'questions':['Como vocês organizam agenda, confirmações e retornos hoje?','Qual parte mais toma tempo da equipe?'],
        }
    if 'booksy' in lower:
        angle='Entender custo, dependência do marketplace e necessidade de marca própria; comparar somente onde houver dor real.'
    elif 'trinks' in lower:
        angle='Investigar complexidade, custo por equipe/unidade e experiência do cliente antes de propor migração.'
    elif 'fresha' in lower:
        angle='Perguntar sobre taxas, experiência de pagamento/marketplace e controle da base de clientes.'
    elif 'gendo' in lower:
        angle='Mapear o que já funciona e focar apenas em diferenciais BeeSys que resolvam uma dor comprovada.'
    elif 'doctoralia' in lower:
        angle='Separar aquisição de pacientes de gestão/agenda própria e entender quanto dependem do marketplace.'
    else:
        angle='Não atacar o concorrente. Descobrir a principal limitação atual e demonstrar somente a diferença relevante.'
    return {
        'competitor':name,
        'angle':angle,
        'questions':['O que você mais gosta no sistema atual?','O que ainda precisa fazer manualmente?','Se pudesse mudar uma coisa nele, qual seria?'],
    }


def compute_lead_intelligence(lead: dict, segment_baseline: dict | None = None) -> dict:
    maturity=clamp(lead.get('digital_maturity_score') or 0)
    gap=100-maturity
    target=clamp(lead.get('target_fit_score') or lead.get('commercial_potential_score') or 50)
    commercial=clamp(0.55*target+0.45*clamp(lead.get('commercial_potential_score') or target))
    probability=clamp(lead.get('conversion_probability') or 0)
    data_conf=clamp(lead.get('data_confidence') or 50)
    completeness=sum(1 for k in ('address','phone','website','category','last_analyzed_at') if lead.get(k))/5*100
    confidence=clamp(data_conf*0.7+completeness*0.3)
    mrr=float(lead.get('estimated_mrr') or 89.90)
    expected=max(0,mrr*probability/100)
    fits=product_fit(lead)
    reasons=[]
    if gap >= 60: reasons.append('Grande lacuna digital')
    if lead.get('manual_booking_detected'): reasons.append('Agendamento manual identificado')
    if not lead.get('has_booking'): reasons.append('Sem agenda online identificada')
    if lead.get('competitor_detected'): reasons.append('Já usa software concorrente')
    if target >= 75: reasons.append('Alta aderência ao ICP')
    if confidence < 55: reasons.append('Dados ainda precisam de confirmação')
    counterfactual=[]
    if not lead.get('has_booking'): counterfactual.append('Se adotar agendamento online, a lacuna digital deixa de ser um dos principais argumentos de abordagem.')
    if not lead.get('website'): counterfactual.append('Se criar um site próprio rastreável, a diferença de presença digital tende a cair de forma relevante.')
    if probability < 35: counterfactual.append('Uma interação positiva ou demonstração registrada pode aumentar a prioridade comercial mais do que sinais digitais isolados.')
    if confidence < 55: counterfactual.append('Confirmar telefone, site e rotina de agendamento pode mudar significativamente esta recomendação.')
    return {
        'digital_gap_score':round(gap),
        'commercial_fit_score':round(commercial),
        'conversion_probability':round(probability,1),
        'conversion_confidence':round(confidence),
        'expected_mrr_value':round(expected,2),
        'product_fit':fits,
        'decision_reasons':reasons,
        'counterfactual':counterfactual,
        'competitor_playbook':competitor_playbook(lead),
    }


def _conv(rows):
    if not rows:return 0.0
    return 100*sum(1 for x in rows if x.get('pipeline_status')=='CLIENT')/len(rows)


def _wilson_interval(successes:int,total:int,z:float=1.96):
    if total<=0:return (0.0,0.0)
    p=successes/total;den=1+z*z/total
    center=(p+z*z/(2*total))/den
    margin=z*math.sqrt((p*(1-p)+z*z/(4*total))/total)/den
    return (round(max(0,center-margin)*100,1),round(min(1,center+margin)*100,1))


def intelligence_overview(leads: list[dict]) -> dict:
    usable=[x for x in leads if x.get('pipeline_status') not in ('DO_NOT_CONTACT',)]
    by_segment=defaultdict(list);by_campaign=defaultdict(list);by_provider=defaultdict(list)
    for x in usable:
        segment=(x.get('category') or 'Sem segmento').split(',')[0].strip()[:70] or 'Sem segmento'
        by_segment[segment].append(x)
        by_campaign[x.get('campaign_name') or 'Sem campanha'].append(x)
        by_provider[x.get('provider') or 'Desconhecida'].append(x)
    segments=[]
    for name,rows in by_segment.items():
        if len(rows)<2:continue
        clients=sum(1 for x in rows if x.get('pipeline_status')=='CLIENT')
        expected=sum(float((compute_lead_intelligence(x)).get('expected_mrr_value') or 0) for x in rows)
        segments.append({'name':name,'leads':len(rows),'clients':clients,'conversion_pct':round(_conv(rows),1),'expected_mrr':round(expected,2)})
    segments.sort(key=lambda x:(x['conversion_pct'],x['clients'],x['leads']),reverse=True)

    pitch=defaultdict(list)
    for x in usable:
        pitch[x.get('pitch_variant') or 'A'].append(x)
    pitch_rows=[]
    for variant,rows in pitch.items():
        positive=sum(1 for x in rows if x.get('pipeline_status') in ('INTERESTED','DEMO','PROPOSAL','CLIENT'))
        clients=sum(1 for x in rows if x.get('pipeline_status')=='CLIENT')
        lo,hi=_wilson_interval(clients,len(rows))
        pitch_rows.append({'variant':variant,'leads':len(rows),'positive':positive,'clients':clients,'positive_pct':round(100*positive/max(1,len(rows)),1),'client_pct':round(100*clients/max(1,len(rows)),1),'client_ci_low':lo,'client_ci_high':hi,'confidence_label':'alta' if len(rows)>=100 else 'média' if len(rows)>=30 else 'baixa'})

    signals=defaultdict(lambda:{'total':0,'clients':0})
    def sig(x,label,ok):
        if ok:
            signals[label]['total']+=1
            signals[label]['clients']+=1 if x.get('pipeline_status')=='CLIENT' else 0
    for x in usable:
        sig(x,'Sem agenda online',not x.get('has_booking'))
        sig(x,'Agenda manual',bool(x.get('manual_booking_detected')))
        sig(x,'Sem site',not x.get('website'))
        sig(x,'WhatsApp ativo',bool(x.get('has_whatsapp')))
        sig(x,'Negócio local',not x.get('is_large_chain'))
        sig(x,'50+ avaliações',float(x.get('reviews') or 0)>=50)
    signal_rows=[]
    for label,s in signals.items():
        signal_rows.append({'signal':label,'leads':s['total'],'clients':s['clients'],'conversion_pct':round(100*s['clients']/max(1,s['total']),1)})
    signal_rows.sort(key=lambda x:(x['conversion_pct'],x['clients']),reverse=True)

    recommended=[]
    for x in usable:
        intel=compute_lead_intelligence(x)
        if x.get('pipeline_status') in ('CLIENT','LOST'):continue
        score=float(x.get('visit_priority_score') or 0)*0.55+intel['expected_mrr_value']*0.25+intel['commercial_fit_score']*0.20
        recommended.append({'lead':x,'intelligence':intel,'decision_score':round(score,2)})
    recommended.sort(key=lambda x:x['decision_score'],reverse=True)
    best_segment=segments[0] if segments else None
    best_signal=signal_rows[0] if signal_rows else None
    insights=[]
    if best_segment and best_segment['clients']:
        insights.append(f"{best_segment['name']} é o segmento com melhor conversão observada ({best_segment['conversion_pct']}% em {best_segment['leads']} leads).")
    if best_signal and best_signal['clients']:
        insights.append(f"O sinal “{best_signal['signal']}” aparece com conversão observada de {best_signal['conversion_pct']}%.")
    if not insights:
        insights.append('Ainda faltam conversões suficientes para o sistema aprender padrões com confiança; continue registrando CLIENT e LOST.')
    suggested_icp=None
    if best_segment:
        segrows=by_segment.get(best_segment['name'],[])
        booking_gap=sum(1 for x in segrows if not x.get('has_booking'))/max(1,len(segrows))*100
        local_share=sum(1 for x in segrows if not x.get('is_large_chain'))/max(1,len(segrows))*100
        review_values=sorted(float(x.get('reviews') or 0) for x in segrows)
        median_reviews=review_values[len(review_values)//2] if review_values else 0
        suggested_icp={'segment':best_segment['name'],'observed_conversion_pct':best_segment['conversion_pct'],'sample_size':best_segment['leads'],'signals':{'without_online_booking_pct':round(booking_gap,1),'local_business_pct':round(local_share,1),'median_reviews':round(median_reviews)},'confidence':'alta' if best_segment['leads']>=100 else 'média' if best_segment['leads']>=30 else 'baixa'}
    return {
        'totals':{'leads':len(usable),'clients':sum(1 for x in usable if x.get('pipeline_status')=='CLIENT'),'expected_mrr':round(sum(compute_lead_intelligence(x)['expected_mrr_value'] for x in usable),2)},
        'segments':segments[:12],
        'pitches':pitch_rows,
        'signals':signal_rows,
        'recommended':recommended[:25],
        'insights':insights,
        'suggested_icp':suggested_icp,
    }


def natural_filter(query: str, leads: list[dict]) -> dict:
    q=(query or '').strip().lower()
    min_score=None
    m=re.search(r'(?:score|prioridade)\s*(?:acima de|>|maior que)?\s*(\d{1,3})',q)
    if m:min_score=int(m.group(1))
    only_unvisited=any(x in q for x in ('não visit','nao visit','sem visita'))
    no_booking=any(x in q for x in ('sem agendamento','sem agenda','não têm agenda','nao tem agenda'))
    no_site=any(x in q for x in ('sem site','não têm site','nao tem site'))
    local_only=any(x in q for x in ('negócios locais','negocios locais','sem rede','independentes'))
    status=None
    for s in ('client','proposal','demo','interested','visited','priority','new','lost'):
        if s.lower() in q:status=s.upper()
    segment_terms=[]
    for term in ('barbearia','barbearias','salão','salao','clínica','clinica','pet shop','academia','restaurante','loja','papelaria','boutique'):
        if term in q:segment_terms.append(term.replace('barbearias','barbearia').replace('salao','salão').replace('clinica','clínica'))
    out=[]
    for x in leads:
        if min_score is not None and float(x.get('visit_priority_score') or x.get('opportunity_score') or 0)<min_score:continue
        if only_unvisited and x.get('visited'):continue
        if no_booking and x.get('has_booking'):continue
        if no_site and x.get('website'):continue
        if local_only and x.get('is_large_chain'):continue
        if status and (x.get('pipeline_status') or '').upper()!=status:continue
        blob=f"{x.get('name','')} {x.get('category','')} {x.get('district_name','')} {x.get('city_name','')}".lower()
        if segment_terms and not any(term in blob for term in segment_terms):continue
        out.append(x)
    out.sort(key=lambda x:(float(x.get('visit_priority_score') or 0),float(x.get('conversion_probability') or 0)),reverse=True)
    parsed={'min_score':min_score,'only_unvisited':only_unvisited,'no_booking':no_booking,'no_site':no_site,'local_only':local_only,'status':status,'segments':segment_terms}
    return {'query':query,'parsed':parsed,'count':len(out),'results':out[:200]}


def copilot_answer(question: str, leads: list[dict], actor_email: str='') -> dict:
    q=(question or '').lower()
    overview=intelligence_overview(leads)
    if any(x in q for x in ('quem visitar','visitar hoje','melhores leads','prioridade')):
        picks=overview['recommended'][:7]
        summary='Priorizei valor esperado, prioridade comercial, aderência e probabilidade observada.'
        return {'answer':summary,'items':picks,'kind':'recommended'}
    if any(x in q for x in ('segmento','converte','conversão','conversao','icp')):
        return {'answer':overview['insights'][0],'items':overview['segments'][:8],'kind':'segments'}
    if any(x in q for x in ('pitch','abordagem','script')):
        pitches=sorted(overview['pitches'],key=lambda x:(x['client_pct'],x['positive_pct']),reverse=True)
        answer='Ainda não há volume suficiente para declarar um vencedor.' if not pitches or max(x['clients'] for x in pitches)==0 else f"A variante {pitches[0]['variant']} tem o melhor resultado observado até agora."
        return {'answer':answer,'items':pitches,'kind':'pitches'}
    if any(x in q for x in ('perd','objeção','objecao','motivo')):
        counts=Counter((x.get('lost_reason') or x.get('last_objection_code') or 'Sem motivo registrado') for x in leads if x.get('pipeline_status')=='LOST' or x.get('last_objection_code'))
        rows=[{'reason':k,'count':v} for k,v in counts.most_common(10)]
        return {'answer':'Estes são os motivos/objeções mais registrados na base atual.','items':rows,'kind':'losses'}
    return {'answer':overview['insights'][0], 'items':overview['recommended'][:5], 'kind':'overview'}
