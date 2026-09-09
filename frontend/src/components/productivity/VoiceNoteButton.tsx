import {useRef,useState} from 'react'
import {Mic,Square} from 'lucide-react'
import {Button} from '@/components/ui/Button'

type Props={onText:(text:string)=>void;label?:string}
export function VoiceNoteButton({onText,label='Ditado'}:Props){
 const[active,setActive]=useState(false);const rec=useRef<any>(null)
 const start=()=>{
  const W:any=(window as any).SpeechRecognition||(window as any).webkitSpeechRecognition
  if(!W){alert('O navegador atual não oferece ditado por voz. No Android, teste pelo Chrome.');return}
  const r=new W();r.lang='pt-BR';r.continuous=false;r.interimResults=false
  r.onresult=(e:any)=>{const t=e.results?.[0]?.[0]?.transcript||'';if(t)onText(t)}
  r.onend=()=>setActive(false);r.onerror=()=>setActive(false);rec.current=r;r.start();setActive(true)
 }
 const stop=()=>{rec.current?.stop?.();setActive(false)}
 return <Button type="button" variant="secondary" onClick={active?stop:start}>{active?<><Square className="h-4 w-4"/>Parar</>:<><Mic className="h-4 w-4"/>{label}</>}</Button>
}
