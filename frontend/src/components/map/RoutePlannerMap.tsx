import {MapContainer,TileLayer,Marker,Popup,Polyline,CircleMarker,useMap} from 'react-leaflet'
import L from 'leaflet'
import {useEffect} from 'react'
import type {Lead,RouteScheduleStop} from '@/types'

const icon=(n:number,fixed=false)=>L.divIcon({className:'',html:`<div style="width:32px;height:32px;border-radius:50%;display:grid;place-items:center;background:${fixed?'#e8a91b':'#4338ca'};color:white;font-weight:800;border:3px solid white;box-shadow:0 2px 8px #0004">${n}</div>`,iconSize:[32,32],iconAnchor:[16,16]})
function Fit({points}:{points:[number,number][]}){const map=useMap();useEffect(()=>{if(points.length>1)map.fitBounds(points,{padding:[30,30]})},[map,JSON.stringify(points)]);return null}

export function RoutePlannerMap({origin,end,leads,schedule,line,onLead}:{origin:[number,number];end?:[number,number]|null;leads:Lead[];schedule?:RouteScheduleStop[];line?:number[][];onLead?:(l:Lead)=>void}){
 const order=new Map((schedule||[]).map((s,i)=>[s.business_key,{i:i+1,fixed:!!s.fixed}]))
 const points:[number,number][]=[origin,...leads.map(l=>[l.lat,l.lon] as [number,number]),...(end?[end]:[])]
 return <MapContainer center={origin} zoom={14} className="h-[520px] w-full rounded-xl"><TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/><Fit points={points}/>
  <CircleMarker center={origin} radius={9} pathOptions={{color:'#16161d',fillColor:'#fff',fillOpacity:1,weight:3}}><Popup>Início da rota</Popup></CircleMarker>
  {end&&<CircleMarker center={end} radius={9} pathOptions={{color:'#0f766e',fillColor:'#ccfbf1',fillOpacity:1,weight:3}}><Popup>Destino final</Popup></CircleMarker>}
  {leads.map(l=>{const o=order.get(l.business_key);return <Marker key={l.business_key} position={[l.lat,l.lon]} icon={icon(o?.i||0,o?.fixed)} eventHandlers={{click:()=>onLead?.(l)}}><Popup><b>{l.name}</b><br/>{l.address}<br/>Prioridade: {l.visit_priority_score||0}</Popup></Marker>})}
  {!!line?.length&&<Polyline positions={line as [number,number][]} pathOptions={{color:'#4338ca',weight:5,opacity:.8}}/>}
 </MapContainer>
}
