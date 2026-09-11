import {useEffect,useState} from 'react'
import {useQuery} from '@tanstack/react-query'
import {NavLink,Outlet,useLocation,useNavigate} from 'react-router-dom'
import {
  BarChart3,
  CalendarDays,
  ClipboardList,
  Crosshair,
  LogOut,
  Map,
  MapPinned,
  Menu,
  Route,
  Settings,
  Target,
  Users,
  X,
  BrainCircuit,
  Workflow,
  ShieldCog,
  Inbox as InboxIcon,
} from 'lucide-react'
import {supabase} from '@/lib/supabase'
import {ThemeToggle} from '@/components/ui/ThemeToggle'
import {api} from '@/services/api'

const items=[
  ['Hoje','/',CalendarDays],
  ['Inbox','/inbox',InboxIcon],
  ['Dashboard','/dashboard',BarChart3],
  ['Buscar leads','/search',MapPinned],
  ['CRM','/leads',Users],
  ['Inteligência','/intelligence',BrainCircuit],
  ['Rotas','/routes',Map],
  ['Modo rua','/street',Route],
  ['Follow-ups','/followups',ClipboardList],
  ['Metas','/goals',Target],
  ['Processamentos','/jobs',Crosshair],
  ['Automações','/automations',Workflow],
  ['Administração','/admin',ShieldCog],
  ['Configurações','/settings',Settings],
] as const

function Brand(){
  return (
    <div className="flex h-20 items-center gap-3 border-b border-border px-5">
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary text-white">
        <Map className="h-5 w-5"/>
      </span>
      <div className="min-w-0 flex-1">
        <b className="block text-lg leading-tight">BeeSys</b>
        <span className="text-sm font-semibold text-primary">Lead Search</span>
      </div>
    </div>
  )
}

function Navigation({onNavigate,role}:{onNavigate?:()=>void;role?:string}){
  const visibleItems=items.filter(([label])=>{if(label==='Administração')return role==='ADMIN'||role==='MANAGER';if(label==='Automações')return role==='ADMIN'||role==='MANAGER';return true})
  return (
    <nav className="flex-1 space-y-1 overflow-y-auto p-3">
      {visibleItems.map(([label,to,Icon])=>(
        <NavLink
          key={to}
          to={to}
          end={to==='/'}
          onClick={onNavigate}
          className={({isActive})=>
            `flex min-h-11 items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
              isActive
                ? 'bg-primary-soft text-primary'
                : 'text-muted hover:bg-surface-hover hover:text-ink'
            }`
          }
        >
          <Icon className="h-[18px] w-[18px] shrink-0"/>
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  )
}

export function AppLayout(){
  const navigate=useNavigate()
  const location=useLocation()
  const [mobileOpen,setMobileOpen]=useState(false)
  const roleQuery=useQuery({queryKey:['my-role'],queryFn:()=>api.get<{email:string;role:string}>('/api/me/role'),staleTime:300000})
  const role=roleQuery.data?.role

  useEffect(()=>{
    setMobileOpen(false)
  },[location.pathname])

  useEffect(()=>{
    if(!mobileOpen) return

    const previousOverflow=document.body.style.overflow
    document.body.style.overflow='hidden'

    const onKeyDown=(event:KeyboardEvent)=>{
      if(event.key==='Escape') setMobileOpen(false)
    }

    window.addEventListener('keydown',onKeyDown)

    return ()=>{
      document.body.style.overflow=previousOverflow
      window.removeEventListener('keydown',onKeyDown)
    }
  },[mobileOpen])

  async function signOut(){
    await supabase.auth.signOut()
    setMobileOpen(false)
    navigate('/login')
  }

  return (
    <div className="min-h-screen bg-background">
      <aside className="no-print fixed inset-y-0 left-0 z-30 hidden w-[268px] flex-col border-r border-border bg-surface lg:flex">
        <Brand/>
        <Navigation role={role}/>
        <div className="mx-3 mb-1 flex justify-end"><ThemeToggle/></div>
        <button
          className="m-3 flex min-h-11 items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-muted transition-colors hover:bg-danger-soft hover:text-danger"
          onClick={signOut}
        >
          <LogOut className="h-[18px] w-[18px]"/>
          Sair
        </button>
      </aside>

      <header className="no-print fixed inset-x-0 top-0 z-40 flex h-16 items-center justify-between border-b border-border bg-surface/95 px-4 backdrop-blur lg:hidden">
        <div className="flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-primary text-white">
            <Map className="h-[18px] w-[18px]"/>
          </span>
          <div className="leading-tight">
            <b className="block text-sm">BeeSys</b>
            <span className="text-xs font-semibold text-primary">Lead Search</span>
          </div>
        </div>

        <div className="flex items-center gap-2"><ThemeToggle/><button
          type="button"
          aria-label="Abrir menu"
          aria-expanded={mobileOpen}
          aria-controls="mobile-navigation"
          onClick={()=>setMobileOpen(true)}
          className="grid h-11 w-11 place-items-center rounded-xl border border-border bg-surface text-ink transition-colors hover:bg-surface-hover"
        >
          <Menu className="h-5 w-5"/>
        </button></div>
      </header>

      <div
        aria-hidden={!mobileOpen}
        onClick={()=>setMobileOpen(false)}
        className={`no-print fixed inset-0 z-40 bg-slate-950/45 backdrop-blur-[1px] transition-opacity duration-200 lg:hidden ${
          mobileOpen
            ? 'pointer-events-auto opacity-100'
            : 'pointer-events-none opacity-0'
        }`}
      />

      <aside
        id="mobile-navigation"
        aria-hidden={!mobileOpen}
        className={`no-print fixed inset-y-0 left-0 z-50 flex w-[86vw] max-w-[320px] flex-col border-r border-border bg-surface shadow-2xl transition-transform duration-200 ease-out lg:hidden ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="relative">
          <Brand/>
          <button
            type="button"
            aria-label="Fechar menu"
            onClick={()=>setMobileOpen(false)}
            className="absolute right-3 top-[18px] grid h-11 w-11 place-items-center rounded-xl text-muted transition-colors hover:bg-surface-hover hover:text-ink"
          >
            <X className="h-5 w-5"/>
          </button>
        </div>

        <Navigation role={role} onNavigate={()=>setMobileOpen(false)}/>

        <div
          className="border-t border-border p-3"
          style={{paddingBottom:'max(0.75rem, env(safe-area-inset-bottom))'}}
        >
          <button
            className="flex min-h-11 w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-muted transition-colors hover:bg-danger-soft hover:text-danger"
            onClick={signOut}
          >
            <LogOut className="h-[18px] w-[18px]"/>
            Sair
          </button>
        </div>
      </aside>

      <main className="app-main min-h-screen pt-16 lg:pl-[268px] lg:pt-0">
        <div className="app-content mx-auto max-w-[1500px] p-4 sm:p-6 lg:p-8">
          <Outlet/>
        </div>
      </main>
    </div>
  )
}
