import {useQuery} from '@tanstack/react-query'
import {useParams} from 'react-router-dom'
import {api} from '@/services/api'
import type {Report} from '@/types'
import {BusinessReportView} from '@/components/report/BusinessReportView'
export function PublicReportPage(){const{token}=useParams();const q=useQuery({queryKey:['public-report',token],queryFn:()=>api.get<Report>(`/public/reports/${token}`),enabled:!!token,retry:false});if(q.isError)return <div className="mx-auto max-w-3xl p-8"><h1 className="text-2xl font-bold">Relatório indisponível</h1><p className="mt-2 text-muted">O link pode ter expirado ou sido desativado.</p></div>;if(!q.data)return <div className="p-8 text-muted">Carregando relatório...</div>;return <main className="mx-auto max-w-[1300px] p-4 sm:p-7"><BusinessReportView r={q.data} publicMode/></main>}
