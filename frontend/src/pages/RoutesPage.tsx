import {useEffect,useMemo,useState} from 'react'
import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query'
import {api} from '@/services/api'
import type {Lead,RoutePlan,SavedRoute,SearchJob} from '@/types'
import {Card} from '@/components/ui/Card'
import {Button} from '@/components/ui/Button'
import {Badge} from '@/components/ui/Badge'
import {RoutePlannerMap} from '@/components/map/RoutePlannerMap'
import {GripVertical,Lock,LockOpen,MapPin,RotateCcw,Trash2,X} from 'lucide-react'

const strategies=[['balanced','Equilibrado'],['sales','Mais vendas prováveis'],['visits','Mais visitas possíveis'],['distance','Menor deslocamento'],['manual','Ordem manual']] as const
const money=(v?:number)=>v==null?'—':v.toLocaleString('pt-BR',{style:'currency',currency:'BRL'})
type CampaignItem=string|{campaign_name:string;leads?:number}
const campaignName=(item:CampaignItem)=>typeof item==='string'?item:item.campaign_name

export function RoutesPage(){
 const qc=useQueryClient()
 const globalLeads=useQuery({queryKey:['route-candidates'],queryFn:()=>api.get<Lead[]>('/api/leads?limit=1000&visited=no&min_score=0&include_large_chains=true')})
 const jobs=useQuery({queryKey:['route-search-jobs'],queryFn:()=>api.get<SearchJob[]>('/api/searches?limit=50')})
 const saved=useQuery({queryKey:['routes'],queryFn:()=>api.get<SavedRoute[]>('/api/routes?limit=30')})
 const team=useQuery({queryKey:['team'],queryFn:()=>api.get<string[]>('/api/team')})
 const campaigns=useQuery({queryKey:['campaigns'],queryFn:()=>api.get<CampaignItem[]>('/api/campaigns')})

 const[processingId,setProcessingId]=useState<number|''>('')
 const selectedJob=useQuery({queryKey:['route-processing',processingId],queryFn:()=>api.get<SearchJob>(`/api/searches/${processingId}`),enabled:!!processingId})
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
 const[previousPlan,setPreviousPlan]=useState<RoutePlan|null>(null)
 const[name,setName]=useState('Rota de hoje')
 const[drag,setDrag]=useState<string|null>(null)
 const[search,setSearch]=useState('')
 const[assignedTo,setAssignedTo]=useState('')
 const[campaign,setCampaign]=useState('')
 const[minScore,setMinScore]=useState(50)

 const allLeads=(processingId?selectedJob.data?.results:globalLeads.data)||[]
 const leads=useMemo(()=>allLeads.filter(l=>{
   if(l.is_large_chain||l.do_not_contact)return false
   if((l.visit_priority_score||0)<minScore)return false
   if(assignedTo&&l.assigned_to!==assignedTo)return false
   if(campaign&&l.campaign_name!==campaign)return false
   return true
 }),[allLeads,minScore,assignedTo,campaign])
 const byKey=useMemo(()=>new Map(allLeads.map(l=>[l.business_key,l])),[allLeads])
 const campaignOptions=useMemo(()=>Array.from(new Set((campaigns.data||[]).map(campaignName).filter(Boolean))),[campaigns.data])
 const completedJobs=useMemo(()=>[...(jobs.data||[])].sort((a,b)=>b.id-a.id),[jobs.data])

 useEffect(()=>{
   if(!processingId||!selectedJob.data)return
   setOrigin([selectedJob.data.center_lat,selectedJob.data.center_lon])
   const initial=(selectedJob.data.results||[]).filter(l=>!l.is_large_chain&&!l.do_not_contact&&(l.visit_priority_score||0)>=minScore).sort((a,b)=>(b.visit_priority_score||0)-(a.visit_priority_score||0)).slice(0,20).map(l=>l.business_key)
   setSelected(initial)
   setFixed([]);setExcluded({});setPlan(null)
   const cfg=selectedJob.data.config||{}
   if(typeof cfg.campaign_name==='string')setCampaign(cfg.campaign_name)
 },[processingId,selectedJob.data?.id])

 const chosen=selected.map(k=>byKey.get(k)).filter(Boolean) as Lead[]
 const candidates=leads.filter(l=>!selected.includes(l.business_key)&&`${l.name} ${l.address||''}`.toLowerCase().includes(search.toLowerCase())).slice(0,30)
 const currentPos=()=>new Promise<void>((res,rej)=>navigator.geolocation.getCurrentPosition(p=>{setOrigin([p.coords.latitude,p.coords.longitude]);res()},rej,{enableHighAccuracy:true,timeout:8000}))
 const payload=(persist:boolean,manual=false)=>{const now=new Date();const startLocal=new Date(now.getTime()-now.getTimezoneOffset()*60000).toISOString().slice(0,19);return {origin_lat:origin[0],origin_lon:origin[1],origin_label:'Ponto inicial',start_local:startLocal,end_lat:end?.[0],end_lon:end?.[1],end_label:end?'Destino final':undefined,business_keys:selected,fixed_business_keys:fixed,excluded_business_keys:Object.keys(excluded),mode,strategy:manual?'manual':strategy,available_minutes:available,visit_minutes:visit,max_stops:maxStops,return_to_start:returnToStart,persist,name,route_date:new Date().toISOString().slice(0,10),campaign_name:campaign||undefined}}
 const calc=useMutation({mutationFn:()=>api.post<RoutePlan>('/api/routes/plan',payload(false,false)),onSuccess:r=>{setPreviousPlan(plan);setPlan(r);if(r.schedule?.length)setSelected(r.schedule.map(s=>s.business_key))}})
 const save=useMutation({mutationFn:()=>api.post<RoutePlan>('/api/routes/plan',payload(true,true)),onSuccess:r=>{setPlan(r);qc.invalidateQueries({queryKey:['routes']})}})
 const discard=useMutation({mutationFn:(lead:Lead)=>api.patch(`/api/leads/${encodeURIComponent(lead.business_key)}`,{pipeline_status:'LOST',assigned_to:lead.assigned_to||'',contact_name:lead.contact_name||'',contact_phone:lead.contact_phone||'',next_action_at:lead.next_action_at||null,notes:lead.notes||'',lost_reason:'Fora do perfil de prospecção',do_not_contact:true,estimated_mrr:lead.estimated_mrr||89.9}),onSuccess:()=>{qc.invalidateQueries({queryKey:['route-candidates']});if(processingId)qc.invalidateQueries({queryKey:['route-processing',processingId]})}})
 const remove=(k:string,reason='Não interessa nesta rota')=>{setSelected(v=>v.filter(x=>x!==k));setFixed(v=>v.filter(x=>x!==k));setExcluded(v=>({...v,[k]:reason}));setPlan(null)}
 const move=(from:string,to:string)=>{setSelected(list=>{const a=[...list];const i=a.indexOf(from),j=a.indexOf(to);if(i<0||j<0)return a;a.splice(i,1);a.splice(j,0,from);return a});setPlan(null)}
 const toggleFixed=(k:string)=>setFixed(v=>v.includes(k)?v.filter(x=>x!==k):[...v,k])
 const selectSuggested=()=>{setSelected(leads.slice(0,Math.min(Math.max(maxStops*2,20),40)).map(l=>l.business_key));setFixed([]);setExcluded({});setPlan(null)}
 const routeLine=plan?.geometry?.line||[]
 const omitted=plan?.omitted||[]
 const scheduleByKey=useMemo(()=>new Map((plan?.schedule||[]).map(x=>[x.business_key,x])),[plan])
 const expectedMrr=chosen.reduce((sum,l)=>sum+(l.estimated_mrr||0)*((l.conversion_probability||0)/100),0)
 const timeDelta=plan&&previousPlan?plan.used_minutes-previousPlan.used_minutes:0
 const stopDelta=plan&&previousPlan?plan.schedule.length-previousPlan.schedule.length:0

 return <div className="space-y-6">
  <div><h1 className="text-2xl font-bold">Planejador de rota</h1><p className="mt-1 text-sm text-muted">Escolha primeiro qual processamento quer usar. Depois ajuste os estabelecimentos, remova os que não interessam e deixe a BeeSys otimizar a ordem.</p></div>
  <Card className="space-y-4"><div><h2 className="font-semibold">Fonte dos estabelecimentos</h2><p className="mt-1 text-sm text-muted">Selecione uma busca já processada para montar a rota somente com os estabelecimentos daquela região.</p></div><div className="grid gap-3 lg:grid-cols-[1fr_auto_auto]"><label className="text-sm font-medium">Processamento<select className="mt-1 h-11 w-full rounded-lg border border-border bg-surface px-3" value={processingId} onChange={e=>{const id=e.target.value?Number(e.target.value):'';setProcessingId(id);setSelected([]);setFixed([]);setExcluded({});setPlan(null);setCampaign('')}}><option value="">Todos os leads do CRM</option>{completedJobs.map(j=><option key={j.id} value={j.id} disabled={j.status!=='DONE'}>#{j.id} — {j.query_text} — {(j.radius_m/1000).toFixed(1)} km — {j.status==='DONE'?`${j.total_items} encontrados`:j.status}</option>)}</select></label><Button variant="secondary" className="self-end" disabled={!leads.length} onClick={selectSuggested}>Selecionar sugeridos</Button><Button variant="secondary" className="self-end" disabled={!selected.length} onClick={()=>{setSelected([]);setFixed([]);setExcluded({});setPlan(null)}}>Limpar seleção</Button></div>
   {processingId&&selectedJob.data&&<div className="grid gap-3 rounded-xl bg-primary-soft p-4 text-sm sm:grid-cols-4"><div><span className="block text-xs text-primary/70">Processamento</span><b>#{selectedJob.data.id}</b></div><div><span className="block text-xs text-primary/70">Área</span><b>{selectedJob.data.query_text}</b></div><div><span className="block text-xs text-primary/70">Raio</span><b>{(selectedJob.data.radius_m/1000).toFixed(1)} km</b></div><div><span className="block text-xs text-primary/70">Elegíveis agora</span><b>{leads.length} de {allLeads.length}</b></div></div>}
  </Card>
  <div className="grid gap-5 xl:grid-cols-[410px_1fr]">
   <Card className="space-y-4">
    <label className="text-sm font-medium">Nome da rota<input className="mt-1 h-10 w-full rounded-lg border border-border px-3" value={name} onChange={e=>setName(e.target.value)}/></label>
    <div className="grid grid-cols-2 gap-3"><label className="text-sm font-medium">Modo<select className="mt-1 h-10 w-full rounded-lg border border-border bg-surface px-3" value={mode} onChange={e=>setMode(e.target.value)}><option value="driving-car">Carro</option><option value="foot-walking">A pé</option></select></label><label className="text-sm font-medium">Estratégia<select className="mt-1 h-10 w-full rounded-lg border border-border bg-surface px-3" value={strategy} onChange={e=>setStrategy(e.target.value)}>{strategies.map(([v,n])=><option key={v} value={v}>{n}</option>)}</select></label></div>
    <div className="grid grid-cols-3 gap-2"><label className="text-xs font-medium">Tempo (min)<input type="number" className="mt-1 h-10 w-full rounded-lg border border-border px-2" value={available} onChange={e=>setAvailable(Number(e.target.value))}/></label><label className="text-xs font-medium">Visita (min)<input type="number" className="mt-1 h-10 w-full rounded-lg border border-border px-2" value={visit} onChange={e=>setVisit(Number(e.target.value))}/></label><label className="text-xs font-medium">Máx. paradas<input type="number" className="mt-1 h-10 w-full rounded-lg border border-border px-2" value={maxStops} onChange={e=>setMaxStops(Number(e.target.value))}/></label></div>
    <div className="grid grid-cols-2 gap-2"><label className="text-xs font-medium">Responsável<select className="mt-1 h-10 w-full rounded-lg border border-border bg-surface px-2" value={assignedTo} onChange={e=>{setAssignedTo(e.target.value);setPlan(null)}}><option value="">Todos</option>{(team.data||[]).map(x=><option key={x}>{x}</option>)}</select></label><label className="text-xs font-medium">Campanha<select className="mt-1 h-10 w-full rounded-lg border border-border bg-surface px-2" value={campaign} onChange={e=>{setCampaign(e.target.value);setPlan(null)}}><option value="">Todas</option>{campaignOptions.map(x=><option key={x} value={x}>{x}</option>)}</select></label></div>
    <label className="text-xs font-medium">Prioridade mínima: {minScore}<input type="range" min="0" max="100" step="5" className="mt-2 w-full" value={minScore} onChange={e=>{setMinScore(Number(e.target.value));setPlan(null)}}/></label>
    <Button variant="secondary" className="w-full" onClick={()=>currentPos().catch(()=>alert('Não foi possível acessar sua localização.'))}><MapPin className="h-4 w-4"/>Usar minha localização</Button>
    <div className="rounded-xl border border-border p-3"><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={returnToStart} onChange={e=>{setReturnToStart(e.target.checked);if(e.target.checked)setEnd(null)}}/>Voltar ao ponto inicial</label><label className="mt-3 flex items-center gap-2 text-sm"><input type="checkbox" checked={!!end} disabled={returnToStart} onChange={e=>setEnd(e.target.checked?[origin[0],origin[1]]:null)}/>Usar destino final diferente</label>{end&&<div className="mt-2 grid grid-cols-2 gap-2"><input type="number" step="any" className="h-9 rounded-lg border border-border px-2 text-xs" value={end[0]} onChange={e=>setEnd([Number(e.target.value),end[1]])}/><input type="number" step="any" className="h-9 rounded-lg border border-border px-2 text-xs" value={end[1]} onChange={e=>setEnd([end[0],Number(e.target.value)])}/><p className="col-span-2 text-[11px] text-muted">Latitude e longitude do destino final. Pode ser casa, escritório ou outro compromisso.</p></div>}</div>
    <Button className="w-full" disabled={!selected.length||calc.isPending} onClick={()=>calc.mutate()}>{calc.isPending?'Calculando...':'Recalcular rota'}</Button>
    <Button variant="secondary" className="w-full" disabled={!selected.length||save.isPending} onClick={()=>save.mutate()}>{save.isPending?'Salvando...':'Salvar rota de hoje'}</Button>
    <div className="grid grid-cols-2 gap-2 rounded-xl bg-background p-3 text-sm"><div><span className="block text-xs text-muted">MRR potencial selecionado</span><b>{money(chosen.reduce((a,l)=>a+(l.estimated_mrr||0),0))}</b></div><div><span className="block text-xs text-muted">Valor esperado da rota</span><b className="text-primary">{money(expectedMrr)}</b></div></div>
    {plan&&<div className="rounded-xl bg-primary-soft p-3 text-sm text-primary"><div className="flex flex-wrap items-center justify-between gap-2"><b>{plan.schedule.length} paradas · {plan.used_minutes} min</b>{previousPlan&&<span className={`text-xs font-semibold ${timeDelta<0?'text-success':timeDelta>0?'text-warning':'text-muted'}`}>{timeDelta===0?'mesmo tempo':timeDelta<0?`${Math.abs(timeDelta)} min a menos`:`${timeDelta} min a mais`}{stopDelta!==0?` · ${stopDelta>0?'+':''}${stopDelta} parada(s)`:''}</span>}</div><div className="mt-1">{plan.distance_m?`${(plan.distance_m/1000).toFixed(1)} km · `:''}${plan.strategy||strategy}</div>{plan.exceeds_window&&<div className="mt-1 font-semibold text-danger">Paradas obrigatórias ultrapassam a janela de tempo.</div>}</div>}
    <div className="border-t border-border pt-4"><p className="text-sm font-semibold">Adicionar estabelecimento</p><input className="mt-2 h-10 w-full rounded-lg border border-border px-3" placeholder="Buscar nesta fonte" value={search} onChange={e=>setSearch(e.target.value)}/><div className="mt-2 max-h-44 space-y-1 overflow-auto">{candidates.map(l=><button key={l.business_key} className="w-full rounded-lg p-2 text-left text-sm hover:bg-surface-hover" onClick={()=>{setSelected(v=>[...v,l.business_key]);setSearch('');setPlan(null)}}><b>{l.name}</b><span className="block text-xs text-muted">Prioridade {l.visit_priority_score||0} · {l.next_best_action?.label||'avaliar'}</span></button>)}</div></div>
   </Card>
   <Card className="p-2"><RoutePlannerMap origin={origin} end={end} leads={chosen} schedule={plan?.schedule} line={routeLine}/></Card>
  </div>

  <div className="grid gap-5 xl:grid-cols-[1fr_360px]">
   <Card><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-semibold">Paradas selecionadas</h2><p className="mt-1 text-sm text-muted">Arraste para ordenar. Remover daqui não apaga o lead do CRM.</p></div><div className="flex gap-2"><Badge tone="neutral">{leads.length} elegíveis</Badge><Badge tone="primary">{selected.length} selecionados</Badge></div></div><div className="mt-4 space-y-2">{chosen.map((l,i)=><div key={l.business_key} draggable onDragStart={()=>setDrag(l.business_key)} onDragOver={e=>e.preventDefault()} onDrop={()=>{if(drag&&drag!==l.business_key)move(drag,l.business_key);setDrag(null)}} className="flex items-start gap-3 rounded-xl border border-border p-3"><GripVertical className="mt-1 h-5 w-5 cursor-grab text-subtle"/><div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-primary-soft text-sm font-bold text-primary">{i+1}</div><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><b>{l.name}</b>{fixed.includes(l.business_key)&&<Badge tone="warning">Obrigatório</Badge>}<Badge tone={(l.visit_priority_score||0)>=75?'primary':'neutral'}>{l.visit_priority_score||0}</Badge></div><p className="mt-1 text-xs text-muted">{l.address}</p><p className="mt-2 text-xs text-muted">{l.why_approach||l.next_best_action?.reason}</p>{l.notes&&<p className="mt-2 rounded-lg bg-background p-2 text-xs"><b>Nota:</b> {l.notes}</p>}<p className="mt-2 text-[11px] text-subtle">Valor esperado aproximado: {money((l.estimated_mrr||0)*((l.conversion_probability||0)/100))}</p>{scheduleByKey.get(l.business_key)&&<p className={`mt-1 text-[11px] ${scheduleByKey.get(l.business_key)?.open_at_arrival===false?'font-semibold text-danger':'text-subtle'}`}>Chegada {scheduleByKey.get(l.business_key)?.arrival?new Date(scheduleByKey.get(l.business_key)!.arrival!).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'}):'estimada'} · {scheduleByKey.get(l.business_key)?.open_at_arrival===false?'provavelmente fechado':'horário compatível'}{scheduleByKey.get(l.business_key)?.opening_hours_text?` · ${scheduleByKey.get(l.business_key)?.opening_hours_text}`:''}</p>}</div><div className="flex gap-1"><button title="Fixar" className="rounded-lg p-2 hover:bg-surface-hover" onClick={()=>toggleFixed(l.business_key)}>{fixed.includes(l.business_key)?<Lock className="h-4 w-4 text-warning"/>:<LockOpen className="h-4 w-4 text-muted"/>}</button><button title="Remover só desta rota" className="rounded-lg p-2 hover:bg-danger-soft" onClick={()=>remove(l.business_key)}><X className="h-4 w-4 text-danger"/></button><button title="Descartar permanentemente" className="rounded-lg p-2 hover:bg-danger-soft" onClick={()=>{if(confirm(`Descartar ${l.name} e marcar como não contatar?`)){discard.mutate(l);remove(l.business_key,'Descartado permanentemente')}}}><Trash2 className="h-4 w-4 text-danger"/></button></div></div>)}{!chosen.length&&<p className="text-sm text-muted">Escolha um processamento e clique em “Selecionar sugeridos”, ou adicione estabelecimentos manualmente.</p>}</div></Card>
   <div className="space-y-5">
    <Card><h2 className="font-semibold">Ficaram de fora</h2><p className="mt-1 text-xs text-muted">O sistema explica por que uma parada não entrou no plano calculado.</p><div className="mt-3 max-h-64 space-y-2 overflow-auto">{omitted.map(o=><div key={`${o.business_key}-${o.reason}`} className="rounded-lg border border-border p-3"><b className="text-sm">{o.name||byKey.get(o.business_key)?.name||o.business_key}</b><p className="mt-1 text-xs text-muted">{o.reason}</p></div>)}{!omitted.length&&<p className="text-sm text-muted">Recalcule a rota para ver a análise.</p>}</div></Card>
    <Card><h2 className="font-semibold">Excluídos manualmente</h2><p className="mt-1 text-xs text-muted">Continuam no CRM.</p><div className="mt-3 space-y-2">{Object.entries(excluded).map(([k,reason])=>{const l=byKey.get(k);return <div key={k} className="rounded-lg border border-border p-3"><b className="text-sm">{l?.name||k}</b><p className="text-xs text-muted">{reason}</p><button className="mt-2 text-xs font-semibold text-primary" onClick={()=>{setExcluded(v=>{const n={...v};delete n[k];return n});setSelected(v=>[...v,k])}}><RotateCcw className="mr-1 inline h-3 w-3"/>Voltar para rota</button></div>})}{!Object.keys(excluded).length&&<p className="text-sm text-muted">Nenhum.</p>}</div></Card>
    <Card><h2 className="font-semibold">Rotas salvas</h2><div className="mt-3 space-y-2">{(saved.data||[]).slice(0,6).map(r=><div key={r.id} className="rounded-lg border border-border p-3"><b className="text-sm">{r.name}</b><p className="text-xs text-muted">{r.route_date} · {r.mode==='foot-walking'?'A pé':'Carro'} · {r.strategy}</p></div>)}</div></Card>
   </div>
  </div>
 </div>
}
