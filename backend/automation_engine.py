import json
from datetime import datetime, timedelta, timezone

from db import _conn,_execute,get_business,create_followup,assign_cadence,list_automation_rules


def _matches(lead,conditions):
    for key,value in (conditions or {}).items():
        if key=='min_score' and float(lead.get('visit_priority_score') or 0)<float(value):return False
        if key=='status' and (lead.get('pipeline_status') or '')!=str(value):return False
        if key=='campaign' and (lead.get('campaign_name') or '')!=str(value):return False
        if key=='no_booking' and bool(value) and lead.get('has_booking'):return False
        if key=='local_only' and bool(value) and lead.get('is_large_chain'):return False
    return True


def run_automations(event_name,business_key,actor_email=''):
    lead=get_business(business_key)
    if not lead:return []
    applied=[]
    now=datetime.now(timezone.utc)
    for rule in list_automation_rules(active_only=True):
        if rule.get('event_name') not in {event_name,'*'}:continue
        if not _matches(lead,rule.get('conditions') or {}):continue
        for action in rule.get('actions') or []:
            kind=action.get('type')
            if kind=='followup':
                days=max(0,int(action.get('days') or 0));due=(now+timedelta(days=days)).isoformat()
                create_followup(business_key,action.get('title') or 'Follow-up automático',due,'AUTOMATION',action.get('notes') or '')
                applied.append({'rule':rule['name'],'action':'followup'})
            elif kind=='cadence' and action.get('cadence_id'):
                assign_cadence(business_key,int(action['cadence_id']),actor_email);applied.append({'rule':rule['name'],'action':'cadence'})
            elif kind=='status' and action.get('status'):
                with _conn() as conn:_execute(conn,"UPDATE businesses SET pipeline_status=?,last_status_changed_at=? WHERE business_key=?",(action['status'],now.isoformat(),business_key));conn.commit()
                applied.append({'rule':rule['name'],'action':'status'})
            elif kind=='assign' and action.get('email'):
                with _conn() as conn:_execute(conn,"UPDATE businesses SET assigned_to=? WHERE business_key=?",(action['email'],business_key));conn.commit()
                applied.append({'rule':rule['name'],'action':'assign'})
    return applied
