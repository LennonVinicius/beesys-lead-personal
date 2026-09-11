import {Link} from 'react-router-dom'
import {Star,GitCompareArrows,Clock3} from 'lucide-react'
import type {Lead} from '@/types'
import {Badge} from '@/components/ui/Badge'
import {confidenceLabel,freshnessLabel,leadTags,scoreColor} from '@/lib/leadUi'
import {PIPELINE} from '@/lib/options'

export function LeadCard({lead,jobId,favorite,onFavorite,selected,onCompare}:{lead:Lead;jobId?:string|null;favorite:boolean;onFavorite:()=>void;selected:boolean;onCompare:()=>void}){
 const confidence=confidenceLabel(lead.data_confidence)
 return <article className={`rounded-2xl border bg-surface p-4 transition-colors ${selected?'border-primary bg-primary-soft/40':'border-border hover:border-border-strong'}`}>
  <div className="flex items-start gap-3"><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><Link className="truncate font-semibold text-ink hover:text-primary" to={`/leads/${encodeURIComponent(lead.business_key)}${jobId?`?jobId=${jobId}`:''}`}>{lead.name}</Link><Badge tone={lead.is_large_chain?'danger':'neutral'}>{lead.is_large_chain?'Rede':'Local'}</Badge></div><p className="mt-1 line-clamp-1 text-xs text-muted">{lead.category||'Categoria não informada'} · {lead.address||'Endereço não informado'}</p></div><div className="text-right"><div className={`metric-number text-2xl font-bold ${scoreColor(lead.visit_priority_score)}`}>{lead.visit_priority_score??0}</div><span className="text-[10px] uppercase tracking-wide text-muted">prioridade</span></div></div>
  <div className="mt-3 flex flex-wrap gap-1.5">{leadTags(lead).map(t=><span key={t} className="rounded-full bg-background px-2 py-1 text-[11px] font-medium text-muted">{t}</span>)}</div>
  <div className="mt-4 rounded-xl bg-background p-3"><div className="flex items-start justify-between gap-3"><div><p className="text-xs font-semibold text-ink">Próxima ação</p><p className="mt-1 text-xs leading-5 text-muted">{lead.next_best_action?.label||'Analisar oportunidade'} — {lead.next_best_action?.reason||lead.why_approach||'Verificar os sinais digitais e definir abordagem.'}</p></div><Badge tone={confidence.tone}>{confidence.label}</Badge></div></div>
  <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-muted"><span className="inline-flex items-center gap-1"><Clock3 className="h-3.5 w-3.5"/>{freshnessLabel(lead.last_analyzed_at||lead.last_seen_at)}</span><span>{PIPELINE.find(x=>x[0]===lead.pipeline_status)?.[1]||lead.pipeline_status||'Novo'}</span></div>
  <div className="mt-4 flex items-center gap-2"><button type="button" onClick={onFavorite} className={`inline-flex h-9 items-center gap-1 rounded-lg border px-2.5 text-xs font-semibold ${favorite?'border-warning bg-warning-soft text-warning':'border-border text-muted hover:bg-surface-hover'}`}><Star className={`h-3.5 w-3.5 ${favorite?'fill-current':''}`}/>Favorito</button><button type="button" onClick={onCompare} className={`inline-flex h-9 items-center gap-1 rounded-lg border px-2.5 text-xs font-semibold ${selected?'border-primary bg-primary-soft text-primary':'border-border text-muted hover:bg-surface-hover'}`}><GitCompareArrows className="h-3.5 w-3.5"/>Comparar</button><Link className="ml-auto text-xs font-semibold text-primary" to={`/reports/${encodeURIComponent(lead.business_key)}${jobId?`?jobId=${jobId}`:''}`}>Relatório</Link></div>
 </article>
}
