import { useState, useEffect, type FormEvent } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { HeartPulse, LayoutDashboard, Files, Activity, MessageCircle, UserRound, LogOut, Menu, ShieldCheck } from 'lucide-react'
import { api, type Patient } from './api'
import { ErrorNotice, Empty, dateLabel } from './ui'
import { Documents } from './Documents'
import { Records } from './Records'
import { Assistant } from './Assistant'
import { Profile } from './Profile'

const tabs = [
  { id: 'overview', title: 'Overview', icon: LayoutDashboard },
  { id: 'documents', title: 'Documents & review', icon: Files },
  { id: 'records', title: 'Records & trends', icon: Activity },
  { id: 'assistant', title: 'Health assistant', icon: MessageCircle },
  { id: 'profile', title: 'Profile & consent', icon: UserRound },
]
function currentTab() { const tab = window.location.hash.slice(1); return tabs.some(t => t.id === tab) ? tab : 'overview' }

function Login() {
  const client = useQueryClient()
  const [creating, setCreating] = useState(false)
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [validationError, setValidationError] = useState<Error | null>(null)
  const login = useMutation({
    mutationFn: () => creating ? api.register(fullName, email, password, confirmation) : api.login(email, password),
    onSuccess: patient => { setPassword(''); setConfirmation(''); client.removeQueries({ predicate: query => query.queryKey[0] !== 'session' }); client.setQueryData(['session'], patient) },
  })
  function submit(event: FormEvent) {
    event.preventDefault()
    if (login.isPending) return
    setValidationError(null)
    if (creating && password !== confirmation) { setValidationError(new Error('Passwords do not match.')); return }
    login.mutate()
  }
  function switchMode() {
    setCreating(!creating); setPassword(''); setConfirmation(''); setValidationError(null); login.reset()
  }
  return <main className='login-page'><section className='login-intro'>
    <div className='brand'><HeartPulse size={30} /> Personal Health Copilot</div>
    <h1>Your health records,<br />in one clear picture.</h1>
    <p>Organize your documents, verify extracted results, and ask questions grounded in your own health history.</p>
    <div className='login-points'><span><ShieldCheck /> Private records</span><span><Files /> Reviewed evidence</span><span><MessageCircle /> English & Tamil</span></div>
  </section><section className='login-card'><p className='eyebrow'>YOUR PRIVATE ACCOUNT</p><h2>{creating ? 'Create your account' : 'Welcome back'}</h2><p>{creating ? 'Enter your details to start your personal health workspace.' : 'Sign in with your email and password to open your records.'}</p>
    <form onSubmit={submit}>
    {creating && <label>Full name<input type='text' autoComplete='name' required pattern='.*\S.*' maxLength={160} disabled={login.isPending} value={fullName} onChange={e => setFullName(e.target.value)} /></label>}
    <label>Email<input type='email' autoComplete='username' required maxLength={254} disabled={login.isPending} value={email} onChange={e => setEmail(e.target.value)} /></label>
    <label><span id='account-password-label'>Password</span><input aria-labelledby='account-password-label' type='password' autoComplete={creating ? 'new-password' : 'current-password'} required minLength={creating ? 12 : undefined} maxLength={200} aria-describedby={creating ? 'password-guidance' : undefined} disabled={login.isPending} value={password} onChange={e => { setPassword(e.target.value); setValidationError(null) }} />{creating && <small id='password-guidance'>Use at least 12 characters.</small>}</label>
    {creating && <label>Confirm password<input type='password' autoComplete='new-password' required minLength={12} maxLength={200} disabled={login.isPending} value={confirmation} onChange={e => { setConfirmation(e.target.value); setValidationError(null) }} /></label>}
    <ErrorNotice error={validationError || login.error} /><button className='primary' disabled={login.isPending}>{login.isPending ? (creating ? 'Creating account…' : 'Signing in…') : (creating ? 'Create account' : 'Sign in')}</button></form>
    <p className='auth-switch'>{creating ? 'Already have an account?' : 'New here?'} <button type='button' className='link-button' disabled={login.isPending} onClick={switchMode}>{creating ? 'Sign in instead' : 'Create account'}</button></p>
  </section></main>
}

