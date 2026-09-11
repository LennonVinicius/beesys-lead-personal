import {Moon,Sun} from 'lucide-react'
import {useEffect,useState} from 'react'

export function ThemeToggle(){
 const[dark,setDark]=useState(()=>localStorage.getItem('beesys_theme')==='dark')
 useEffect(()=>{document.documentElement.classList.toggle('dark',dark);localStorage.setItem('beesys_theme',dark?'dark':'light')},[dark])
 return <button type="button" aria-label="Alternar tema" onClick={()=>setDark(v=>!v)} className="grid h-10 w-10 place-items-center rounded-lg border border-border bg-surface text-muted transition-colors hover:bg-surface-hover hover:text-ink">{dark?<Sun className="h-4 w-4"/>:<Moon className="h-4 w-4"/>}</button>
}
