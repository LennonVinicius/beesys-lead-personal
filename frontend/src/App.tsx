import {Routes,Route,Navigate} from 'react-router-dom'
import {AuthGuard} from '@/contexts/AuthGuard'
import {AppLayout} from '@/components/layout/AppLayout'
import {LoginPage} from '@/pages/LoginPage'
import {TodayPage} from '@/pages/TodayPage'
import {DashboardPage} from '@/pages/DashboardPage'
import {SearchPage} from '@/pages/SearchPage'
import {LeadsPage} from '@/pages/LeadsPage'
import {LeadDetailPage} from '@/pages/LeadDetailPage'
import {ReportPage} from '@/pages/ReportPage'
import {PublicReportPage} from '@/pages/PublicReportPage'
import {GoalsPage} from '@/pages/GoalsPage'
import {JobsPage} from '@/pages/JobsPage'
import {FollowupsPage} from '@/pages/FollowupsPage'
import {StreetPage} from '@/pages/StreetPage'
import {RoutesPage} from '@/pages/RoutesPage'
import {SettingsPage} from '@/pages/SettingsPage'
import {AdminPage} from '@/pages/AdminPage'
import {AutomationsPage} from '@/pages/AutomationsPage'
import {IntelligencePage} from '@/pages/IntelligencePage'
import {InboxPage} from '@/pages/InboxPage'

export default function App(){return <Routes>
 <Route path="/login" element={<LoginPage/>}/>
 <Route path="/public/report/:token" element={<PublicReportPage/>}/>
 <Route element={<AuthGuard/>}><Route element={<AppLayout/>}>
  <Route index element={<TodayPage/>}/><Route path="inbox" element={<InboxPage/>}/><Route path="dashboard" element={<DashboardPage/>}/><Route path="search" element={<SearchPage/>}/><Route path="leads" element={<LeadsPage/>}/><Route path="leads/:key" element={<LeadDetailPage/>}/><Route path="reports/:key" element={<ReportPage/>}/><Route path="intelligence" element={<IntelligencePage/>}/><Route path="automations" element={<AutomationsPage/>}/><Route path="admin" element={<AdminPage/>}/><Route path="routes" element={<RoutesPage/>}/><Route path="goals" element={<GoalsPage/>}/><Route path="jobs" element={<JobsPage/>}/><Route path="followups" element={<FollowupsPage/>}/><Route path="street" element={<StreetPage/>}/><Route path="settings" element={<SettingsPage/>}/>
 </Route></Route><Route path="*" element={<Navigate to="/" replace/>}/>
 </Routes>}
