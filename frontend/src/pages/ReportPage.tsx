import {useMutation,useQuery} from '@tanstack/react-query'
import {api} from '@/services/api'
import type {Report} from '@/types'
import {useParams,useSearchParams,Link} from 'react-router-dom'
import {BusinessReportView} from '@/components/report/BusinessReportView'
import {ArrowLeft,Link2} from 'lucide-react'
import {useState} from 'react'

export function ReportPage(){
 const{key}=useParams();const[sp]=useSearchParams();const jobId=sp.get('jobId');const[expires,setExpires]=useState(30);const[publicUrl,setPublicUrl]=useState('')
 const q=useQuery({queryKey:['report',key,jobId],queryFn:()=>api.get<Report>(`/api/reports/business/${key}${jobId?`?job_id=${jobId}`:''}`),enabled:!!key})
 const share=useMutation({mutationFn:()=>api.post<{token:string}>(`/api/reports/business/${key}/share`,{job_id:jobId?Number(jobId):null,expires_days:expires}),onSuccess:d=>{const url=`${window.location.origin}/public/report/${d.token}`;setPublicUrl(url);navigator.clipboard?.writeText(url).catch(()=>{})}})
 if(!q.data)return <p className="text-muted">Carregando relatório...</p>
 return <div className="space-y-4"><div className="no-print flex flex-wrap items-center justify-between gap-3"><Link to={`/leads/${encodeURIComponent(q.data.lead.business_key)}${jobId?`?jobId=${jobId}`:''}`} className="inline-flex items-center gap-2 text-sm font-medium text-muted"><ArrowLeft className="h-4 w-4"/>Voltar ao lead</Link><div className="flex flex-wrap items-center gap-2"><label className="text-xs text-muted">Link válido por <select className="ml-1 h-9 rounded-lg border border-border bg-surface px-2 text-sm text-ink" value={expires} onChange={e=>setExpires(Number(e.target.value))}><option value={7}>7 dias</option><option value={30}>30 dias</option><option value={90}>90 dias</option></select></label><button onClick={()=>share.mutate()} className="inline-flex h-9 items-center gap-2 rounded-lg border border-border bg-surface px-3 text-sm font-semibold text-primary"><Link2 className="h-4 w-4"/>Gerar link público</button></div></div>{publicUrl&&<div className="no-print rounded-xl border border-success/20 bg-success-soft p-3 text-sm"><b className="text-success">Link criado</b><p className="mt-1 break-all text-xs text-muted">{publicUrl}</p></div>}<BusinessReportView r={q.data}/></div>
}
