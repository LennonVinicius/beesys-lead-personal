import { supabase } from '@/lib/supabase'
const BASE=(import.meta.env.VITE_API_URL||'http://localhost:8000').replace(/\/$/,'')
async function request<T>(path:string,init:RequestInit={}):Promise<T>{
 const {data:{session}}=await supabase.auth.getSession(); const headers=new Headers(init.headers); headers.set('Content-Type','application/json'); if(session?.access_token)headers.set('Authorization',`Bearer ${session.access_token}`)
 const r=await fetch(BASE+path,{...init,headers}); if(!r.ok){let m='Não foi possível concluir a ação.';try{const j=await r.json();m=j.detail||m}catch{} throw new Error(m)} return r.json()
}
export const api={
 get:<T>(p:string)=>request<T>(p), post:<T>(p:string,b?:unknown)=>request<T>(p,{method:'POST',body:b===undefined?undefined:JSON.stringify(b)}), patch:<T>(p:string,b:unknown)=>request<T>(p,{method:'PATCH',body:JSON.stringify(b)})
}
