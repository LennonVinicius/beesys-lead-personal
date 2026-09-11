import type {Lead} from '@/types'

export const leadTags=(lead:Lead)=>{
  const tags:string[]=[]
  if((lead.visit_priority_score||0)>=80)tags.push('Alta prioridade')
  if(!lead.website)tags.push('Sem site')
  else if(lead.site_functional===false)tags.push('Site com problema')
  if(lead.manual_booking_detected)tags.push('Agenda manual')
  else if(!lead.has_booking)tags.push('Sem agenda')
  if(!lead.has_catalog)tags.push('Sem catálogo')
  if(lead.competitor_detected)tags.push(`Usa ${lead.competitor_name||'concorrente'}`)
  if(lead.is_large_chain)tags.push('Grande rede')
  if(lead.aging_days!=null&&lead.aging_days>=30)tags.push('Precisa de ação')
  if(lead.pipeline_status==='CLIENT')tags.push('Cliente')
  return tags.slice(0,6)
}

export const confidenceLabel=(value?:number)=>{
  const v=Number(value||0)
  if(v>=80)return {label:'Confirmado',tone:'success' as const}
  if(v>=55)return {label:'Provável',tone:'warning' as const}
  return {label:'Não verificado',tone:'neutral' as const}
}

export const freshnessLabel=(iso?:string)=>{
  if(!iso)return 'Atualização não informada'
  const d=new Date(iso);if(Number.isNaN(d.getTime()))return 'Atualização não informada'
  const days=Math.max(0,Math.floor((Date.now()-d.getTime())/86400000))
  if(days===0)return 'Atualizado hoje'
  if(days===1)return 'Atualizado ontem'
  if(days<30)return `Atualizado há ${days} dias`
  const months=Math.floor(days/30)
  return `Atualizado há ${months} ${months===1?'mês':'meses'}`
}

export const scoreColor=(score?:number)=>{
  const v=Number(score||0)
  if(v>=80)return 'text-danger'
  if(v>=60)return 'text-warning'
  return 'text-primary'
}
