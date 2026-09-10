import {useEffect,useState} from 'react'
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
} from 'lucide-react'
import {supabase} from '@/lib/supabase'

const items=[
  ['Hoje','/',CalendarDays],
  ['Dashboard','/dashboard',BarChart3],
  ['Buscar leads','/search',MapPinned],
  ['CRM','/leads',Users],
  ['Rotas','/routes',Map],
  ['Modo rua','/street',Route],
  ['Follow-ups','/followups',ClipboardList],
  ['Metas','/goals',Target],
  ['Processamentos','/jobs',Crosshair],
  ['Configurações','/settings',Settings],
] as const

function Brand(){
  return (
    <div className="flex h-20 items-center gap-3 border-b border-border px-5">
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary text-white">
        <Map className="h-5 w-5"/>
      </span>
      <div>
        <b className="block text-lg leading-tight">BeeSys</b>
        <span className="text-sm font-semibold text-primary">Lead Search</span>
      </div>
    </div>
  )
}

function Navigation({onNavigate}:{onNavigate?:()=>void}){
  return (
    <nav className="flex-1 space-y-1 overflow-y-auto p-3">
      {items.map(([label,to,Icon])=>(
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
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[268px] flex-col border-r border-border bg-surface lg:flex">
        <Brand/>
        <Navigation/>
        <button
          className="m-3 flex min-h-11 items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-muted transition-colors hover:bg-danger-soft hover:text-danger"
          onClick={signOut}
        >
          <LogOut className="h-[18px] w-[18px]"/>
          Sair
        </button>
      </aside>

      <header className="fixed inset-x-0 top-0 z-40 flex h-16 items-center justify-between border-b border-border bg-surface/95 px-4 backdrop-blur lg:hidden">
        <div className="flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-primary text-white">
            <Map className="h-[18px] w-[18px]"/>
          </span>
          <div className="leading-tight">
            <b className="block text-sm">BeeSys</b>
            <span className="text-xs font-semibold text-primary">Lead Search</span>
          </div>
        </div>

        <button
          type="button"
          aria-label="Abrir menu"
          aria-expanded={mobileOpen}
          aria-controls="mobile-navigation"
          onClick={()=>setMobileOpen(true)}
          className="grid h-11 w-11 place-items-center rounded-xl border border-border bg-surface text-ink transition-colors hover:bg-surface-hover"
        >
          <Menu className="h-5 w-5"/>
        </button>
      </header>

      <div
        aria-hidden={!mobileOpen}
        onClick={()=>setMobileOpen(false)}
        className={`fixed inset-0 z-40 bg-slate-950/45 backdrop-blur-[1px] transition-opacity duration-200 lg:hidden ${
          mobileOpen
            ? 'pointer-events-auto opacity-100'
            : 'pointer-events-none opacity-0'
        }`}
      />

      <aside
        id="mobile-navigation"
        aria-hidden={!mobileOpen}
        className={`fixed inset-y-0 left-0 z-50 flex w-[86vw] max-w-[320px] flex-col border-r border-border bg-surface shadow-2xl transition-transform duration-200 ease-out lg:hidden ${
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

        <Navigation onNavigate={()=>setMobileOpen(false)}/>

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

      <main className="min-h-screen pt-16 lg:pl-[268px] lg:pt-0">
        <div className="mx-auto max-w-[1500px] p-4 sm:p-6 lg:p-8">
          <Outlet/>
        </div>
      </main>
    </div>
  )
}
