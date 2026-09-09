import {useMutation,useQuery} from '@tanstack/react-query'
import {api} from '@/services/api'
import type {Report} from '@/types'
import {useParams,useSearchParams,Link} from 'react-router-dom'
import {BusinessReportView} from '@/components/report/BusinessReportView'
import {ArrowLeft} from 'lucide-react'

export function ReportPage(){const{key}=useParams();const[sp]=useSearchParams();const jobId=sp.get('jobId');const q=useQuery({queryKey:['report',key,jobId],queryFn:()=>api.get<Report>(`/api/reports/business/${key}${jobId?`?job_id=${jobId}`:''}`),enabled:!!key});const share=useMutation({mutationFn:()=>api.post<{token:string}>(`/api/reports/business/${key}/share`,{job_id:jobId?Number(jobId):null,expires_days:30}),onSuccess:d=>{const url=`${window.location.origin}/public/report/${d.token}`;navigator.clipboard?.writeText(url);prompt('Link do relatório (copiado quando permitido):',url)}});if(!q.data)return <p className="text-muted">Carregando relatório...</p>;return <div className="space-y-4"><div className="no-print"><Link to={`/leads/${encodeURIComponent(q.data.lead.business_key)}${jobId?`?jobId=${jobId}`:''}`} className="inline-flex items-center gap-2 text-sm font-medium text-muted"><ArrowLeft className="h-4 w-4"/>Voltar ao lead</Link></div><BusinessReportView r={q.data} onShare={()=>share.mutate()}/></div>}