function Overview({ patient, navigate }: { patient: Patient; navigate: (tab: string) => void }) {
  const documents = useQuery({ queryKey: ['documents', 0], queryFn: () => api.documents(), refetchInterval: query => query.state.data?.some(d => ['queued', 'processing'].includes(d.processing_status)) ? 2000 : false })
  const observations = useQuery({ queryKey: ['observations'], queryFn: api.observations })
  const medications = useQuery({ queryKey: ['medications'], queryFn: api.medications })
  const docs = documents.data ?? []
  const pending = docs.filter(d => d.processing_status === 'awaiting_review')
  return <><div className='page-heading'><div><p className='eyebrow'>YOUR HEALTH WORKSPACE</p><h1>Hello, {patient.full_name.split(' ')[0]}</h1><p>Keep your records current, and understand what they say.</p></div><button className='primary' onClick={() => navigate('documents')}>Upload a document</button></div>
    <ErrorNotice error={documents.error || observations.error || medications.error} />
    <div className='stats'><article><span>Recent documents</span><strong>{docs.length}{docs.length === 50 ? '+' : ''}</strong><small>Stored in your private account</small></article><article><span>Awaiting review</span><strong>{pending.length}</strong><small>Verify before adding to your history</small></article><article><span>Reviewed results</span><strong>{observations.data?.length ?? 0}</strong><small>From confirmed documents</small></article><article><span>Active medications</span><strong>{medications.data?.filter(m => m.medication_status === 'active').length ?? 0}</strong><small>Based on your review</small></article></div>
    <div className='two-col'><section className='panel'><div className='section-heading'><h2>Recent activity</h2><button className='link-button' onClick={() => navigate('documents')}>View documents →</button></div>
      {documents.isPending ? <Empty>Loading records…</Empty> : docs.length === 0 ? <Empty>Start by uploading a laboratory report or prescription.</Empty> : docs.slice(0, 5).map(doc => <div className='activity-row' key={doc.id}><Files size={20} /><div><strong>{doc.original_filename}</strong><small>{dateLabel(doc.created_at)} · {doc.processing_status.replaceAll('_', ' ')}</small></div></div>)}</section>
    <section className='panel next-step'><p className='eyebrow'>NEXT STEP</p><h2>{pending.length ? 'Your records need a review' : 'Ask about your health history'}</h2><p>{pending.length ? 'Check the extracted values against the source document, correct anything unclear, and choose the records to confirm.' : 'The assistant cites your reviewed documents so you can check the evidence behind each answer.'}</p><button onClick={() => navigate(pending.length ? 'documents' : 'assistant')}>{pending.length ? 'Review documents' : 'Open assistant'}</button></section></div>
    {!patient.external_ai_consent && <div className='notice'>AI features send content to Laya, Sarvam, and the embedding provider with your consent. <button className='link-button' onClick={() => navigate('profile')}>Manage consent</button></div>}
    <p className='fine-print'>ABDM / ABHA integration is unavailable until official onboarding is complete.</p>
  </>
}

export default function App() {
  const client = useQueryClient()
  const session = useQuery({ queryKey: ['session'], queryFn: api.session, retry: false, refetchOnWindowFocus: true })
  const [tab, setTab] = useState(currentTab)
  const [mobileNav, setMobileNav] = useState(false)
  useEffect(() => { const changed = () => setTab(currentTab()); window.addEventListener('hashchange', changed); window.addEventListener('popstate', changed); return () => { window.removeEventListener('hashchange', changed); window.removeEventListener('popstate', changed) } }, [])
  function navigate(next: string) { window.history.pushState(null, '', '#' + next); setTab(next); setMobileNav(false) }
  const logout = useMutation({ mutationFn: api.logout, onSuccess: () => { client.clear(); client.setQueryData(['session'], null) } })
  useEffect(() => {
    const expired = () => { client.clear(); client.setQueryData(['session'], null) }
    window.addEventListener('health-session-expired', expired)
    return () => window.removeEventListener('health-session-expired', expired)
  }, [client])
  if (session.isPending) return <main className='startup'><HeartPulse /><p>Opening your workspace…</p></main>
  if (session.error) return <main className='startup'><ErrorNotice error={session.error} /><button onClick={() => session.refetch()}>Retry connection</button></main>
  const patient = session.data
  if (!patient) return <Login />
  return <div className='app-shell'><a className='skip-link' href='#main-content'>Skip to content</a><aside className={mobileNav ? 'sidebar open' : 'sidebar'}>
    <div className='brand'><HeartPulse /><span>Health Copilot<small>PERSONAL HEALTH PORTAL</small></span></div><p className='nav-label'>WORKSPACE</p>
    <nav aria-label='Workspace'>{tabs.map(item => <button key={item.id} aria-current={tab === item.id ? 'page' : undefined} className={tab === item.id ? 'active' : ''} onClick={() => navigate(item.id)}><item.icon size={19} />{item.title}</button>)}</nav>
    <div className='sidebar-bottom'><ShieldCheck size={20} /><span>Private pilot<small>Your records belong to you</small></span></div></aside>
    <div className='workspace'><header className='topbar'><button className='mobile-menu' aria-label='Toggle navigation' onClick={() => setMobileNav(!mobileNav)}><Menu /></button><span>{tabs.find(t => t.id === tab)?.title}</span><div className='account'><span>{patient.full_name}</span><button aria-label='Sign out' disabled={logout.isPending} onClick={() => logout.mutate()}><LogOut size={18} /></button></div></header>
    <main id='main-content'><ErrorNotice error={logout.error} />{tab === 'overview' ? <Overview patient={patient} navigate={navigate} /> : tab === 'documents' ? <Documents /> : tab === 'records' ? <Records /> : tab === 'assistant' ? <Assistant patient={patient} /> : <Profile key={patient.id} patient={patient} />}</main>
    <footer>Informational assistance. Review results with your clinician before making health decisions.</footer></div></div>
}
