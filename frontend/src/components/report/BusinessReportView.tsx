import {useMemo,useState} from 'react'
import type {Report} from '@/types'
import {Card} from '@/components/ui/Card'
import {Badge} from '@/components/ui/Badge'
import {AlertTriangle,CheckCircle2,Globe2,Printer,Share2,TrendingUp,Presentation,Minimize2,QrCode,Sparkles} from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
} from 'recharts'
import {Button} from '@/components/ui/Button'
import {API_BASE} from '@/services/api'

const pct=(v:any)=>`${Number(v||0).toFixed(0)}%`
const score=(v:any)=>Math.max(0,Math.min(100,Number(v||0)))
const metrics=[
  ['website_pct','Site'],
  ['functional_site_pct','Site funcional'],
  ['booking_pct','Agenda online'],
  ['catalog_pct','Catálogo/serviços'],
  ['whatsapp_pct','WhatsApp'],
  ['structured_data_pct','Dados estruturados'],
] as const

export function BusinessReportView({r,publicMode=false,onShare}:{r:Report;publicMode?:boolean;onShare?:()=>void}){
  const[ticket,setTicket]=useState(80)
  const[presentation,setPresentation]=useState(false)
  const[lost,setLost]=useState(8)
  const[conversion,setConversion]=useState(35)
  const opportunity=useMemo(()=>ticket*lost,[ticket,lost])
  const recovered=useMemo(()=>opportunity*conversion/100,[opportunity,conversion])
  const l=r.lead
  const publicUrl=publicMode&&typeof window!=='undefined'?window.location.href:''
  const qrUrl=publicUrl?`${API_BASE}/api/public/qr?data=${encodeURIComponent(publicUrl)}`:''
  const leadScore=score(l.digital_maturity_score)

  const presenceChart=metrics.slice(0,5).map(([k,name])=>({
    name,
    raio:Number((r.area_metrics as any)[k]||0),
    segmento:Number((r.segment_metrics as any)[k]||0),
    cidadeSegmento:Number((r.city_segment_metrics as any)[k]||0),
  }))

  const scoreChart=useMemo(()=>{
    const candidates=[
      {name:'Este estabelecimento',score:leadScore,kind:'lead'},
      {name:'Média no raio',score:r.area_metrics.digital_maturity_avg,kind:'peer'},
      {name:'Mesmo segmento no raio',score:r.segment_metrics.digital_maturity_avg,kind:'peer'},
      {name:'Média da cidade',score:r.city_metrics.digital_maturity_avg,kind:'peer'},
      {name:'Mesmo segmento na cidade',score:r.city_segment_metrics.digital_maturity_avg,kind:'peer'},
      {name:'Bairro / área',score:r.district_metrics.digital_maturity_avg,kind:'peer'},
    ]
    return candidates
      .filter(x=>x.kind==='lead'||(x.score!==null&&x.score!==undefined&&Number.isFinite(Number(x.score))))
      .map(x=>({...x,score:score(x.score)}))
  },[leadScore,r])


  const radarData=useMemo(()=>[
    {axis:'Site',negocio:l.website?100:0,mercado:Number(r.area_metrics.website_pct||0)},
    {axis:'Agenda',negocio:l.has_booking?100:l.manual_booking_detected?45:0,mercado:Number(r.area_metrics.booking_pct||0)},
    {axis:'Catálogo',negocio:l.has_catalog?100:0,mercado:Number(r.area_metrics.catalog_pct||0)},
    {axis:'Contato',negocio:(l.has_whatsapp||l.phone)?100:0,mercado:Number(r.area_metrics.whatsapp_pct||0)},
    {axis:'Estrutura',negocio:l.has_structured_data?100:0,mercado:Number(r.area_metrics.structured_data_pct||0)},
    {axis:'Busca IA',negocio:Number(l.ai_search_readiness_score||0),mercado:Number(r.area_metrics.ai_readiness_avg||0)},
  ],[l,r])
  const percentile=Number(r.benchmark.percentile||0)
  const quartile=percentile>=75?'Top 25%':percentile>=50?'2º quartil':percentile>=25?'3º quartil':'Bottom 25%'

  const areaAvg=score(r.area_metrics.digital_maturity_avg)
  const delta=Math.round(leadScore-areaAvg)
  const deltaText=delta===0
    ? 'na mesma faixa da média do raio'
    : delta>0
      ? `${Math.abs(delta)} pontos acima da média do raio`
      : `${Math.abs(delta)} pontos abaixo da média do raio`

  return <div className={`report-root space-y-6 print:bg-white ${presentation?'presentation-mode':''}`}>
    <div className="no-print flex flex-wrap justify-end gap-2">
      <Button variant="secondary" onClick={()=>setPresentation(x=>!x)}>{presentation?<><Minimize2 className="h-4 w-4"/>Sair da apresentação</>:<><Presentation className="h-4 w-4"/>Modo apresentação</>}</Button>
      <Button variant="secondary" onClick={()=>window.print()}><Printer className="h-4 w-4"/>Imprimir / salvar PDF</Button>
      {!publicMode&&onShare&&<Button onClick={onShare}><Share2 className="h-4 w-4"/>Criar link para o estabelecimento</Button>}
    </div>

    <section className="rounded-2xl border border-border bg-surface p-6 print-card report-cover">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[.18em] text-primary">BeeSys · diagnóstico comparativo</p>
          <h1 className="mt-2 text-3xl font-bold">{l.name}</h1>
          <p className="mt-1 text-sm text-muted">{l.address}</p>
          <p className="mt-2 text-sm text-muted">Segmento: {r.context.segment} · Amostra do raio: {r.context.sample_size} negócios</p><p className="mt-1 text-xs text-subtle">Diagnóstico gerado por BeeSys Lead Search · {new Date().toLocaleDateString('pt-BR')}</p>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-xl bg-primary-soft p-4 text-center">
            <p className="text-xs text-primary">Maturidade digital</p>
            <p className="mt-1 text-3xl font-bold text-primary">{leadScore}</p>
            <p className="text-[11px] text-primary">de 100</p>
          </div>
          <div className="rounded-xl bg-background p-4 text-center">
            <p className="text-xs text-muted">Posição no raio</p>
            <p className="mt-1 text-2xl font-bold">{r.benchmark.digital_maturity_rank}º</p>
            <p className="text-xs text-muted">de {r.benchmark.sample_size}</p>
          </div>
        </div>
      </div>
      {publicMode&&qrUrl&&<div className="mt-5 flex flex-wrap items-center justify-between gap-4 rounded-xl border border-border bg-background p-4"><div><div className="flex items-center gap-2"><QrCode className="h-4 w-4 text-primary"/><b className="text-sm">Abrir este diagnóstico no celular</b></div><p className="mt-1 max-w-xl text-xs text-muted">Este QR aponta para o link público deste relatório. A validade do link continua sendo controlada pela BeeSys.</p></div><img src={qrUrl} alt="QR Code do relatório público" className="h-24 w-24 rounded-lg bg-white p-1"/></div>}
      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-border p-4">
          <p className="text-xs text-muted">Posição relativa</p>
          <p className="mt-1 text-2xl font-bold">{pct(r.benchmark.percentile)}</p>
          <p className="text-xs text-muted">à frente · {quartile}</p>
        </div>
        <div className="rounded-xl border border-border p-4">
          <p className="text-xs text-muted">Posição na cidade</p>
          <p className="mt-1 text-2xl font-bold">{r.city_benchmark.digital_maturity_rank}º</p>
          <p className="text-xs text-muted">em {r.city_benchmark.sample_size} analisados</p>
        </div>
        <div className="rounded-xl border border-border p-4">
          <p className="text-xs text-muted">Mesmo segmento no raio</p>
          <p className="mt-1 text-2xl font-bold">{r.segment_benchmark.digital_maturity_rank}º</p>
          <p className="text-xs text-muted">em {r.segment_benchmark.sample_size} semelhantes</p>
        </div>
      </div>
    </section>

    {r.context.sample_size<10&&<section className="rounded-xl border border-warning/30 bg-warning-soft p-4 print-card"><div className="flex gap-3"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning"/><div><b className="text-sm text-warning">Amostra pequena</b><p className="mt-1 text-xs leading-5 text-muted">Esta comparação usa apenas {r.context.sample_size} negócios no raio. Os percentuais devem ser interpretados como indicativos, não como retrato definitivo do mercado.</p></div></div></section>}

    <Card className="print-card score-comparison-card">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-semibold">Score deste estabelecimento comparado ao mercado</h2>
          <p className="mt-1 text-sm text-muted">O score abaixo mede maturidade digital. Quanto maior, mais completa é a presença digital identificada.</p>
        </div>
        <div className={`rounded-lg px-3 py-2 text-sm font-semibold ${delta<0?'bg-danger-soft text-danger':delta>0?'bg-success-soft text-success':'bg-background text-muted'}`}>
          {deltaText}
        </div>
      </div>
      <div className="report-score-chart mt-5 h-[330px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={scoreChart} layout="vertical" margin={{top:4,right:36,bottom:4,left:28}}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false}/>
            <XAxis type="number" domain={[0,100]} tickCount={6}/>
            <YAxis type="category" dataKey="name" width={168} tick={{fontSize:12}}/>
            <Tooltip formatter={(value:any)=>[`${Number(value).toFixed(0)}/100`,'Maturidade digital']}/>
            <Bar dataKey="score" name="Maturidade digital" radius={[0,6,6,0]} barSize={24}>
              {scoreChart.map((entry,index)=><Cell key={`${entry.name}-${index}`} fill={entry.kind==='lead'?'#4338ca':'#a8a8b3'}/>) }
              <LabelList dataKey="score" position="right" formatter={(value:any)=>`${Number(value).toFixed(0)}`}/>
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-2 text-xs text-muted">Este estabelecimento aparece em destaque. As demais barras são médias dos grupos comparáveis encontrados na análise.</p>
    </Card>

    <Card className="print-card">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><h2 className="font-semibold">Radar de maturidade digital</h2><p className="mt-1 text-sm text-muted">Comparação visual entre o estabelecimento e a média dos negócios do raio.</p></div>
        <Badge tone={percentile>=75?'success':percentile>=50?'primary':percentile>=25?'warning':'danger'}>{quartile}</Badge>
      </div>
      <div className="mt-4 h-[360px]">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={radarData} outerRadius="72%">
            <PolarGrid/>
            <PolarAngleAxis dataKey="axis" tick={{fontSize:12}}/>
            <PolarRadiusAxis domain={[0,100]} tickCount={5} tick={{fontSize:10}}/>
            <Radar name="Este estabelecimento" dataKey="negocio" stroke="#4338ca" fill="#4338ca" fillOpacity={0.22}/>
            <Radar name="Média do raio" dataKey="mercado" stroke="#a8a8b3" fill="#a8a8b3" fillOpacity={0.12}/>
            <Legend/>
            <Tooltip formatter={(value:any)=>`${Number(value).toFixed(0)}/100`}/>
          </RadarChart>
        </ResponsiveContainer>
      </div>
      <p className="text-xs text-muted">Leitura BeeSys: os eixos representam presença digital observável. Não é uma métrica oficial de buscadores.</p>
    </Card>

    {r.ai_search_alert&&<section className="rounded-2xl border border-red-200 bg-danger-soft p-5 print-card">
      <div className="flex gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-danger"/>
        <div>
          <h2 className="font-semibold text-danger">{r.ai_search_alert.title}</h2>
          <p className="mt-2 text-sm leading-6 text-red-900">{r.ai_search_alert.message}</p>
          <p className="mt-2 text-xs text-red-800">Este alerta não significa que a empresa deixará de aparecer no Google. Ele indica menor controle sobre conteúdo próprio rastreável e indexável, num cenário em que AI Overviews e AI Mode usam conteúdo do índice da Pesquisa.</p>
          <div className="mt-3 flex flex-wrap gap-3 no-print">{r.ai_search_alert.sources.map(x=><a key={x.url} className="text-xs font-semibold text-danger underline" target="_blank" rel="noreferrer" href={x.url}>{x.title}</a>)}</div>
        </div>
      </div>
    </section>}

    <Card className="print-card report-comparison-table presentation-secondary">
      <h2 className="font-semibold">Como o estabelecimento se compara</h2>
      <p className="mt-1 text-sm text-muted">Os percentuais representam a amostra realmente encontrada pelas fontes configuradas. “Não identificado” não é tratado como certeza absoluta de ausência.</p>
      <div className="mt-5 overflow-x-auto">
        <table className="w-full min-w-[900px] text-left text-sm">
          <thead className="border-b border-border text-muted"><tr><th className="pb-3">Grupo comparado</th>{metrics.map(([,n])=><th key={n} className="pb-3">{n}</th>)}</tr></thead>
          <tbody>{r.comparisons.map(c=><tr key={c.key} className="border-b border-border last:border-0"><td className="py-3 pr-4"><b>{c.label}</b><p className="text-xs text-muted">{c.sample_size} negócios</p></td>{metrics.map(([k])=><td key={k} className="py-3">{pct((c.metrics as any)[k])}</td>)}</tr>)}</tbody>
        </table>
      </div>
    </Card>

    <div className="grid gap-5 lg:grid-cols-2">
      <Card className="print-card">
        <h2 className="font-semibold">Presença digital: raio, segmento e cidade</h2>
        <p className="mt-1 text-sm text-muted">Percentual dos negócios em que cada recurso foi identificado.</p>
        <div className="report-presence-chart mt-5 h-80">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={presenceChart}>
              <CartesianGrid strokeDasharray="3 3"/>
              <XAxis dataKey="name"/>
              <YAxis domain={[0,100]} unit="%"/>
              <Tooltip/>
              <Legend/>
              <Bar dataKey="raio" name="Raio" fill="#4338ca" radius={[4,4,0,0]}/>
              <Bar dataKey="segmento" name="Mesmo segmento no raio" fill="#e8a91b" radius={[4,4,0,0]}/>
              <Bar dataKey="cidadeSegmento" name="Mesmo segmento na cidade" fill="#16a34a" radius={[4,4,0,0]}/>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card className="print-card">
        <h2 className="font-semibold">Onde existe espaço para evoluir</h2>
        <div className="mt-4 space-y-3">{r.gaps.length?r.gaps.map(g=><div key={g.title} className="rounded-xl border border-border p-4"><div className="flex items-center gap-2"><Badge tone={g.severity==='high'?'danger':g.severity==='medium'?'warning':'neutral'}>{g.severity==='high'?'Prioridade alta':g.severity==='medium'?'Atenção':'Oportunidade'}</Badge><b className="text-sm">{g.title}</b></div><p className="mt-2 text-sm leading-6 text-muted">{g.detail}</p></div>):<div className="flex gap-3 rounded-xl bg-success-soft p-4"><CheckCircle2 className="h-5 w-5 text-success"/><p className="text-sm text-success">O estabelecimento já apresenta boa cobertura nos principais sinais analisados.</p></div>}</div>
      </Card>
    </div>

    <div className="grid gap-4 md:grid-cols-3">
      <Card className="print-card"><p className="text-sm text-muted">Este negócio</p><p className="mt-2 text-3xl font-bold">{l.website?'Site identificado':'Site não identificado'}</p><p className="mt-2 text-sm text-muted">Na região, {pct(r.area_metrics.website_pct)} possuem site identificado.</p></Card>
      <Card className="print-card"><p className="text-sm text-muted">Agendamento</p><p className="mt-2 text-3xl font-bold">{l.has_booking?'Online':l.manual_booking_detected?'Manual':'Não identificado'}</p><p className="mt-2 text-sm text-muted">No mesmo segmento no raio, {pct(r.segment_metrics.booking_pct)} já têm agendamento online identificado.</p></Card>
      <Card className="print-card"><p className="text-sm text-muted">Prontidão para busca com IA</p><p className="mt-2 text-3xl font-bold">{l.ai_search_readiness_score||0}/100</p><p className="mt-2 text-sm text-muted">Indicador BeeSys; não é métrica oficial do Google.</p></Card>
    </div>

    <Card className="print-card"><div className="flex items-center gap-2"><Sparkles className="h-5 w-5 text-primary"/><h2 className="font-semibold">Como a BeeSys pode atuar nestas lacunas</h2></div><p className="mt-1 text-sm text-muted">As sugestões abaixo ligam problemas observados a soluções possíveis. A recomendação final deve considerar a rotina e a prioridade do estabelecimento.</p><div className="mt-4 grid gap-3 md:grid-cols-2">{r.gaps.map((g:any)=>{const pain=(l.pains||[]).find(p=>p.label===g.title);const solution=(pain&&r.solution_map?.[pain.code])||(/agenda|agendamento/i.test(g.title)?r.solution_map?.NO_BOOKING:/site/i.test(g.title)?r.solution_map?.NO_WEBSITE:/catálogo|serviço/i.test(g.title)?r.solution_map?.NO_CATALOG:undefined);return <div key={`solution-${g.title}`} className="rounded-xl border border-border p-4"><b className="text-sm">{g.title}</b><p className="mt-1 text-xs leading-5 text-muted">{solution||'Revisar o fluxo atual e configurar somente os módulos BeeSys que resolvam uma dor comprovada.'}</p></div>})}</div></Card>

    {r.evolution?.changes&&r.evolution.changes.length>0&&<Card className="print-card"><h2 className="font-semibold">Evolução desde análises anteriores</h2><p className="mt-1 text-sm text-muted">Mudanças observadas entre o snapshot mais antigo disponível e a situação atual.</p><div className="mt-4 grid gap-3 md:grid-cols-2">{r.evolution.changes.slice(0,8).map(c=><div key={c.field} className="rounded-xl border border-border p-3"><p className="text-xs font-semibold uppercase text-muted">{c.field}</p><div className="mt-2 grid grid-cols-[1fr_auto_1fr] items-center gap-2 text-sm"><span className="rounded-lg bg-background p-2 text-center">{String(c.before??'não identificado')}</span><span className="text-muted">→</span><span className="rounded-lg bg-success-soft p-2 text-center text-success">{String(c.after??'não identificado')}</span></div></div>)}</div></Card>}

    <Card className="print-card report-opportunity-simulator presentation-secondary">
      <div className="flex items-start gap-3">
        <TrendingUp className="mt-0.5 h-5 w-5 text-primary"/>
        <div className="flex-1">
          <h2 className="font-semibold">Simulador de oportunidade</h2>
          <p className="mt-1 text-sm text-muted">Use números do próprio estabelecimento. O cálculo é um cenário, não uma promessa de resultado.</p>

          <div className="no-print mt-4 grid gap-3 sm:grid-cols-3">
            <label className="text-sm">Ticket médio (R$)<input type="number" className="mt-1 h-10 w-full rounded-lg border border-border px-3" value={ticket} onChange={e=>setTicket(Number(e.target.value))}/></label>
            <label className="text-sm">Oportunidades perdidas/mês<input type="number" className="mt-1 h-10 w-full rounded-lg border border-border px-3" value={lost} onChange={e=>setLost(Number(e.target.value))}/></label>
            <label className="text-sm">Recuperação estimada (%)<input type="number" min="0" max="100" className="mt-1 h-10 w-full rounded-lg border border-border px-3" value={conversion} onChange={e=>setConversion(Number(e.target.value))}/></label>
          </div>

          <div className="print-only mt-3 text-xs text-muted">
            Cenário utilizado: ticket médio de R$ {ticket.toLocaleString('pt-BR',{minimumFractionDigits:2})}, {lost} oportunidades/mês e recuperação estimada de {conversion}%.
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl bg-background p-4"><p className="text-xs text-muted">Receita associada às oportunidades informadas</p><p className="mt-1 text-2xl font-bold">R$ {opportunity.toLocaleString('pt-BR',{minimumFractionDigits:2})}</p></div>
            <div className="rounded-xl bg-primary-soft p-4"><p className="text-xs text-primary">Cenário de receita recuperada</p><p className="mt-1 text-2xl font-bold text-primary">R$ {recovered.toLocaleString('pt-BR',{minimumFractionDigits:2})}/mês</p></div>
          </div>
        </div>
      </div>
    </Card>

    <Card className="print-card">
      <h2 className="font-semibold">Cenário de evolução com digitalização</h2>
      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">{[
        ['Agenda',l.has_booking?'Já possui':'Organizar horários online'],
        ['Lembretes','Automatizar confirmações e retornos'],
        ['Serviços',l.has_catalog?'Já apresenta':'Apresentar catálogo/serviços'],
        ['Presença digital',l.website?'Melhorar estrutura e indexabilidade':'Criar presença própria rastreável'],
      ].map(([a,b])=><div key={a} className="rounded-xl border border-border p-4"><p className="text-xs font-semibold uppercase text-muted">{a}</p><p className="mt-2 text-sm font-medium">{b}</p></div>)}</div>
    </Card>

    <Card className="print-card report-disclaimer presentation-secondary">
      <div className="flex items-start gap-3">
        <Globe2 className="mt-0.5 h-5 w-5 text-primary"/>
        <div><h2 className="font-semibold">Como interpretar este relatório</h2><p className="mt-2 text-sm leading-6 text-muted">{r.disclaimer} A comparação serve para mostrar posição digital relativa e oportunidades práticas. Os dados podem variar conforme cobertura das fontes, data da coleta e disponibilidade pública das informações.</p></div>
      </div>
    </Card>

    <div className="print-only border-t border-border pt-3 text-center text-[10px] text-muted">BeeSys Lead Search · Diagnóstico de presença digital · {l.name}</div>
  </div>
}
