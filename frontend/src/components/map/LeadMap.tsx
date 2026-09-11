import {CircleMarker,MapContainer,Popup,TileLayer,useMapEvents} from 'react-leaflet'
import {Link} from 'react-router-dom'
import {useMemo,useState} from 'react'
import type {Lead} from '@/types'

type Mode='pins'|'opportunity'
type Cluster={key:string;lat:number;lon:number;leads:Lead[];score:number}

function ZoomWatcher({onZoom}:{onZoom:(z:number)=>void}){useMapEvents({zoomend:e=>onZoom(e.target.getZoom())});return null}

function clusterLeads(leads:Lead[],zoom:number):Cluster[]{
  if(zoom>=15)return leads.map(l=>({key:l.business_key,lat:l.lat,lon:l.lon,leads:[l],score:l.visit_priority_score||0}))
  const precision=zoom<=11?0.03:zoom<=12?0.018:zoom<=13?0.01:0.005
  const groups=new Map<string,Lead[]>()
  for(const lead of leads){const key=`${Math.round(lead.lat/precision)}:${Math.round(lead.lon/precision)}`;const arr=groups.get(key)||[];arr.push(lead);groups.set(key,arr)}
  return [...groups.entries()].map(([key,group])=>({key,lat:group.reduce((a,l)=>a+l.lat,0)/group.length,lon:group.reduce((a,l)=>a+l.lon,0)/group.length,leads:group,score:Math.round(group.reduce((a,l)=>a+(l.visit_priority_score||0),0)/group.length)}))
}

export function LeadMap({leads,jobId,height=520,mode='pins'}:{leads:Lead[];jobId?:string|null;height?:number;mode?:Mode}){
 const first=leads[0];const[zoom,setZoom]=useState(13)
 const clusters=useMemo(()=>clusterLeads(leads.slice(0,800),zoom),[leads,zoom])
 if(!first)return <div className="grid h-[320px] place-items-center rounded-xl bg-background text-sm text-muted">Sem leads para mostrar no mapa.</div>
 return <div className="relative"><MapContainer center={[first.lat,first.lon]} zoom={13} style={{height,borderRadius:16}} scrollWheelZoom><ZoomWatcher onZoom={setZoom}/><TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/>{clusters.map(c=>{
  const single=c.leads.length===1?c.leads[0]:null;const score=c.score;const visited=single?.visited;const color=visited?'#16a34a':score>=75?'#dc2626':score>=50?'#d97706':'#4338ca';const radius=c.leads.length>1?Math.min(26,10+Math.log2(c.leads.length)*4):mode==='opportunity'?Math.max(8,Math.min(26,6+score/4)):7;const opacity=mode==='opportunity'?.26:.86
  return <CircleMarker key={c.key} center={[c.lat,c.lon]} radius={radius} pathOptions={{color,fillColor:color,fillOpacity:opacity,weight:2}}><Popup>{single?<div className="min-w-[210px]"><b>{single.name}</b><div className="mt-1 text-xs">Prioridade {score}/100 · aderência {single.target_fit_score||0}/100</div><div className="mt-1 text-xs text-muted">{single.next_best_action?.label||single.why_approach}</div><Link className="mt-2 block text-xs font-semibold text-primary" to={`/leads/${encodeURIComponent(single.business_key)}${jobId?`?jobId=${jobId}`:''}`}>Abrir estabelecimento</Link></div>:<div className="min-w-[210px]"><b>{c.leads.length} estabelecimentos</b><p className="mt-1 text-xs text-muted">Prioridade média {score}/100. Aproxime o mapa para separar os pontos.</p><div className="mt-2 space-y-1">{c.leads.slice(0,5).map(l=><div key={l.business_key} className="text-xs">{l.name} · {l.visit_priority_score||0}</div>)}</div></div>}</Popup></CircleMarker>
 })}</MapContainer><div className="pointer-events-none absolute bottom-3 left-3 z-[500] rounded-xl border border-border bg-surface/95 p-3 text-[11px] shadow-sm backdrop-blur"><div className="mb-2 font-semibold text-ink">Legenda</div><div className="grid gap-1.5"><span><i className="mr-2 inline-block h-2.5 w-2.5 rounded-full bg-red-600"/>Alta prioridade</span><span><i className="mr-2 inline-block h-2.5 w-2.5 rounded-full bg-amber-600"/>Prioridade média</span><span><i className="mr-2 inline-block h-2.5 w-2.5 rounded-full bg-indigo-600"/>Baixa prioridade</span><span><i className="mr-2 inline-block h-2.5 w-2.5 rounded-full bg-green-600"/>Visitado</span></div></div></div>
}
