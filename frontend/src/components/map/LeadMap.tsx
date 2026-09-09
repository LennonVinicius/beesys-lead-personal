import {CircleMarker,MapContainer,Popup,TileLayer} from 'react-leaflet'
import {Link} from 'react-router-dom'
import type {Lead} from '@/types'

export function LeadMap({leads,jobId,height=520,mode='pins'}:{leads:Lead[];jobId?:string|null;height?:number;mode?:'pins'|'opportunity'}){
 const first=leads[0];if(!first)return <div className="grid h-[320px] place-items-center rounded-xl bg-background text-sm text-muted">Sem leads para mostrar no mapa.</div>
 return <MapContainer center={[first.lat,first.lon]} zoom={13} style={{height,borderRadius:16}} scrollWheelZoom><TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/>{leads.slice(0,500).map(l=>{const score=l.visit_priority_score||0;const color=l.visited?'#16a34a':score>=75?'#dc2626':score>=50?'#d97706':'#4338ca';const radius=mode==='opportunity'?Math.max(8,Math.min(28,6+score/4)):7;const opacity=mode==='opportunity'?.28:.85;return <CircleMarker key={l.business_key} center={[l.lat,l.lon]} radius={radius} pathOptions={{color,fillColor:color,fillOpacity:opacity,weight:mode==='opportunity'?1:2}}><Popup><div className="min-w-[190px]"><b>{l.name}</b><div className="mt-1 text-xs">Prioridade {score}/100 · aderência {l.target_fit_score||0}/100</div><div className="mt-1 text-xs text-muted">{l.next_best_action?.label||l.why_approach}</div><Link className="mt-2 block text-xs font-semibold text-primary" to={`/leads/${encodeURIComponent(l.business_key)}${jobId?`?jobId=${jobId}`:''}`}>Abrir estabelecimento</Link></div></Popup></CircleMarker>})}</MapContainer>
}
