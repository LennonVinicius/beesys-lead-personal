import {useEffect,useMemo,useState} from 'react'
import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query'
import {api} from '@/services/api'
import type {Lead,RoutePlan,SavedRoute} from '@/types'
import {Card} from '@/components/ui/Card'
import {Button} from '@/components/ui/Button'
import {Badge} from '@/components/ui/Badge'
import {RoutePlannerMap} from '@/components/map/RoutePlannerMap'
import {GripVertical,Lock,LockOpen,MapPin,RotateCcw,Trash2,X} from 'lucide-react'

const strategies=[['balanced','Equilibrado'],['sales','Mais vendas prováveis'],['visits','Mais visitas possíveis'],['distance','Menor deslocamento'],['manual','Ordem manual']] as const
const money=(v?:number)=>v==null?'—':v.toLocaleString('pt-BR',{style:'currency',currency:'BRL'})
const conversionProbability=(lead:Lead)=>((lead as Lead & {conversion_probability?:number}).conversion_probability ?? 0)

export function RoutesPage(){
 const qc=useQueryClient()
 const q=useQuery({queryKey:['route-candidates'],queryFn:()=>api.get<Lead[]>('/api/leads?limit=500&visited=no&min_score=35')})
 const saved=useQuery({queryKey:['routes'],queryFn:()=>api.get<SavedRoute[]>('/api/routes?limit=30')})
 const team=useQuery({queryKey:['team'],queryFn:()=>api.get<string[]>('/api/team')})
 const campaigns=useQuery({queryKey:['campaigns'],queryFn:()=>api.get<string[]>('/api/campaigns')})

 const[origin,setOrigin]=useState<[number,number]>([-23.1896,-45.8841])
 const[end,setEnd]=useState<[number,number]|null>(null)
 const[returnToStart,setReturnToStart]=useState(false)
 const[selected,setSelected]=useState<string[]>([])
 const[fixed,setFixed]=useState<string[]>([])
 const[excluded,setExcluded]=useState<Record<string,string>>({})
 const[mode,setMode]=useState('driving-car')
 const[strategy,setStrategy]=useState('balanced')
 const[available,setAvailable]=useState(240)
 const[visit,setVisit]=useState(15)
 const[maxStops,setMaxStops]=useState(12)
 const[plan,setPlan]=useState<RoutePlan|null>(null)
 const[name,setName]=useState('Rota de hoje')
 const[drag,setDrag]=useState<string|null>(null)
 const[search,setSearch]=useState('')
 const[assignedTo,setAssignedTo]=useState('')
 const[campaign,setCampaign]=useState('')
 const[minScore,setMinScore]=useState(50)

 const allLeads=q.data||[]
 const leads=useMemo(()=>allLeads.filter(l=>{
   if(l.is_large_chain||l.do_not_contact)return false
   if((l.visit_priority_score||0)<minScore)return false
   if(assignedTo&&l.assigned_to!==assignedTo)return false
   if(campaign&&l.campaign_name!==campaign)return false
   return true
 }),[allLeads,minScore,assignedTo,campaign])
 const byKey=useMemo(()=>new Map(allLeads.map(l=>[l.business_key,l])),[allLeads])
 useEffect(()=>{if(leads.length&&!selected.length)setSelected(leads.slice(0,Math.min(20,leads.length)).map(l=>l.business_key))},[leads])
 const chosen=selected.map(k=>byKey.get(k)).filter(Boolean) as Lead[]
 const candidates=leads.filter(l=>!selected.includes(l.business_key)&&`${l.name} ${l.address||''}`.toLowerCase().includes(search.toLowerCase())).slice(0,30)
 const currentPos=()=>new Promise<void>((res,rej)=>navigator.geolocation.getCurrentPosition(p=>{setOrigin([p.coords.latitude,p.coords.longitude]);res()},rej,{enableHighAccuracy:true,timeout:8000}))
 const payload=(persist:boolean,manual=false)=>({origin_lat:origin[0],origin_lon:origin[1],origin_label:'Ponto inicial',end_lat:end?.[0],end_lon:end?.[1],end_label:end?'Destino final':undefined,business_keys:selected,fixed_business_keys:fixed,excluded_business_keys:Object.keys(excluded),mode,strategy:manual?'manual':strategy,available_minutes:available,visit_minutes:visit,max_stops:maxStops,return_to_start:returnToStart,persist,name,route_date:new Date().toISOString().slice(0,10),campaign_name:campaign||undefined})
 const calc=useMutation({mutationFn:()=>api.post<RoutePlan>('/api/routes/plan',payload(false,false)),onSuccess:r=>{setPlan(r);if(r.schedule?.length)setSelected(r.schedule.map(s=>s.business_key))}})
 const save=useMutation({mutationFn:()=>api.post<RoutePlan>('/api/routes/plan',payload(true,true)),onSuccess:r=>{setPlan(r);qc.invalidateQueries({queryKey:['routes']})}})
 const discard=useMutation({mutationFn:(lead:Lead)=>api.patch(`/api/leads/${encodeURIComponent(lead.business_key)}`,{pipeline_status:'LOST',assigned_to:lead.assigned_to||'',contact_name:lead.contact_name||'',contact_phone:lead.contact_phone||'',next_action_at:lead.next_action_at||null,notes:lead.notes||'',lost_reason:'Fora do perfil de prospecção',do_not_contact:true,estimated_mrr:lead.estimated_mrr||89.9}),onSuccess:()=>qc.invalidateQueries({queryKey:['route-candidates']})})
 const remove=(k:string,reason='Não interessa nesta rota')=>{setSelected(v=>v.filter(x=>x!==k));setFixed(v=>v.filter(x=>x!==k));setExcluded(v=>({...v,[k]:reason}));setPlan(null)}
 const move=(from:string,to:string)=>{setSelected(list=>{const a=[...list];const i=a.indexOf(from),j=a.indexOf(to);if(i<0||j<0)return a;a.splice(i,1);a.splice(j,0,from);return a});setPlan(null)}
 const toggleFixed=(k:string)=>setFixed(v=>v.includes(k)?v.filter(x=>x!==k):[...v,k])
 const routeLine=plan?.geometry?.line||[]
 const omitted=plan?.omitted||[]

 return <div className="space-y-6">
  <div><h1 className="text-2xl font-bold">Planejador de rota</h1><p className="mt-1 text-sm text-muted">A BeeSys sugere. Vocês decidem: removam, fixem, adicionem e reorganizem paradas antes de sair.</p></div>
  <div className="grid gap-5 xl:grid-cols-[410px_1fr]">
   <Card className="space-y-4">
    <label className="text-sm font-medium">Nome da rota<input className="mt-1 h-10 w-full rounded-lg border border-border px-3" value={name} onChange={e=>setName(e.target.value)}/></label>
    <div className="grid grid-cols-2 gap-3"><label className="text-sm font-medium">Modo<select className="mt-1 h-10 w-full rounded-lg border border-border bg-surface px-3" value={mode} onChange={e=>setMode(e.target.value)}><option value="driving-car">Carro</option><option value="foot-walking">A pé</option></select></label><label className="text-sm font-medium">Estratégia<select className="mt-1 h-10 w-full rounded-lg border border-border bg-surface px-3" value={strategy} onChange={e=>setStrategy(e.target.value)}>{strategies.map(([v,n])=><option key={v} value={v}>{n}</option>)}</select></label></div>
    <div className="grid grid-cols-3 gap-2"><label className="text-xs font-medium">Tempo (min)<input type="number" className="mt-1 h-10 w-full rounded-lg border border-border px-2" value={available} onChange={e=>setAvailable(Number(e.target.value))}/></label><label className="text-xs font-medium">Visita (min)<input type="number" className="mt-1 h-10 w-full rounded-lg border border-border px-2" value={visit} onChange={e=>setVisit(Number(e.target.value))}/></label><label className="text-xs font-medium">Máx. paradas<input type="number" className="mt-1 h-10 w-full rounded-lg border border-border px-2" value={maxStops} onChange={e=>setMaxStops(Number(e.target.value))}/></label></div>
    <div className="grid grid-cols-2 gap-2"><label className="text-xs font-medium">Responsável<select className="mt-1 h-10 w-full rounded-lg border border-border bg-surface px-2" value={assignedTo} onChange={e=>{setAssignedTo(e.target.value);setSelected([]);setPlan(null)}}><option value="">Todos</option>{(team.data||[]).map(x=><option key={x}>{x}</option>)}</select></label><label className="text-xs font-medium">Campanha<select className="mt-1 h-10 w-full rounded-lg border border-border bg-surface px-2" value={campaign} onChange={e=>{setCampaign(e.target.value);setSelected([]);setPlan(null)}}><option value="">Todas</option>{(campaigns.data||[]).map(x=><option key={x}>{x}</option>)}</select></label></div>
    <label className="text-xs font-medium">Prioridade mínima: {minScore}<input type="range" min="0" max="100" step="5" className="mt-2 w-full" value={minScore} onChange={e=>{setMinScore(Number(e.target.value));setSelected([]);setPlan(null)}}/></label>
    <Button variant="secondary" className="w-full" onClick={()=>currentPos().catch(()=>alert('Não foi possível acessar sua localização.'))}><MapPin className="h-4 w-4"/>Usar minha localização</Button>
    <div className="rounded-xl border border-border p-3"><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={returnToStart} onChange={e=>{setReturnToStart(e.target.checked);if(e.target.checked)setEnd(null)}}/>Voltar ao ponto inicial</label><label className="mt-3 flex items-center gap-2 text-sm"><input type="checkbox" checked={!!end} disabled={returnToStart} onChange={e=>setEnd(e.target.checked?[origin[0],origin[1]]:null)}/>Usar destino final diferente</label>{end&&<div className="mt-2 grid grid-cols-2 gap-2"><input type="number" step="any" className="h-9 rounded-lg border border-border px-2 text-xs" value={end[0]} onChange={e=>setEnd([Number(e.target.value),end[1]])}/><input type="number" step="any" className="h-9 rounded-lg border border-border px-2 text-xs" value={end[1]} onChange={e=>setEnd([end[0],Number(e.target.value)])}/><p className="col-span-2 text-[11px] text-muted">Latitude e longitude do destino final. Pode ser casa, escritório ou outro compromisso.</p></div>}</div>
    <Button className="w-full" disabled={!selected.length||calc.isPending} onClick={()=>calc.mutate()}>{calc.isPending?'Calculando...':'Recalcular rota'}</Button>
    <Button variant="secondary" className="w-full" disabled={!selected.length||save.isPending} onClick={()=>save.mutate()}>{save.isPending?'Salvando...':'Salvar rota de hoje'}</Button>
    {plan&&<div className="rounded-xl bg-primary-soft p-3 text-sm text-primary"><b>{plan.schedule.length} paradas</b><div className="mt-1">{plan.used_minutes} min estimados{plan.distance_m?` · ${(plan.distance_m/1000).toFixed(1)} km`:''}</div>{plan.exceeds_window&&<div className="mt-1 font-semibold text-danger">Paradas obrigatórias ultrapassam a janela de tempo.</div>}</div>}
    <div className="border-t border-border pt-4"><p className="text-sm font-semibold">Adicionar estabelecimento</p><input className="mt-2 h-10 w-full rounded-lg border border-border px-3" placeholder="Buscar no CRM" value={search} onChange={e=>setSearch(e.target.value)}/><div className="mt-2 max-h-44 space-y-1 overflow-auto">{candidates.map(l=><button key={l.business_key} className="w-full rounded-lg p-2 text-left text-sm hover:bg-surface-hover" onClick={()=>{setSelected(v=>[...v,l.business_key]);setSearch('');setPlan(null)}}><b>{l.name}</b><span className="block text-xs text-muted">Prioridade {l.visit_priority_score||0} · {l.next_best_action?.label||'avaliar'}</span></button>)}</div></div>
   </Card>
   <Card className="p-2"><RoutePlannerMap origin={origin} end={end} leads={chosen} schedule={plan?.schedule} line={routeLine}/></Card>
  </div>

  <div className="grid gap-5 xl:grid-cols-[1fr_360px]">
   <Card><div className="flex items-center justify-between"><div><h2 className="font-semibold">Paradas selecionadas</h2><p className="mt-1 text-sm text-muted">Arraste para ordenar. Remover daqui não apaga o lead do CRM.</p></div><Badge tone="primary">{selected.length} selecionados</Badge></div><div className="mt-4 space-y-2">{chosen.map((l,i)=><div key={l.business_key} draggable onDragStart={()=>setDrag(l.business_key)} onDragOver={e=>e.preventDefault()} onDrop={()=>{if(drag&&drag!==l.business_key)move(drag,l.business_key);setDrag(null)}} className="flex items-start gap-3 rounded-xl border border-border p-3"><GripVertical className="mt-1 h-5 w-5 cursor-grab text-subtle"/><div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-primary-soft text-sm font-bold text-primary">{i+1}</div><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><b>{l.name}</b>{fixed.includes(l.business_key)&&<Badge tone="warning">Obrigatório</Badge>}<Badge tone={(l.visit_priority_score||0)>=75?'primary':'neutral'}>{l.visit_priority_score||0}</Badge></div><p className="mt-1 text-xs text-muted">{l.address}</p><p className="mt-2 text-xs text-muted">{l.why_approach||l.next_best_action?.reason}</p>{l.notes&&<p className="mt-2 rounded-lg bg-background p-2 text-xs"><b>Nota:</b> {l.notes}</p>}<p className="mt-2 text-[11px] text-subtle">Valor esperado aproximado: {money((l.estimated_mrr||0)*(conversionProbability(l)/100))}</p></div><div className="flex gap-1"><button title="Fixar" className="rounded-lg p-2 hover:bg-surface-hover" onClick={()=>toggleFixed(l.business_key)}>{fixed.includes(l.business_key)?<Lock className="h-4 w-4 text-warning"/>:<LockOpen className="h-4 w-4 text-muted"/>}</button><button title="Remover só desta rota" className="rounded-lg p-2 hover:bg-danger-soft" onClick={()=>remove(l.business_key)}><X className="h-4 w-4 text-danger"/></button><button title="Descartar permanentemente" className="rounded-lg p-2 hover:bg-danger-soft" onClick={()=>{if(confirm(`Descartar ${l.name} e marcar como não contatar?`)){discard.mutate(l);remove(l.business_key,'Descartado permanentemente')}}}><Trash2 className="h-4 w-4 text-danger"/></button></div></div>)}{!chosen.length&&<p className="text-sm text-muted">Nenhum estabelecimento selecionado.</p>}</div></Card>
   <div className="space-y-5">
    <Card><h2 className="font-semibold">Ficaram de fora</h2><p className="mt-1 text-xs text-muted">O sistema explica por que uma parada não entrou no plano calculado.</p><div className="mt-3 max-h-64 space-y-2 overflow-auto">{omitted.map(o=><div key={`${o.business_key}-${o.reason}`} className="rounded-lg border border-border p-3"><b className="text-sm">{o.name||byKey.get(o.business_key)?.name||o.business_key}</b><p className="mt-1 text-xs text-muted">{o.reason}</p></div>)}{!omitted.length&&<p className="text-sm text-muted">Recalcule a rota para ver a análise.</p>}</div></Card>
    <Card><h2 className="font-semibold">Excluídos manualmente</h2><p className="mt-1 text-xs text-muted">Continuam no CRM.</p><div className="mt-3 space-y-2">{Object.entries(excluded).map(([k,reason])=>{const l=byKey.get(k);return <div key={k} className="rounded-lg border border-border p-3"><b className="text-sm">{l?.name||k}</b><p className="text-xs text-muted">{reason}</p><button className="mt-2 text-xs font-semibold text-primary" onClick={()=>{setExcluded(v=>{const n={...v};delete n[k];return n});setSelected(v=>[...v,k])}}><RotateCcw className="mr-1 inline h-3 w-3"/>Voltar para rota</button></div>})}{!Object.keys(excluded).length&&<p className="text-sm text-muted">Nenhum.</p>}</div></Card>
    <Card><h2 className="font-semibold">Rotas salvas</h2><div className="mt-3 space-y-2">{(saved.data||[]).slice(0,6).map(r=><div key={r.id} className="rounded-lg border border-border p-3"><b className="text-sm">{r.name}</b><p className="text-xs text-muted">{r.route_date} · {r.mode==='foot-walking'?'A pé':'Carro'} · {r.strategy}</p></div>)}</div></Card>
   </div>
  </div>
 </div>
}
