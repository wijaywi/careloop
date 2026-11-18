import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { careLoopApi, type ApiAuditItem, type ApiCaseDetail, type ApiCaseSummary } from './api/client'

type Role = 'navigator' | 'clinician' | 'manager' | 'patient'
type Page = 'command' | 'case' | 'queue' | 'consult' | 'patient' | 'simulation' | 'governance'
type Stage = 'stalled' | 'escalated' | 'handoff' | 'closed'

type ActivityEntry = { at: string; label: string; detail: string; source: 'api' | 'local' }

// Shared handle to the ledger object behind the synthetic narrative. `run` performs a
// real API action and refetches the case, returning false when the API is unreachable
// so callers can still record the action locally and keep the interface responsive.
type CareApi = {
  caseId: string
  detail: ApiCaseDetail | null
  activity: ActivityEntry[]
  patientActorId: string
  actorId: string
  lastError: string
  run: (action: string, payload?: Record<string, unknown>, actor?: string) => Promise<boolean>
  log: (label: string, detail: string, source: 'api' | 'local') => void
  reload: () => Promise<void>
  select: (caseId: string) => void
  passportOpen: boolean
  setPassportOpen: (open: boolean) => void
}

const clockLabel = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })

type QueueCase = {
  id: string
  initials: string
  name: string
  need: string
  age: string
  stage: Stage
  priority: 'High' | 'Medium' | 'Low'
}

const roles: { id: Role; label: string; short: string; icon: string }[] = [
  { id: 'navigator', label: 'Navigator', short: 'Navigator', icon: '◉' },
  { id: 'clinician', label: 'Clinician', short: 'Clinician', icon: '✚' },
  { id: 'manager', label: 'Program manager', short: 'Manager', icon: '▦' },
  { id: 'patient', label: 'Patient view', short: 'Patient', icon: '♡' },
]

const stageInfo: Record<Stage, { label: string; tone: string; helper: string }> = {
  stalled: { label: 'Stalled', tone: 'red', helper: 'No appointment booked after 4 days' },
  escalated: { label: 'Escalated', tone: 'amber', helper: 'Navigator flagged for clinical review' },
  handoff: { label: 'Handoff ready', tone: 'blue', helper: 'Warm handoff sent to Riverside Clinic' },
  closed: { label: 'Closed loop', tone: 'green', helper: 'Patient confirmed the next step' },
}

const seedCases: QueueCase[] = [
  { id: 'CL-2048', initials: 'SM', name: 'Samira Malik', need: 'Food insecurity', age: '4 days', stage: 'stalled', priority: 'High' },
  { id: 'CL-2047', initials: 'JT', name: 'James Thompson', need: 'Depression screen', age: '2 days', stage: 'escalated', priority: 'High' },
  { id: 'CL-2046', initials: 'LC', name: 'Lena Chen', need: 'Housing support', age: '1 day', stage: 'handoff', priority: 'Medium' },
  { id: 'CL-2045', initials: 'OB', name: 'Omar Bashir', need: 'Transportation', age: '1 day', stage: 'stalled', priority: 'Medium' },
  { id: 'CL-2044', initials: 'RP', name: 'Rosa Perez', need: 'Food insecurity', age: 'Today', stage: 'stalled', priority: 'Low' },
]

const demoMetrics = {
  openCases: seedCases.filter(item => item.stage !== 'closed').length,
  atRisk: seedCases.filter(item => item.priority === 'High').length,
  closedThisMonth: seedCases.filter(item => item.stage === 'closed').length,
  namedOwners: seedCases.length,
}

// Values copied from `python scripts/reproduce.py --output out`, which writes
// out/reproduce.json (24 cases x 2 runs, seed 20261019). These are workflow
// model outputs, not observed clinical results.
const reproduceRun = {
  cohort: 24,
  runs: 2,
  seed: 20261019,
  closureByArm: {
    'Arm A': 0.5,
    'B-full': 0.5833,
    'B_without_closure_gate': 0.7292,
    'B_without_absence_detector': 0.5833,
    'B_without_positive_handoff': 0.5,
    'B_without_multilingual_passport': 0.5833,
  } as Record<string, number>,
  coreByArm: {
    'Arm A': 0.1458,
    'B-full': 0.5417,
  } as Record<string, number>,
  visibilityByArm: {
    'Arm A': { unknownRate: 0.0833, uncertaintyHours: 2.2, consultWithoutReferral: 0.0 },
    'B-full': { unknownRate: 0.125, uncertaintyHours: 4.3, consultWithoutReferral: 0.8333 },
  } as Record<string, { unknownRate: number; uncertaintyHours: number; consultWithoutReferral: number }>,
  backlogByArmPolicy: {
    'Arm A': { fifo: 59, priority: 59 },
    'B-full': { fifo: 83, priority: 79 },
  } as Record<string, Record<string, number>>,
}

const navItems: { id: Page; label: string; icon: string; badge?: string }[] = [
  { id: 'command', label: 'Command center', icon: '⌂' },
  { id: 'case', label: 'Case detail', icon: '◎', badge: '3' },
  { id: 'queue', label: 'Navigator queue', icon: '☷', badge: '8' },
  { id: 'consult', label: 'Consult workspace', icon: '✚' },
  { id: 'patient', label: 'Patient view', icon: '♡' },
  { id: 'simulation', label: 'Simulation lab', icon: '◇' },
]

// The role switcher selects the workspace a person works in and the actor identity
// used for read requests. It does not narrow the staff case list: the API scope rule
// only separates a patient account from staff accounts (see api/service.py,
// list_case_summaries), so the visible count is identical for the three staff roles.
const roleHome: Record<Role, Page> = { navigator: 'queue', clinician: 'consult', manager: 'governance', patient: 'patient' }
const scopeActor: Record<Role, string> = { navigator: 'navigator-1', clinician: 'clinician-1', manager: 'manager-1', patient: 'patient-01' }
const roleWorkspace: Record<Role, string> = {
  navigator: 'Operational workspace · Navigator queue',
  clinician: 'Clinical review workspace · Consult workspace',
  manager: 'Programme oversight workspace · Governance',
  patient: 'Patient portal · one synthetic patient',
}

function App() {
  const [role, setRole] = useState<Role>('navigator')
  const [page, setPage] = useState<Page>('command')
  const [stage, setStage] = useState<Stage>('stalled')
  const [demoLoaded, setDemoLoaded] = useState(false)
  const [arabic, setArabic] = useState(false)
  const [toast, setToast] = useState('')
  const [apiOnline, setApiOnline] = useState<boolean | null>(null)
  const [apiBusy, setApiBusy] = useState(false)
  const [activeCaseId, setActiveCaseId] = useState('demo-case-01')
  const [scope, setScope] = useState<{ actor: string; total: number; open: number } | null>(null)
  const [scopeNote, setScopeNote] = useState('cohort not seeded yet')
  const lastErrorRef = useRef('')
  const [cohort, setCohort] = useState<ApiCaseSummary[] | null>(null)
  const [detail, setDetail] = useState<ApiCaseDetail | null>(null)
  const [activity, setActivity] = useState<ActivityEntry[]>([])
  const [passportOpen, setPassportOpen] = useState(false)
  const [menu, setMenu] = useState<'none' | 'workspace' | 'profile' | 'bell'>('none')

  const logActivity = (label: string, itemDetail: string, source: 'api' | 'local') =>
    setActivity(current => [...current, { at: clockLabel(), label, detail: itemDetail, source }].slice(-9))

  const reloadCase = async () => {
    try {
      setDetail(await careLoopApi.getCase(activeCaseId, 'manager-1'))
    } catch {
      setDetail(null)
    }
  }

  const selectCase = (caseId: string) => setActiveCaseId(caseId)

  const runCaseAction = async (action: string, payload: Record<string, unknown> = {}, actor?: string) => {
    setApiBusy(true)
    let ok = true
    try {
      await careLoopApi.action(activeCaseId, actor ?? actorId, action, payload)
      lastErrorRef.current = ''
    } catch (error) {
      ok = false
      lastErrorRef.current = error instanceof Error ? error.message : 'request failed'
    } finally {
      setApiBusy(false)
    }
    await reloadCase()
    return ok
  }

  useEffect(() => {
    void reloadCase()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeCaseId, stage])

  const syncScope = async (nextRole: Role) => {
    const actor = scopeActor[nextRole]
    try {
      const data = await careLoopApi.listCases(actor)
      const items = data.items ?? []
      setScope({ actor, total: data.count ?? items.length, open: items.filter(item => item.status !== 'closed').length })
      setCohort(items)
      setScopeNote('')
      setApiOnline(true)
    } catch (error) {
      setScope(null)
      setScopeNote(error instanceof Error ? error.message : 'read scope request failed')
    }
  }

  useEffect(() => {
    careLoopApi.health()
      .then(() => {
        setApiOnline(true)
        void syncScope('navigator')
      })
      .catch(() => setApiOnline(false))
  }, [])

  const toastTimer = useRef<number | undefined>(undefined)

  // A single timeout: a new message replaces the visible one instead of an older
  // timer clearing the newer message off the screen.
  const notify = (message: string) => {
    setToast(message)
    window.clearTimeout(toastTimer.current)
    toastTimer.current = window.setTimeout(() => setToast(''), 4200)
  }

  const loadDemo = async () => {
    setApiBusy(true)
    setDemoLoaded(true)
    setStage('stalled')
    setActivity([])
    try {
      await careLoopApi.seedDemo()
      setApiOnline(true)
      const list = await careLoopApi.listCases('manager-1')
      const open = list.items.find(item => item.status !== 'closed')
      const nextId = open?.id ?? 'demo-case-01'
      setActiveCaseId(nextId)
      setCohort(list.items)
      setScope({ actor: 'manager-1', total: list.count ?? list.items.length, open: list.items.filter(item => item.status !== 'closed').length })
      setPage('case')
      logActivity('Cohort loaded', `POST /demo/seed · ledger object ${nextId}`, 'api')
      notify(`Synthetic cohort loaded from the CareLoop API · ledger object ${nextId} is open`)
    } catch {
      setActiveCaseId('demo-case-01')
      setPage('case')
      setApiOnline(false)
      logActivity('Cohort loaded locally', 'API unreachable · local synthetic view', 'local')
      notify('API unavailable · local synthetic fallback is active')
    } finally {
      setApiBusy(false)
    }
  }

  const actorId = role === 'clinician' ? 'clinician-1' : role === 'manager' ? 'manager-1' : 'navigator-1'

  const advance = async () => {
    const next: Record<Stage, Stage> = { stalled: 'escalated', escalated: 'handoff', handoff: 'closed', closed: 'closed' }
    const value = next[stage]
    if (stage === 'closed') return
    setApiBusy(true)
    let synced = true
    try {
      if (stage === 'stalled') {
        await careLoopApi.action(activeCaseId, actorId, 'escalate', { reason: 'absence-of-event deadline exceeded', target_role: 'program_manager', level: 1 })
        logActivity('Escalation recorded', `escalate · ${activeCaseId} · target program_manager`, 'api')
      } else if (stage === 'escalated') {
        await careLoopApi.action(activeCaseId, actorId === 'clinician-1' ? actorId : 'navigator-1', 'handoff', { to_user: 'clinician-1', note: 'Positive handoff: sender remains owner until acceptance.' })
        logActivity('Warm handoff sent', `handoff · navigator-1 → clinician-1`, 'api')
      } else if (stage === 'handoff') {
        const evidence = await careLoopApi.action<{ id: string }>(activeCaseId, 'clinician-1', 'evidence', { kind: 'confirmatory_result', summary: 'Synthetic evidence reviewed by an authorized clinician.' })
        await careLoopApi.action(activeCaseId, 'clinician-1', 'close', { evidence_id: evidence.id, closure_code: 'Completed' })
        logActivity('Evidence + closure', `evidence ${evidence.id} · closure_code Completed`, 'api')
      }
      setApiOnline(true)
      await reloadCase()
    } catch {
      synced = false
      setApiOnline(false)
      logActivity('Action kept locally', `API rejected or unreachable · ${stage} → ${value}`, 'local')
      notify('API action unavailable · continuing in local synthetic fallback')
    } finally {
      setApiBusy(false)
    }
    setStage(value)
    if (synced) {
      notify(value === 'closed' ? 'Loop closed with API evidence · patient confirmed the next step' : `Case moved to ${stageInfo[value].label.toLowerCase()}`)
    }
  }

  const changeRole = (nextRole: Role) => {
    setRole(nextRole)
    setPage(roleHome[nextRole])
    void syncScope(nextRole)
  }

  const roleMeta = roles.find(item => item.id === role) ?? roles[0]

  const care: CareApi = {
    caseId: activeCaseId,
    detail,
    activity,
    patientActorId: detail?.patient_id ?? 'patient-01',
    actorId,
    get lastError() { return lastErrorRef.current },
    select: selectCase,
    run: runCaseAction,
    log: logActivity,
    reload: reloadCase,
    passportOpen,
    setPassportOpen,
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><img className="brand-logo" src="/careloop-logo.png" alt="CareLoop logo" /><div><strong>care<span>loop</span></strong><small>CONNECTED CARE</small></div></div>
        <div className="workspace"><span className="eyebrow">WORKSPACE</span><button className="workspace-btn" onClick={() => setMenu(menu === 'workspace' ? 'none' : 'workspace')}><span className="org-dot">N</span><span>Northstar Health</span><span className="chevron">⌄</span></button>
          {menu === 'workspace' && <div className="popover">
            <header>NORTHSTAR HEALTH · WORKSPACE</header>
            <div><span>API endpoint</span><strong>{window.location.origin}/api</strong></div>
            <div><span>Health</span><strong>{apiOnline === null ? 'checking' : apiOnline ? 'connected' : 'unreachable · local fallback'}</strong></div>
            <div><span>Ledger object</span><strong>{care.caseId}</strong></div>
            <div><span>Seeded cohort</span><strong>{scope ? `${scope.total} synthetic cases` : 'not loaded'}</strong></div>
            <footer>Single workspace in this prototype · synthetic data only</footer>
          </div>}
        </div>
        <nav className="nav-list" aria-label="Main navigation">
          <span className="eyebrow">OPERATIONS</span>
          {navItems.map(item => <button key={item.id} className={`nav-item ${page === item.id ? 'active' : ''}`} onClick={() => setPage(item.id)}><span className="nav-icon">{item.icon}</span><span className="nav-label">{item.label}</span>{item.badge && <span className="nav-badge">{item.badge}</span>}</button>)}
          <span className="eyebrow lower">PROGRAM</span>
          <button className={`nav-item ${page === 'governance' ? 'active' : ''}`} onClick={() => setPage('governance')}><span className="nav-icon">⌘</span><span className="nav-label">Governance</span></button>
        </nav>
        <div className="sidebar-bottom"><div className="offline"><span className="live-dot"/> {apiOnline ? 'API connected' : 'Local fallback mode'} <span className="info" title="Synthetic data only; the UI falls back safely when the API is unavailable">i</span></div><div className="profile"><div className="avatar">AM</div><div><strong>Alex Morgan</strong><small>Care navigator</small></div><button className="more" onClick={() => setMenu(menu === 'profile' ? 'none' : 'profile')}>•••</button>
          {menu === 'profile' && <div className="popover">
            <header>SIGNED-IN IDENTITY</header>
            <div><span>Person</span><strong>Alex Morgan</strong></div>
            <div><span>Actor ID on writes</span><strong>{actorId}</strong></div>
            <div><span>Currently viewing as</span><strong>{roleMeta.label}</strong></div>
            <div><span>Actions this session</span><strong>{activity.length}</strong></div>
            <footer>Prototype identity · no authentication layer in this build</footer>
          </div>}
        </div></div>
      </aside>

      <main className="main-content">
        <header className="topbar"><div className="crumb"><span>Northstar Health</span><b>/</b><strong>{pageTitle(page)}</strong></div><div className="top-actions"><span className="sync"><i/> {apiOnline ? 'API synced' : apiOnline === false ? 'Local fallback' : 'Checking API'}</span><span className="bell-wrap"><button className="icon-btn notification" aria-label="Notifications" onClick={() => setMenu(menu === 'bell' ? 'none' : 'bell')}>♧{activity.length > 0 && <span className="notification-dot">{activity.length}</span>}</button>
              {menu === 'bell' && <div className="popover tray">
                <header>ACTION TRAY · THIS SESSION</header>
                {activity.length === 0 && <div className="tray-empty">No actions recorded yet. Load the dataset to start the loop.</div>}
                {activity.slice().reverse().map((item, index) => <div className="tray-row" key={`${item.at}-${index}`}><span className={`tray-dot ${item.source}`}/><div><strong>{item.label}</strong><small>{item.detail}</small></div><b>{item.at}</b></div>)}
                <footer>Entries come from the actions you performed in this browser session.</footer>
              </div>}
            </span><label className="role-select"><span className="avatar mini">{role === 'patient' ? 'SM' : 'AM'}</span><select aria-label="Select role" value={role} onChange={event => changeRole(event.target.value as Role)}>{roles.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select><span>⌄</span></label></div></header>
        <div className="content-wrap">
          <div className="role-context">
            <span className="rc-icon">{roleMeta.icon}</span>
            <strong>Viewing as {roleMeta.label}</strong>
            <span>{roleWorkspace[role]}</span>
            <span className={scope ? 'rc-scope' : 'rc-scope offline'}>
              {scope
                ? `read scope · X-Actor-ID ${scope.actor} · ${scope.total} synthetic case${scope.total === 1 ? '' : 's'} · ${scope.open} open`
                : `read scope · ${scopeNote}`}
            </span>
          </div>
           <div className="banner-row"><div className="demo-banner"><span className="banner-symbol">✦</span><div><strong>Synthetic dataset</strong><small>All records are generated from a seeded cohort · no patient data</small></div><button onClick={loadDemo} disabled={apiBusy}>{apiBusy ? 'Syncing…' : demoLoaded ? 'Reload dataset' : 'Load dataset'} <span>→</span></button></div><div className="human-banner"><span className="banner-symbol">♧</span><div><strong>Human governance active</strong><small>Care decisions require clinician review</small></div><span className="info" title="Automation is advisory only">i</span></div></div>
           <div className="metric-note">ASSUMPTION / TEST-RUN: every number shown here is synthetic, generated from a seeded cohort, or clearly labelled as model output. It is not a real-world health statistic.</div>
          {page === 'command' && <CommandCenter setPage={setPage} stage={stage} role={role} setRole={changeRole} onAdvance={advance} cohort={cohort} />}
          {page === 'case' && <CaseDetail stage={stage} onAdvance={advance} notify={notify} care={care} setPage={setPage} />}
          {page === 'queue' && <Queue setPage={setPage} care={care} notify={notify} />}
          {page === 'consult' && <Consult notify={notify} care={care} />}
           {page === 'patient' && <PatientEnglish stage={stage} notify={notify} care={care} />}
           {page === 'simulation' && <SimulationV2 notify={notify} />}
          {page === 'governance' && <Governance notify={notify} care={care} />}
        </div>
        <Passport care={care} notify={notify} stage={stage} />
        {toast && <div className="toast" role="status"><span>✓</span>{toast}</div>}
      </main>
    </div>
  )
}

function pageTitle(page: Page) { return ({ command: 'Command center', case: 'Case detail', queue: 'Navigator queue', consult: 'Consult workspace', patient: 'Patient view', simulation: 'Simulation lab', governance: 'Governance' }[page]) }

function PageHeading({ eyebrow, title, subtitle, children }: { eyebrow?: string; title: string; subtitle?: string; children?: ReactNode }) {
  return <div className="page-heading"><div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div><div className="heading-actions">{children}</div></div>
}

function StatusPill({ stage, compact = false }: { stage: Stage; compact?: boolean }) { const info = stageInfo[stage]; return <span className={`status-pill ${info.tone} ${compact ? 'compact' : ''}`}><i/>{info.label}</span> }
function Metric({ label, value, delta, tone = 'default', icon }: { label: string; value: string; delta?: string; tone?: string; icon: string }) { return <div className="metric-card"><div className={`metric-icon ${tone}`}>{icon}</div><div><span>{label}</span><strong>{value}</strong>{delta && <small className={delta.startsWith('+') || delta.includes('↓') ? 'positive' : ''}>{delta}</small>}</div></div> }

function CommandCenter({ setPage, stage, role, setRole, onAdvance, cohort }: { setPage: (p: Page) => void; stage: Stage; role: Role; setRole: (r: Role) => void; onAdvance: () => void; cohort: ApiCaseSummary[] | null }) {
  const items = cohort ?? []
  const fromApi = cohort !== null
  const counts = {
    open: fromApi ? items.filter(item => item.status !== 'closed').length : demoMetrics.openCases,
    closed: fromApi ? items.filter(item => item.status === 'closed').length : demoMetrics.closedThisMonth,
    owners: fromApi ? new Set(items.map(item => item.owner_id).filter(Boolean)).size : demoMetrics.namedOwners,
    total: fromApi ? items.length : demoMetrics.namedOwners,
  }
  return <>
    <PageHeading eyebrow="OVERVIEW · TUESDAY, OCTOBER 20, 2026" title="Good morning, Alex" subtitle="Here’s what needs your attention today."><button className="outline-btn" onClick={() => setPage('simulation')}>◇ Open simulation</button><button className="primary-btn" onClick={() => setPage('queue')}>View my queue <span>→</span></button></PageHeading>
    <div className="role-strip"><span>Viewing as</span>{roles.map(item => <button key={item.id} className={role === item.id ? 'selected' : ''} onClick={() => setRole(item.id)}><span>{item.icon}</span>{item.label}</button>)}</div>
    <section className="metrics-grid"><Metric label="Open ledger objects" value={String(counts.open)} delta={fromApi ? 'read from GET /cases' : 'local synthetic list'} tone="blue" icon="◎"/><Metric label="Closed with evidence" value={String(counts.closed)} delta={fromApi ? 'status closed in the store' : 'evidence required'} tone="green" icon="✓"/><Metric label="Named owners" value={String(counts.owners)} delta={fromApi ? 'distinct owner ids' : 'synthetic queue'} tone="purple" icon="◷"/><Metric label="Ledger objects in store" value={String(counts.total)} delta="seeded cohort" tone="amber" icon="⌗"/></section>
    <p className="metric-note">{fromApi ? 'Counts are read from the local ledger through GET /cases with the current actor id. They are synthetic records, not population statistics.' : 'The API list is unavailable, so these counts come from the local synthetic case list only.'}</p>
    <div className="section-grid"><section className="panel attention-panel"><div className="panel-header"><div><span className="eyebrow">PRIORITY QUEUE</span><h2>Needs your attention <span className="count-badge">3</span></h2></div><button className="text-btn" onClick={() => setPage('queue')}>View all <span>→</span></button></div><div className="case-list"><CaseRow initials="SM" name="Samira Malik" detail="Food insecurity · 4 days stalled" stage="stalled" onClick={() => setPage('case')} urgent/><CaseRow initials="JT" name="James Thompson" detail="Depression screen · Awaiting consult" stage="escalated" onClick={() => setPage('case')}/><CaseRow initials="LC" name="Lena Chen" detail="Housing support · Handoff ready" stage="handoff" onClick={() => setPage('case')}/></div></section><section className="panel flow-panel"><div className="panel-header"><div><span className="eyebrow">CARE LOOP HEALTH</span><h2>Where cases are today</h2></div><button className="icon-btn small" onClick={() => setPage('governance')}>•••</button></div><div className="flow-bars"><FlowBar label="Screened" value="96" total="124" width="92%" color="blue"/><FlowBar label="Engaged" value="78" total="96" width="76%" color="purple"/><FlowBar label="Connected" value="61" total="78" width="60%" color="teal"/><FlowBar label="Closed loop" value="44" total="61" width="43%" color="green"/></div><div className="flow-foot"><span><i className="dot teal"/> 71% connected</span><span className="muted">Target 75%</span></div><p className="metric-note">Illustrative funnel from the synthetic narrative · not read from the ledger.</p></section></div>
    <section className="panel journey-panel"><div className="panel-header"><div><span className="eyebrow">WORKED EXAMPLE</span><h2>See the loop in motion</h2></div><StatusPill stage={stage}/></div><div className="journey"><JourneyStep number="01" label="Screening" done/><JourneyLine done/><JourneyStep number="02" label="Stalled" active={stage === 'stalled'} done={stage !== 'stalled'}/><JourneyLine done={stage !== 'stalled'}/><JourneyStep number="03" label="Escalation" active={stage === 'escalated'} done={stage === 'handoff' || stage === 'closed'}/><JourneyLine done={stage === 'handoff' || stage === 'closed'}/><JourneyStep number="04" label="Warm handoff" active={stage === 'handoff'} done={stage === 'closed'}/><JourneyLine done={stage === 'closed'}/><JourneyStep number="05" label="Closed loop" active={stage === 'closed'} done={stage === 'closed'}/></div><div className="journey-cta"><div><strong>Samira’s care journey</strong><span>{stageInfo[stage].helper}</span></div><button className="primary-btn" onClick={() => stage === 'closed' ? setPage('case') : onAdvance()}>{stage === 'closed' ? 'Review closed case' : 'Advance journey'} <span>→</span></button></div></section>
  </>
}

function CaseRow({ initials, name, detail, stage, onClick, urgent }: { initials: string; name: string; detail: string; stage: Stage; onClick: () => void; urgent?: boolean }) { return <button className="case-row" onClick={onClick}><div className={`avatar ${urgent ? 'urgent' : ''}`}>{initials}</div><div className="case-copy"><strong>{name}</strong><span>{detail}</span></div><StatusPill stage={stage} compact/><span className="row-arrow">→</span></button> }
function FlowBar({ label, value, total, width, color }: { label: string; value: string; total: string; width: string; color: string }) { return <div className="flow-row"><div><span>{label}</span><strong>{value}<small> / {total}</small></strong></div><div className="bar"><i className={color} style={{ width }}/></div></div> }
function JourneyStep({ number, label, done, active }: { number: string; label: string; done?: boolean; active?: boolean }) { return <div className={`journey-step ${done ? 'done' : ''} ${active ? 'active' : ''}`}><div>{done ? '✓' : number}</div><span>{label}</span></div> }
function JourneyLine({ done }: { done?: boolean }) { return <div className={`journey-line ${done ? 'done' : ''}`}/> }

function CaseDetail({ stage, onAdvance, notify, care, setPage }: { stage: Stage; onAdvance: () => void; notify: (s: string) => void; care: CareApi; setPage: (p: Page) => void }) {
  const info = stageInfo[stage]
  const [noteOpen, setNoteOpen] = useState(false)
  const [noteDraft, setNoteDraft] = useState('')
  const [contact, setContact] = useState<'none' | 'phone' | 'sms'>('none')
  const [signalsOpen, setSignalsOpen] = useState(false)
  const [ackedAt, setAckedAt] = useState('')
  const detail = care.detail
  const notes = (detail?.evidence ?? []).filter(item => item.kind === 'documentation')
  const ledgerEvidence = (detail?.evidence ?? []).filter(item => item.kind !== 'documentation')

  const saveNote = async () => {
    const text = noteDraft.trim()
    if (!text) { notify('Write a note before saving'); return }
    const ok = await care.run('evidence', { kind: 'documentation', summary: text })
    care.log('Case note recorded', text.slice(0, 60), ok ? 'api' : 'local')
    setNoteDraft('')
    setNoteOpen(false)
    notify(ok ? 'Case note written to the ledger as evidence · documentation' : `Case note kept in this browser only · ${care.lastError}`)
  }

  const logDraft = async (channel: 'phone' | 'sms') => {
    const text = channel === 'phone'
      ? 'Call draft · confirm evening preference and agree a booking time with Riverside Food Hub.'
      : 'SMS draft · Riverside Food Hub is open until 7 PM. Reply to book an evening time.'
    const ok = await care.run('evidence', { kind: 'documentation', summary: `[${channel.toUpperCase()} draft] ${text}` })
    care.log('Outreach draft stored', channel, ok ? 'api' : 'local')
    notify(ok ? 'Outreach draft stored as evidence · no message was sent to any patient' : `Outreach draft kept in this browser only · ${care.lastError}`)
  }

  const acknowledge = async () => {
    const ok = await care.run('acknowledge', { acknowledged_by: 'Alex Morgan', channel: 'SMS' })
    setAckedAt(clockLabel())
    care.log('Recommendation acknowledged', ok ? 'audit row written' : 'local acknowledgement', ok ? 'api' : 'local')
    notify(ok ? 'Acknowledged · audit row written by the API' : `Acknowledged in this browser only · ${care.lastError}`)
  }

  return <><PageHeading eyebrow={`CASE CL-2048 · LEDGER OBJECT ${care.caseId}`} title="Samira Malik" subtitle="Food insecurity · Screening completed Oct 16, 2026"><StatusPill stage={stage}/><button className="outline-btn" onClick={() => setNoteOpen(!noteOpen)}>＋ Add note</button><button className="primary-btn" onClick={() => stage === 'closed' ? care.setPassportOpen(true) : onAdvance()}>{stage === 'stalled' ? 'Escalate case' : stage === 'escalated' ? 'Send warm handoff' : stage === 'handoff' ? 'Close the loop' : 'View result passport'} <span>→</span></button></PageHeading>
    {noteOpen && <div className="note-composer"><input value={noteDraft} onChange={event => setNoteDraft(event.target.value)} placeholder="What did you observe or decide?" aria-label="Case note"/><button className="primary-btn" onClick={saveNote}>Save to ledger</button><button className="text-btn" onClick={() => setNoteOpen(false)}>Cancel</button></div>}
    <div className="case-layout"><div className="case-main"><section className="panel patient-card"><div className="patient-identity"><div className="avatar large">SM</div><div><h2>Samira Malik <span className="verified">✓</span></h2><p>She/her · 34 years · Preferred language: English</p><div className="identity-tags"><span>MRN-04821</span><span>Northside Family Practice</span></div></div></div><div className="patient-contact"><div><span>PHONE</span><strong>(555) 014-7284</strong></div><div><span>BEST TIME</span><strong>Evenings</strong></div><button className={`icon-btn ${contact === 'phone' ? 'on' : ''}`} onClick={() => setContact(contact === 'phone' ? 'none' : 'phone')}>✆</button><button className={`icon-btn ${contact === 'sms' ? 'on' : ''}`} onClick={() => setContact(contact === 'sms' ? 'none' : 'sms')}>✉</button></div>
      {contact !== 'none' && <div className="contact-draft"><div><span className="eyebrow">{contact === 'phone' ? 'CALL PLAN' : 'SMS DRAFT'}</span><p>{contact === 'phone' ? 'Confirm the evening preference and agree a booking time with Riverside Food Hub. Ask the patient to repeat the address back.' : 'Riverside Food Hub is open until 7 PM. Reply to book an evening time.'}</p><small>This prototype never sends anything to a real patient. Synthetic contact only.</small></div><button className="outline-btn" onClick={() => logDraft(contact)}>Store draft as evidence</button></div>}</section>
      <section className="panel timeline-panel"><div className="panel-header"><div><span className="eyebrow">CARE JOURNEY</span><h2>From screening to care</h2></div><span className="muted">{detail ? `${detail.events.length + 4} events · ledger ${detail.events.length ? detail.events.map(item => item.event_type).join(', ') : 'no transport events yet'}` : '4 events'}</span></div><div className="timeline"><TimelineItem date="Oct 20 · 09:14" title={stage === 'stalled' ? 'Case flagged as stalled' : `Case ${info.label.toLowerCase()}`} text={`${info.helper}. System recommendation is advisory and awaits human review.`} tone={stage === 'closed' ? 'green' : 'red'} icon={stage === 'closed' ? '✓' : '!'}/><TimelineItem date="Oct 16 · 14:32" title="Social needs screening completed" text="Food insecurity identified · score 8/10. Patient consented to support." tone="blue" icon="✓"/><TimelineItem date="Oct 16 · 14:35" title="Resource match found" text="3 nearby food access programs matched to patient preferences." tone="purple" icon="⌕"/><TimelineItem date="Oct 16 · 14:28" title="Referral created by Dr. Priya Shah" text="Screening result routed to CareLoop." tone="teal" icon="↗"/></div></section>
      <section className="panel notes-panel"><div className="panel-header"><div><span className="eyebrow">LEDGER EVIDENCE</span><h2>Notes and evidence</h2></div><button className="text-btn" onClick={() => { void care.reload(); notify('Ledger refetched from the API') }}>Refresh ⟳</button></div>
        {notes.length === 0 && ledgerEvidence.length === 0 && <p className="muted-block">{detail ? 'No evidence recorded on this ledger object yet. Add a note or advance the journey.' : 'Ledger not reachable · showing the synthetic narrative only.'}</p>}
        {[...notes, ...ledgerEvidence].map(item => <div className="note-row" key={item.id}><div className={`note-dot ${item.kind === 'documentation' ? 'note' : 'evidence'}`}/><div><strong>{item.kind === 'documentation' ? 'Case note' : item.kind.replace(/_/g, ' ')}</strong><span>{item.summary}</span><small>{item.id} · {item.recorded_by} · {item.recorded_at.slice(11, 19)}Z</small></div></div>)}
      </section>
      <section className="panel next-panel"><div><span className="eyebrow">RECOMMENDED NEXT STEP</span><h2>{stage === 'stalled' ? 'Escalate to navigator review' : stage === 'escalated' ? 'Complete a warm handoff' : stage === 'handoff' ? 'Confirm patient connection' : 'Document the closed loop'}</h2><p>{info.helper}. Review the recommendation, then decide what happens next.{ackedAt && <strong className="acked"> Acknowledged by Alex Morgan at {ackedAt}</strong>}</p></div><button className="outline-btn" onClick={acknowledge}>{ackedAt ? 'Acknowledged ✓' : 'Acknowledge'}</button></section></div>
      <aside className="case-side"><section className="panel"><div className="panel-header"><h2>Case signals</h2><button className={`icon-btn small ${signalsOpen ? 'on' : ''}`} onClick={() => setSignalsOpen(!signalsOpen)}>•••</button></div><Signal label="Urgency" value={detail?.urgency === 'urgent' ? 'High' : 'High'} tone="red"/><Signal label="Consent" value={detail?.consents.length ? 'Recorded' : 'Active'} tone="green"/><Signal label="Preferred channel" value="SMS" tone="blue"/><Signal label="Days open" value={stage === 'closed' ? '5' : '4'} tone="amber"/>
        {signalsOpen && <div className="signal-details">
          <div><span>Ledger object</span><strong>{detail?.id ?? care.caseId}</strong></div>
          <div><span>Loop ID (pseudonymous)</span><strong>{detail?.loop_id ?? 'not loaded from API'}</strong></div>
          <div><span>Stage</span><strong>{detail?.stage ?? '—'}</strong></div>
          <div><span>Status</span><strong>{detail?.status ?? '—'}</strong></div>
          <div><span>Next owner</span><strong>{detail?.owner_next ?? '—'}</strong></div>
          <div><span>Deadline</span><strong>{detail?.due_at ? detail.due_at.slice(11, 16) + 'Z' : '—'}</strong></div>
          <div><span>High-risk flag</span><strong>{detail ? String(detail.high_risk) : '—'}</strong></div>
          <div><span>Closure code</span><strong>{detail?.closure_code ?? 'not closed'}</strong></div>
          <footer>Values read from <code>GET /cases/{care.caseId}</code></footer>
        </div>}
      </section><section className="panel owner-card"><span className="eyebrow">CURRENT OWNER</span><div className="owner"><div className="avatar">AM</div><div><strong>Alex Morgan</strong><span>Care navigator</span></div></div><button className="outline-btn full" onClick={() => setPage('consult')}>Open consult workspace ↗</button></section><section className="panel"><div className="panel-header"><h2>Matched resources</h2><span className="count-badge">3</span></div><div className="resource"><div className="resource-icon">⌂</div><div><strong>Riverside Food Hub</strong><span>0.8 mi · Open today</span></div><span>›</span></div><div className="resource"><div className="resource-icon">♧</div><div><strong>SNAP enrollment help</strong><span>Remote · 9am–5pm</span></div><span>›</span></div></section></aside>
    </div></>
}
function TimelineItem({ date, title, text, tone, icon }: { date: string; title: string; text: string; tone: string; icon: string }) { return <div className="timeline-item"><div className={`timeline-icon ${tone}`}>{icon}</div><div><span className="muted">{date}</span><h3>{title}</h3><p>{text}</p></div></div> }
function Signal({ label, value, tone }: { label: string; value: string; tone: string }) { return <div className="signal"><span>{label}</span><strong className={tone}>{value}</strong></div> }

function Field({ label, value, tone = '' }: { label: string; value: string; tone?: string }) {
  return <div className={`passport-field ${tone}`}><span>{label}</span><strong>{value}</strong></div>
}

function Passport({ care, notify, stage }: { care: CareApi; notify: (s: string) => void; stage: Stage }) {
  const [bundle, setBundle] = useState('')
  const [bundleNote, setBundleNote] = useState('')
  if (!care.passportOpen) return null
  const detail = care.detail
  const info = stageInfo[stage]

  const openFhir = async () => {
    try {
      const data = await careLoopApi.fhirExport(care.caseId, care.actorId)
      setBundle(JSON.stringify(data, null, 2))
      setBundleNote(`${data.entry.length} resources in the bundle · ${data.label} · conformance tested: ${String(data.conformance_tested)}`)
      care.log('Structured export read', `${data.entry.length} resources · ${care.caseId}`, 'api')
    } catch (error) {
      setBundle('')
      setBundleNote(`Export unavailable · ${error instanceof Error ? error.message : 'request failed'}`)
    }
  }

  return <div className="scrim" onClick={() => care.setPassportOpen(false)} role="presentation">
    <section className="modal passport" onClick={event => event.stopPropagation()} role="dialog" aria-label="Result passport">
      <header className="modal-head"><div><span className="eyebrow">RESULT PASSPORT · SYNTHETIC LEDGER READ</span><h2>{detail ? detail.title : 'Ledger object not reachable'}</h2><p>{info.helper} · object {care.caseId}</p></div><button className="icon-btn" onClick={() => care.setPassportOpen(false)} aria-label="Close passport">×</button></header>
      <div className="passport-grid">
        <Field label="Ledger object" value={detail?.id ?? care.caseId}/>
        <Field label="Loop ID (pseudonymous)" value={detail?.loop_id ?? 'not read'}/>
        <Field label="Canonical stage" value={detail?.stage ?? 'not read'}/>
        <Field label="Status" value={detail?.status ?? 'not read'} tone={detail?.status === 'closed' ? 'green' : 'amber'}/>
        <Field label="Next owner" value={detail?.owner_next ?? 'not read'}/>
        <Field label="Urgency" value={detail?.urgency ?? 'not read'}/>
        <Field label="Deadline" value={detail ? detail.due_at.replace('T', ' ').slice(0, 19) + 'Z' : 'not read'}/>
        <Field label="High-risk flag" value={detail ? String(detail.high_risk) : 'not read'}/>
        <Field label="Closure code" value={detail?.closure_code ?? 'not closed'}/>
        <Field label="Closure basis" value={detail?.closure_basis ?? 'no evidence reference yet'}/>
        <Field label="Evidence refs" value={detail ? (detail.evidence_refs.length ? detail.evidence_refs.join(', ') : 'none') : 'not read'}/>
        <Field label="Human authorization" value={detail?.authorization_id ?? 'not required for this record'}/>
      </div>
      <div className="passport-blocks">
        <div className="passport-block"><span className="eyebrow">CONSENT</span>{(detail?.consents ?? []).length === 0 && <p className="muted-block">No consent row on this ledger object.</p>}
          {(detail?.consents ?? []).map(item => <div className="list-row" key={item.id}><span className={item.granted ? 'tick' : 'cross'}>{item.granted ? '✓' : '×'}</span><div><strong>{item.scope}</strong><small>recorded by {item.recorded_by} · {item.recorded_at.slice(0, 19)}Z</small></div></div>)}
        </div>
        <div className="passport-block"><span className="eyebrow">EVIDENCE</span>{(detail?.evidence ?? []).length === 0 && <p className="muted-block">No evidence recorded. A closure is refused until an evidence reference exists.</p>}
          {(detail?.evidence ?? []).map(item => <div className="list-row" key={item.id}><span className="tick">✓</span><div><strong>{item.kind}</strong><small>{item.summary}</small><small>{item.id} · {item.recorded_by}</small></div></div>)}
        </div>
        <div className="passport-block"><span className="eyebrow">APPOINTMENTS</span>{(detail?.appointments ?? []).length === 0 && <p className="muted-block">No appointment slot booked by the care team.</p>}
          {(detail?.appointments ?? []).map(item => <div className="list-row" key={item.id}><span className="tick">✓</span><div><strong>{item.scheduled_for.replace('T', ' ').slice(0, 16)}Z</strong><small>{item.id} · created by {item.created_by}</small></div></div>)}
        </div>
        <div className="passport-block"><span className="eyebrow">ESCALATIONS AND HANDOFFS</span>{(detail?.escalations ?? []).length + (detail?.handoffs ?? []).length === 0 && <p className="muted-block">No escalation or handoff recorded.</p>}
          {(detail?.escalations ?? []).map(item => <div className="list-row" key={item.id}><span className="cross">!</span><div><strong>Escalation · level {item.level} to {item.target_role}</strong><small>{item.reason}</small></div></div>)}
          {(detail?.handoffs ?? []).map(item => <div className="list-row" key={item.id}><span className="tick">→</span><div><strong>{item.from_user} → {item.to_user}</strong><small>{item.note || 'no note'} · {item.id}</small></div></div>)}
        </div>
      </div>
      <div className="passport-events"><span className="eyebrow">TRANSPORT EVENTS · E1–E9</span>
        {(detail?.events ?? []).length === 0 && <p className="muted-block">No transport events on this loop.</p>}
        {(detail?.events ?? []).length > 0 && <div className="pp-head"><span>EVENT</span><span>RECORDED</span><span>OWNER NEXT</span><span>DUE</span><span>EVIDENCE REF</span></div>}
        {(detail?.events ?? []).map((item, index) => <div className="pp-row" key={`${item.loop_id}-${index}`}><strong>{item.event_type}</strong><span>{item.timestamp.replace('T', ' ').slice(0, 19)}Z</span><span>{item.owner_next}</span><span>{item.due_at.replace('T', ' ').slice(11, 19)}Z</span><span>{item.evidence_ref ?? '—'}</span></div>)}
      </div>
      <footer className="modal-foot"><div className="foot-note"><strong>{bundleNote || 'The structured export is read on demand.'}</strong>{bundle && <pre className="pp-json">{bundle}</pre>}<small>Every value above is read from GET /cases/{care.caseId} on this machine. Synthetic data · not a clinical document · not evidence of real-world outcomes.</small></div><div className="foot-actions"><button className="outline-btn" onClick={openFhir}>Structured export ↗</button><button className="outline-btn" onClick={() => { void care.reload(); notify('Passport refetched from the ledger') }}>Refresh ⟳</button><button className="primary-btn" onClick={() => care.setPassportOpen(false)}>Close</button></div></footer>
    </section>
  </div>
}



function Queue({ setPage, care, notify }: { setPage: (p: Page) => void; care: CareApi; notify: (s: string) => void }) {
  const [query, setQuery] = useState('')
  const [tab, setTab] = useState('My queue')
  const [filterOpen, setFilterOpen] = useState(false)
  const [ownerFilter, setOwnerFilter] = useState('navigator-1')
  const [statusFilter, setStatusFilter] = useState('open')

  // Tabs and the popover write the same two filters, so a tab click is a shortcut for
  // a filter pair and the two controls can never contradict each other.
  const selectTab = (next: string) => {
    setTab(next)
    if (next === 'My queue') { setOwnerFilter('navigator-1'); setStatusFilter('open') }
    if (next === 'Unassigned') { setOwnerFilter('none'); setStatusFilter('any') }
    if (next === 'Recently closed') { setOwnerFilter('any'); setStatusFilter('closed') }
  }
  const [cases, setCases] = useState<ApiCaseSummary[] | null>(null)
  const [composerOpen, setComposerOpen] = useState(false)
  const [title, setTitle] = useState('')

  const refresh = async () => {
    try {
      setCases((await careLoopApi.listCases(care.actorId)).items)
    } catch {
      setCases(null)
    }
  }

  useEffect(() => { void refresh() }, [care.caseId, care.actorId])

  const counts = useMemo(() => {
    const items = cases ?? []
    return {
      mine: items.filter(item => item.owner_id === 'navigator-1').length,
      unassigned: items.filter(item => !item.owner_id).length,
      closed: items.filter(item => item.status === 'closed').length,
    }
  }, [cases])

  const ledger = useMemo(() => (cases ?? []).filter(item => {
    if (!`${item.id} ${item.title} ${item.owner_id} ${item.stage}`.toLowerCase().includes(query.toLowerCase())) return false
    if (statusFilter === 'open' && item.status === 'closed') return false
    if (statusFilter === 'closed' && item.status !== 'closed') return false
    if (ownerFilter === 'none' ? Boolean(item.owner_id) : ownerFilter !== 'any' && item.owner_id !== ownerFilter) return false
    return true
  }), [cases, query, statusFilter, ownerFilter])

  const narrative = useMemo(() => (cases === null ? seedCases.filter(item => `${item.name} ${item.need} ${item.id}`.toLowerCase().includes(query.toLowerCase())) : []), [cases, query])

  const createCase = async () => {
    const text = title.trim()
    if (!text) { notify('Give the synthetic case a title first'); return }
    const list = cases ?? []
    for (let n = list.length + 1; n < list.length + 90; n++) {
      const id = `synth-case-${String(n).padStart(3, '0')}`
      if (list.some(item => item.id === id)) continue
      const patientId = `patient-${String(((n - 1) % Math.max(1, list.length)) + 1).padStart(2, '0')}`
      try {
        await careLoopApi.createCase({ id, patient_id: patientId, title: text, owner_id: 'navigator-1' }, care.actorId)
        setTitle('')
        setComposerOpen(false)
        await refresh()
        care.select(id)
        setPage('case')
        care.log('Ledger object created', `POST /cases · ${id} · patient ${patientId}`, 'api')
        notify(`Ledger object ${id} created at stage result_issued · owner navigator-1 · patient ${patientId}`)
      } catch (error) {
        notify(`API refused the new case · ${error instanceof Error ? error.message : 'request failed'}`)
      }
      return
    }
    notify('No free case id available · reload the dataset and try again')
  }

  return <><PageHeading eyebrow="OPERATIONS · NAVIGATOR QUEUE" title="Navigator queue" subtitle="Search, filter, and open the ledger objects held in the local store."><button className={`outline-btn ${filterOpen ? 'on' : ''}`} onClick={() => setFilterOpen(!filterOpen)}>Filter <span>⌄</span></button><button className={`primary-btn ${composerOpen ? 'on' : ''}`} onClick={() => setComposerOpen(!composerOpen)}>＋ New case</button></PageHeading>
    {filterOpen && <div className="popover filter-pop">
      <header>QUEUE FILTERS</header>
      <div className="pop-row"><span>Case status</span><select value={statusFilter} onChange={event => setStatusFilter(event.target.value)}><option value="any">Any status</option><option value="open">Open only</option><option value="closed">Closed only</option></select></div>
      <div className="pop-row"><span>Named owner</span><select value={ownerFilter} onChange={event => setOwnerFilter(event.target.value)}><option value="any">Any owner</option><option value="none">No named owner</option><option value="navigator-1">navigator-1</option><option value="clinician-1">clinician-1</option><option value="manager-1">manager-1</option></select></div>
      <footer>{cases ? `${ledger.length} of ${cases.length} ledger objects match · status ${statusFilter} · owner ${ownerFilter}` : 'API unreachable · filters apply to the local synthetic list'}</footer>
    </div>}
    {composerOpen && <div className="note-composer"><input value={title} onChange={event => setTitle(event.target.value)} onKeyDown={event => event.key === 'Enter' && createCase()} placeholder="Title for the new synthetic case" aria-label="New case title"/><button className="primary-btn" onClick={createCase}>Create ledger object</button><button className="text-btn" onClick={() => setComposerOpen(false)}>Cancel</button></div>}
    <div className="queue-tabs">{(['My queue', 'Unassigned', 'Recently closed'] as const).map(item => <button key={item} className={tab === item ? 'active' : ''} onClick={() => selectTab(item)}>{item}<b>{item === 'My queue' ? counts.mine : item === 'Unassigned' ? counts.unassigned : counts.closed}</b></button>)}<label className="queue-search">⌕ <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search ledger objects" aria-label="Search ledger objects"/></label></div>
    <section className="panel table-panel"><div className="table-head"><span>LEDGER OBJECT</span><span>TITLE / NEED</span><span>STAGE</span><span>STATUS</span><span>NAMED OWNER</span><span></span></div>
      {ledger.map(item => <button className="table-row" key={item.id} onClick={() => { care.select(item.id); setPage('case') }}><div className="patient-cell"><div className="avatar">{item.owner_id.slice(0, 2).toUpperCase()}</div><div><strong>{item.id}</strong><span>{item.patient_id}</span></div></div><span>{item.title}</span><span className="stage-code">{item.stage}</span><span className={`priority ${item.status === 'closed' ? 'low' : 'high'}`}><i/>{item.status}</span><span className="owner-tag">{item.owner_id}</span><span className="row-arrow">→</span></button>)}
      {narrative.map(item => <button className="table-row" key={item.name} onClick={() => setPage('case')}><div className="patient-cell"><div className="avatar">{item.initials}</div><div><strong>{item.name}</strong><span>{item.id}</span></div></div><span>{item.need}</span><StatusPill stage={item.stage} compact/><span>{item.age}</span><span className={`priority ${item.priority.toLowerCase()}`}><i/>{item.priority}</span><span className="row-arrow">→</span></button>)}
      {cases !== null && cases.length === 0 && <div className="empty-state">The local store is empty · press “Load dataset” in the banner to seed the synthetic cohort.</div>}
      {cases !== null && cases.length > 0 && ledger.length === 0 && <div className="empty-state">No ledger object matches this search, tab, or filter. Clear the filter or pick another tab.</div>}
      {cases === null && narrative.length === 0 && <div className="empty-state">No synthetic narrative row matches “{query}”.</div>}
    </section>
    {cases === null ? <p className="metric-note">The API list is unavailable, so this table shows the local synthetic narrative. Nothing here is written to a ledger.</p> : <p className="metric-note">Rows are read from GET /cases with header X-Actor-ID {care.actorId}. Opening a row loads that ledger object into Case detail.</p>}
  </>
}

function Consult({ notify, care }: { notify: (s: string) => void; care: CareApi }) {
  const [message, setMessage] = useState('')
  const [thread, setThread] = useState<{ at: string; body: string; stored: boolean }[]>([])
  const detail = care.detail

  const send = async () => {
    const text = message.trim()
    if (!text) { notify('Type a message before sending'); return }
    const ok = await care.run('evidence', { kind: 'consult_note', summary: `Consult message from Alex Morgan: ${text}` })
    setThread(current => [...current, { at: clockLabel(), body: text, stored: ok }])
    setMessage('')
    care.log('Consult note recorded', text.slice(0, 60), ok ? 'api' : 'local')
    notify(ok ? 'Consult note written to the ledger as evidence · consult_note' : `Message kept in this browser thread only · ${care.lastError}`)
  }

  const requestConsult = async () => {
    const ok = await care.run('escalate', { reason: 'Clinical consult requested before warm handoff', target_role: 'clinician', level: 1 })
    care.log('Consult requested', ok ? `escalate on ${care.caseId} · target clinician` : 'local request only', ok ? 'api' : 'local')
    notify(ok ? `Consult request recorded as an escalation on ${care.caseId} · target role clinician` : `Consult request not recorded · ${care.lastError}`)
  }

  return <><PageHeading eyebrow="CLINICAL COLLABORATION" title="Consult workspace" subtitle="A clear place for the care team to align before a handoff."><span className="secure"><i/> Local workspace</span><button className="primary-btn" onClick={requestConsult}>Request consult <span>→</span></button></PageHeading><div className="consult-grid"><section className="panel consult-thread"><div className="panel-header"><div><span className="eyebrow">LEDGER OBJECT {care.caseId}</span><h2>{detail ? detail.title : 'Samira Malik · Food insecurity'}</h2></div><StatusPill stage="escalated"/></div><div className="thread"><div className="message"><div className="avatar">AM</div><div><div className="message-meta"><strong>Alex Morgan</strong><span>09:18</span></div><p>Samira has not booked with a food access resource after screening. She prefers evening calls and SMS. Can we confirm Riverside Food Hub is appropriate?</p></div></div><div className="message reply"><div className="avatar clinician">PS</div><div><div className="message-meta"><strong>Dr. Priya Shah</strong><span>09:26</span></div><p>Yes, Riverside has evening hours. Please use a warm handoff and ask Samira to repeat the address back to us.</p><div className="clinical-note">✚ Clinical guidance · Human-authored</div></div></div>{thread.map((item, index) => <div className="message" key={`${item.at}-${index}`}><div className="avatar">AM</div><div><div className="message-meta"><strong>Alex Morgan</strong><span>{item.at}</span></div><p>{item.body}</p><small className="thread-tag">{item.stored ? 'written as consult_note evidence on the ledger' : 'browser thread only · not written'}</small></div></div>)}</div><div className="composer"><input value={message} onChange={event => setMessage(event.target.value)} onKeyDown={event => event.key === 'Enter' && send()} placeholder="Write a message to the care team…" aria-label="Consult message"/><button className="primary-btn" onClick={send}>Send</button></div></section><aside className="panel consult-summary"><span className="eyebrow">CONSULT SUMMARY</span><h2>Decision support</h2><div className="summary-block"><span>Screening signal</span><strong>Food insecurity · 8/10</strong></div><div className="summary-block"><span>Suggested match</span><strong>Riverside Food Hub</strong><small>0.8 mi · Accessible by bus</small></div><div className="summary-block"><span>Human review</span><strong className="green-text">Required before outreach</strong></div>
    <div className="consult-ledger"><span className="eyebrow">LEDGER RECORD</span>
      {(detail?.escalations ?? []).map(item => <div className="ledger-line" key={item.id}><b>Escalation</b><span>level {item.level} to {item.target_role} · {item.reason}</span></div>)}
      {(detail?.handoffs ?? []).map(item => <div className="ledger-line" key={item.id}><b>Handoff</b><span>{item.from_user} to {item.to_user}</span></div>)}
      {(detail?.appointments ?? []).map(item => <div className="ledger-line" key={item.id ?? item.scheduled_for}><b>Appointment</b><span>{item.scheduled_for.replace('T', ' ').slice(0, 16)}Z · by {item.created_by}</span></div>)}
      {!detail && <p className="muted-block">Ledger not reachable · this panel stays empty rather than inventing records.</p>}
      {detail && (detail.escalations.length + detail.handoffs.length + detail.appointments.length) === 0 && <p className="muted-block">No escalation, handoff, or appointment on {detail.id} yet.</p>}
    </div>
    <div className="review-note">✦ Suggestions are explainable and reversible. A clinician owns the final decision.</div></aside></div></>
}

function Patient({ arabic, setArabic, stage, notify }: { arabic: boolean; setArabic: (v: boolean) => void; stage: Stage; notify: (s: string) => void }) {
  const [teachBack, setTeachBack] = useState<'yes' | 'needs-help' | null>(null)
  const rtl = arabic
  return <div dir={rtl ? 'rtl' : 'ltr'} className="patient-view"><PageHeading eyebrow={rtl ? 'رِحْلَةُ الرِّعَايَة' : 'PATIENT PORTAL · SAMIRA MALIK'} title={rtl ? 'أهلاً سميرة' : 'Hi Samira'} subtitle={rtl ? 'نحن هنا لمساعدتك في خطوتك التالية.' : 'We’re here to help with your next step.'}><div className="language-toggle"><button className={!arabic ? 'selected' : ''} onClick={() => setArabic(false)}>EN</button><button className={arabic ? 'selected' : ''} onClick={() => setArabic(true)}>عربي</button></div></PageHeading><section className="patient-hero"><div className="hero-copy"><span className="eyebrow">{rtl ? 'تحديث الرعاية' : 'CARE UPDATE'}</span><h2>{rtl ? 'تم العثور على مكان قريب لمساعدتك' : 'We found a nearby place to help'}</h2><p>{rtl ? 'مركز ريفرسايد للطعام مفتوح اليوم حتى الساعة 7 مساءً.' : 'Riverside Food Hub is open today until 7:00 PM and can help with groceries.'}</p><div className="hero-actions"><button className="primary-btn" onClick={() => notify(rtl ? 'بدأنا طلب الموعد' : 'Appointment request started')}>{rtl ? 'احجز موعداً' : 'Book a time'} <span>→</span></button><button className="text-btn" onClick={() => notify(rtl ? 'تفاصيل المركز محفوظة محلياً' : 'Resource details are available locally')}>{rtl ? 'عرض التفاصيل' : 'View details'}</button></div></div><div className="map-card"><div className="map-grid"><span className="map-road r1"/><span className="map-road r2"/><span className="map-road r3"/><span className="map-pin">⌂</span><span className="map-you">●</span></div><div className="map-label"><strong>Riverside Food Hub</strong><span>0.8 mi · 12 min by bus</span></div></div></section><div className="patient-columns"><section className="panel teachback"><div className="panel-header"><div><span className="eyebrow">{rtl ? 'التأكد من الفهم' : 'TEACH-BACK'}</span><h2>{rtl ? 'هل هذا واضح؟' : 'What do you think happens next?'}</h2></div><span className="check-circle">✓</span></div><p>{rtl ? 'أخبرينا بخطوتك التالية بكلماتك الخاصة حتى نتأكد من أن الخطة واضحة.' : 'Tell us the next step in your own words for staff review; it is not proof of comprehension.'}</p><div className="teachback-actions"><button className={teachBack === 'yes' ? 'selected' : ''} onClick={() => { setTeachBack('yes'); notify(rtl ? 'شكراً لتأكيدك' : 'Teach-back recorded locally') }}>✓ {rtl ? 'نعم، فهمت' : 'Yes, I understand'}</button><button className={teachBack === 'needs-help' ? 'selected' : ''} onClick={() => { setTeachBack('needs-help'); notify(rtl ? 'سيتواصل معك أحد أعضاء الفريق' : 'A care team member will follow up') }}>? {rtl ? 'أحتاج للمساعدة' : 'I need help'}</button></div>{teachBack && <div className="teachback-confirm">{teachBack === 'yes' ? (rtl ? 'تم تسجيل إجابتك.' : 'Your response was recorded.') : (rtl ? 'سنطلب من فريق الرعاية التواصل معك.' : 'A care team follow-up was requested.')}</div>}</section><section className="panel appointment"><span className="eyebrow">{rtl ? 'الخطوة التالية' : 'YOUR NEXT STEP'}</span><h2>{stage === 'closed' ? (rtl ? 'تم إغلاق الحلقة' : 'Your care loop is closed') : (rtl ? 'مكالمة مسائية' : 'An evening call')}</h2><div className="appointment-row"><div className="date-tile"><strong>24</strong><span>OCT</span></div><div><strong>Riverside Food Hub</strong><span>Today · 6:30 PM · SMS reminder</span></div></div><button className="outline-btn full" onClick={() => notify(rtl ? 'تم حفظ التغيير محلياً' : 'Appointment change saved locally')}>{rtl ? 'تغيير الوقت' : 'Change time'}</button></section></div><div className="privacy-note"><span>⌁ {rtl ? 'بياناتك آمنة ومستخدمة لتنسيق رعايتك.' : 'Your information is private and used only to coordinate your care.'}</span><span>{rtl ? 'البيانات الاصطناعية' : 'Synthetic data'}</span></div></div>
}

function PatientEnglish({ stage, notify, care }: { stage: Stage; notify: (s: string) => void; care: CareApi }) {
  const [teachBack, setTeachBack] = useState<'understood' | 'needs-help' | null>(null)
  const [answer, setAnswer] = useState('')
  const detail = care.detail

  // The portal signs in as the synthetic patient who owns the open ledger object,
  // because a patient account may only act on its own case (api/service.py, _allowed_case).
  const [portalNote, setPortalNote] = useState('reading the ledger…')

  useEffect(() => {
    careLoopApi.listCases('manager-1').then(list => {
      const open = (list.items ?? []).find(item => item.status !== 'closed')
      if (!open) { setPortalNote('every synthetic ledger object is closed · reload the dataset'); return }
      setPortalNote(`signed in as ${open.patient_id} · ledger object ${open.id}`)
      if (open.id !== care.caseId) care.select(open.id)
    }).catch(() => setPortalNote('ledger unreachable · this portal shows the synthetic narrative only'))
  }, [])

  const requestTime = async () => {
    const asked = await care.run('acknowledge', { intent: 'appointment_request', text: answer || 'I would like an evening call.', channel: 'SMS' }, care.patientActorId)
    const slot = new Date(Date.now() + 3 * 60 * 60 * 1000).toISOString()
    const booked = await care.run('appointment', { scheduled_for: slot }, 'navigator-1')
    care.log('Appointment request sent', asked ? `acknowledge by ${care.patientActorId}` : 'browser only', asked ? 'api' : 'local')
    if (asked && booked) notify(`Slot held for ${slot.replace('T', ' ').slice(0, 16)}Z · booked by navigator-1 because this API does not let a patient create an appointment`)
    else if (asked || booked) notify(`Partly recorded · ${care.lastError || 'one of the two calls was refused'}`)
    else notify(`Request not recorded · ${care.lastError}`)
  }

  const recordTeachBack = async (outcome: 'understood' | 'needs-help') => {
    setTeachBack(outcome)
    const ok = await care.run('teach_back', { outcome: outcome === 'understood' ? 'understood' : 'needs_human_follow_up', answers: [answer || 'No free-text answer typed'] }, care.patientActorId)
    care.log('Teach-back recorded', `${outcome} · ${care.patientActorId}`, ok ? 'api' : 'local')
    notify(ok ? 'Teach-back stored on the ledger as a communication check · not a clinical decision' : `Teach-back kept in this browser only · ${care.lastError}`)
  }

  const booked = (detail?.appointments ?? []).slice(-1)[0]

  return <div className="patient-view"><PageHeading eyebrow="PATIENT PORTAL · SYNTHETIC DATA" title="Hi Samira" subtitle="Here is your next step in plain language."><span className="secure"><i/> {portalNote}</span></PageHeading><section className="patient-hero"><div className="hero-copy"><span className="eyebrow">CARE UPDATE</span><h2>Your screening follow-up needs a next step</h2><p>Riverside Care Team will contact you about the follow-up appointment. This message does not make a diagnosis.</p><div className="hero-actions"><button className="primary-btn" onClick={requestTime}>Request a time <span>→</span></button><button className="text-btn" onClick={() => care.setPassportOpen(true)}>View result passport</button></div><p className="patient-note">Ledger object {care.caseId}{detail ? ` · stage ${detail.stage} · status ${detail.status}` : ' · ledger not reachable'}{booked ? ` · held slot ${booked.scheduled_for.replace('T', ' ').slice(0, 16)}Z` : ' · no slot held yet'}</p></div><div className="map-card"><div className="map-grid"><span className="map-road r1"/><span className="map-road r2"/><span className="map-road r3"/><span className="map-pin">⌂</span><span className="map-you">●</span></div><div className="map-label"><strong>Riverside Care Team</strong><span>Distance is synthetic data</span></div></div></section><div className="patient-columns"><section className="panel teachback"><div className="panel-header"><div><span className="eyebrow">TEACH-BACK</span><h2>What do you think happens next?</h2></div><span className="check-circle">✓</span></div><p>Tell us what you think happens next, in your own words.</p><div className="composer-inline"><input value={answer} onChange={event => setAnswer(event.target.value)} placeholder="Type your answer in your own words" aria-label="Teach-back answer"/></div><div className="teach-options"><button className={teachBack === 'understood' ? 'selected' : ''} onClick={() => recordTeachBack('understood')}>I will describe my next step</button><button className={teachBack === 'needs-help' ? 'selected' : ''} onClick={() => recordTeachBack('needs-help')}>I need help understanding</button></div>{teachBack && <div className="teachback-confirm">{teachBack === 'understood' ? 'Recorded as understood for staff review.' : 'Recorded as needing help · a navigator follows up.'}</div>}<div className="privacy-note">Your response is recorded as a communication check, not a clinical decision.</div></section><section className="panel owner-card"><span className="eyebrow">WHO OWNS MY CASE?</span><div className="owner"><div className="avatar">AM</div><div><strong>{detail ? detail.owner_next : 'navigator-1'}</strong><span>Care navigator</span></div></div><p>Call the care team if nobody contacts you by the deadline shown in your result passport.</p>{detail ? <div className="patient-deadline"><span>DEADLINE</span><strong>{detail.due_at.replace('T', ' ').slice(0, 16)}Z</strong></div> : <p className="muted-block">Deadline not read · the ledger is unreachable.</p>}<StatusPill stage={stage} compact/><button className="outline-btn full" onClick={() => care.setPassportOpen(true)}>Open my result passport</button></section></div></div>
}


function SimulationV2({ notify }: { notify: (s: string) => void }) {
  const [arm, setArm] = useState('B-full')
  const [queuePolicy, setQueuePolicy] = useState('priority')
  const [ran, setRan] = useState(false)
  const [methodOpen, setMethodOpen] = useState(false)
  const [saved, setSaved] = useState(localStorage.getItem('careloop.scenario') ?? '')
  const closure = reproduceRun.closureByArm[arm]
  const core = reproduceRun.coreByArm[arm]
  const visibility = reproduceRun.visibilityByArm[arm]
  const backlog = reproduceRun.backlogByArmPolicy[arm]?.[queuePolicy]
  const primary = arm === 'Arm A' || arm === 'B-full'

  const saveScenario = () => {
    const payload = { arm, queuePolicy, cohort: reproduceRun.cohort, runs: reproduceRun.runs, seed: reproduceRun.seed, at: new Date().toISOString() }
    const text = JSON.stringify(payload)
    localStorage.setItem('careloop.scenario', text)
    setSaved(text)
    notify(`Scenario stored in this browser · localStorage key careloop.scenario · ${arm} · ${queuePolicy}`)
  }

  const loadScenario = () => {
    const raw = localStorage.getItem('careloop.scenario')
    if (!raw) { notify('No stored scenario in this browser yet'); return }
    try {
      const value = JSON.parse(raw) as { arm?: string; queuePolicy?: string }
      if (value.arm && reproduceRun.closureByArm[value.arm] !== undefined) setArm(value.arm)
      if (value.queuePolicy === 'fifo' || value.queuePolicy === 'priority') setQueuePolicy(value.queuePolicy)
      notify(`Scenario restored · ${value.arm ?? 'arm unchanged'} · ${value.queuePolicy ?? 'policy unchanged'}`)
    } catch {
      notify('The stored scenario is not readable JSON · it was left untouched')
    }
  }

  const copyCommand = async () => {
    const command = 'python scripts/reproduce.py --output out'
    try {
      await navigator.clipboard.writeText(command)
      notify('Reproduce command copied to the clipboard')
    } catch {
      notify(`Clipboard blocked by the browser · run ${command}`)
    }
  }

  return <><PageHeading eyebrow="TRANSPORT LEDGER · SYNTHETIC ONLY" title="Simulation lab" subtitle="Compare the event ledger, ablations, and queue policies using the same cohort and seed."><span className="synthetic-chip">✦ Test-run output</span><button className="primary-btn" onClick={() => { setRan(true); notify(`Bounded run loaded · ${reproduceRun.cohort} synthetic cases × ${reproduceRun.runs} replications · seed ${reproduceRun.seed}`) }}>▶ Run bounded simulation</button></PageHeading><div className="simulation-layout"><section className="panel sim-config"><div className="panel-header"><div><span className="eyebrow">SCENARIO BUILDER</span><h2>Screening-to-care loop</h2></div><span className="version">E1–E9</span></div><p>Every partner event is transport-only. Unknown means not visible, not that care did not happen.</p><label>Arm <select value={arm} onChange={event => setArm(event.target.value)}><option>Arm A</option><option>B-full</option><option>B_without_closure_gate</option><option>B_without_absence_detector</option><option>B_without_positive_handoff</option><option>B_without_multilingual_passport</option></select></label><label>Navigator queue policy <select value={queuePolicy} onChange={event => setQueuePolicy(event.target.value)}><option value="priority">Priority: urgency × dropout risk</option><option value="fifo">FIFO</option></select></label><div className="sim-footer"><span>All values are generated test-run outputs, not clinical evidence.</span><button className="outline-btn" onClick={saveScenario}>Save scenario</button><button className="outline-btn" onClick={loadScenario}>Load saved</button></div>{saved && <p className="saved-chip">Stored in this browser: {JSON.parse(saved).arm} · {JSON.parse(saved).queuePolicy} · {String(JSON.parse(saved).at).slice(0, 19)}Z</p>}</section><section className="panel results"><div className="panel-header"><div><span className="eyebrow">GENERATED TEST-RUN OUTPUT</span><h2>{ran ? 'Run selected · just now' : 'Last bounded run'}</h2></div><span className="success-chip">● Seeded</span></div><div className="result-metrics"><div><span>Documented closure</span><strong>{closure === undefined ? '—' : `${(closure * 100).toFixed(2)}%`}</strong><small>{arm} · {reproduceRun.cohort} cases × {reproduceRun.runs} runs</small></div><div><span>Core owner + closure SLA</span><strong>{core === undefined ? 'not reported for this arm' : `${(core * 100).toFixed(2)}%`}</strong><small>named owner and documented closure</small></div><div><span>Queue backlog</span><strong>{backlog ?? 'not reported for this arm'}</strong><small>{queuePolicy} policy · {arm} · seed {reproduceRun.seed}</small></div></div><div className="v2-output-grid"><div><span>Unknown visibility</span><strong>{visibility === undefined ? 'not reported' : `${(visibility.unknownRate * 100).toFixed(2)}%`}</strong></div><div><span>Time in uncertainty</span><strong>{visibility === undefined ? 'not reported' : `${visibility.uncertaintyHours.toFixed(2)}h`}</strong></div><div><span>Consult without referral</span><strong>{visibility === undefined ? 'not reported' : `${(visibility.consultWithoutReferral * 100).toFixed(2)}%`}</strong></div></div>{!primary && <p className="metric-note">Ablation arms report only the documented-closure row in this build; the other three metrics are recorded for Arm A and B-full.</p>}<div className="result-note">ⓘ This screen is linked to the out/reproduce.json artefact and keeps clinical decisions with humans. <button className="text-btn" onClick={() => setMethodOpen(!methodOpen)}>View methodology →</button><button className="text-btn" onClick={copyCommand}>Copy reproduce command</button></div>
      {methodOpen && <div className="method-panel">
        <div className="pop-row"><span>Cohort</span><strong>{reproduceRun.cohort} synthetic cases</strong></div>
        <div className="pop-row"><span>Replications</span><strong>{reproduceRun.runs}</strong></div>
        <div className="pop-row"><span>Seed</span><strong>{reproduceRun.seed}</strong></div>
        <div className="pop-row"><span>Arms compared</span><strong>Arm A vs B-full, plus four ablations</strong></div>
        <div className="pop-row"><span>Source</span><strong>out/reproduce.json · scripts/reproduce.py</strong></div>
        <p>Both arms draw from the same deterministic cohort and paired seeds, so a difference is a difference in the workflow mechanism, not in the population. Queue backlog is compared under FIFO and priority policies. The scale study is a later phase and is not run or reported here.</p>
        <p className="method-limit">Limitation: these are model outputs from configured workflow mechanisms and stated assumptions. They are not clinical evidence, not safety data, and not a population statistic.</p>
      </div>}
    </section></div></>
}


function Simulation({ notify }: { notify: (s: string) => void }) {
  const [running, setRunning] = useState(false)
  const [threshold, setThreshold] = useState(4)
  return <><PageHeading eyebrow="SANDBOX · SYNTHETIC ONLY" title="Simulation lab" subtitle="Explore how small workflow changes affect the care loop."><span className="synthetic-chip">✦ Synthetic environment</span><button className="primary-btn" onClick={() => { setRunning(true); notify('Simulation run started locally') }}>▶ Run simulation</button></PageHeading><div className="simulation-layout"><section className="panel sim-config"><div className="panel-header"><div><span className="eyebrow">SCENARIO BUILDER</span><h2>Stalled referral recovery</h2></div><span className="version">v0.4</span></div><p>Test the intervention that nudges a patient after a screening referral goes unbooked.</p><label>Population <select><option>Northside primary care · 1,000 cases</option></select></label><label>Stall threshold <div className="range-row"><input type="range" min="1" max="7" value={threshold} onChange={event => setThreshold(Number(event.target.value))}/><strong>{threshold} days</strong></div></label><label>Intervention <select><option>Navigator escalation + SMS nudge</option><option>Navigator escalation only</option></select></label><div className="sim-footer"><span>Results are directional, not clinical evidence.</span><button className="outline-btn" onClick={() => notify('Scenario saved locally')}>Save scenario</button></div></section><section className="panel results"><div className="panel-header"><div><span className="eyebrow">PROJECTED OUTCOME</span><h2>{running ? 'Run complete · just now' : 'Last run · local seed'}</h2></div><span className="success-chip">● Ready</span></div><div className="result-metrics"><div><span>Connection rate</span><strong>+12.4%</strong><small>from 61% to 73.4%</small></div><div><span>Median time to care</span><strong>−1.1d</strong><small>from 3.2d to 2.1d</small></div><div><span>Navigator touches</span><strong>+0.4</strong><small>per case on average</small></div></div><div className="chart"><div className="chart-lines"><span/><span/><span/><span/></div><div className="chart-bars"><i style={{ height: '38%' }}/><i style={{ height: '52%' }}/><i style={{ height: '61%' }}/><i style={{ height: '77%' }}/><i style={{ height: '91%' }}/></div><div className="chart-labels"><span>Baseline</span><span>+ nudge</span></div></div><div className="simulation-callout">ⓘ <span>Model outputs are synthetic estimates. A program manager should review assumptions before using them for planning.</span></div></section></div></>
}

function Governance({ notify, care }: { notify: (s: string) => void; care: CareApi }) {
  const [rows, setRows] = useState<{ name: string; use: string; check: string; status: string }[]>([
    { name: 'CareLoop triage helper', use: 'Case prioritization', check: 'Navigator review', status: 'Active' },
    { name: 'Resource matching model', use: 'Program suggestions', check: 'Clinician review', status: 'Active' },
    { name: 'SMS outreach draft', use: 'Patient communication', check: 'Patient consent', status: 'Paused' },
  ])
  const [audit, setAudit] = useState<ApiAuditItem[] | null>(null)
  const [logOpen, setLogOpen] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [draft, setDraft] = useState({ name: '', check: 'Clinician review' })

  const fetchAudit = async (): Promise<ApiAuditItem[] | null> => {
    try {
      const data = await careLoopApi.listAudit(care.actorId)
      setAudit(data.items)
      return data.items
    } catch {
      setAudit(null)
      return null
    }
  }

  const viewLog = async () => {
    const items = await fetchAudit()
    if (items === null) { notify('Activity log needs the API · nothing was invented'); return }
    setLogOpen(true)
    notify(`Activity log loaded · ${items.length} audit rows read from GET /audit as ${care.actorId}`)
  }

  const exportLog = async () => {
    const items = audit ?? await fetchAudit()
    if (!items) { notify('Export needs a reachable API · no file was written'); return }
    if (items.length === 0) { notify('The audit table is empty · perform a case action first'); return }
    const csv = ['id,case_id,actor_id,action,created_at,payload', ...items.map(item => [item.id, item.case_id ?? '', item.actor_id, item.action, item.created_at, JSON.stringify(item.payload)].map(value => `"${String(value).replace(/"/g, '""')}"`).join(','))].join('\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `careloop-activity-${new Date().toISOString().slice(0, 10)}.csv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 2000)
    setLogOpen(true)
    notify(`CSV built from the audit table · ${items.length} rows handed to the browser download`)
  }

  const addPolicy = () => {
    const name = draft.name.trim()
    if (!name) { notify('Name the automation before adding it to the register'); return }
    setRows(current => [...current, { name, use: 'Program oversight', check: draft.check, status: 'Draft' }])
    setDraft({ name: '', check: draft.check })
    setAddOpen(false)
    care.log('Policy draft added', name, 'local')
    notify('Draft added to the register in this browser · the register is not persisted by the API')
  }

  return <><PageHeading eyebrow="PROGRAM · OVERSIGHT" title="Governance" subtitle="Make automation visible, reviewable, and accountable across the loop."><button className="outline-btn" onClick={exportLog}>Export activity log ↓</button><button className="primary-btn" onClick={() => setAddOpen(!addOpen)}>＋ Add policy</button></PageHeading>
    {addOpen && <div className="note-composer"><input value={draft.name} onChange={event => setDraft({ ...draft, name: event.target.value })} onKeyDown={event => event.key === 'Enter' && addPolicy()} placeholder="Name of the automation or policy" aria-label="Policy name"/><select value={draft.check} onChange={event => setDraft({ ...draft, check: event.target.value })} aria-label="Human check"><option>Clinician review</option><option>Navigator review</option><option>Patient consent</option><option>Program manager review</option></select><button className="primary-btn" onClick={addPolicy}>Add to register</button><button className="text-btn" onClick={() => setAddOpen(false)}>Cancel</button></div>}
    <div className="governance-metrics"><Metric label="Automations listed" value={String(rows.length)} tone="blue" icon="✦"/><Metric label="Audit rows in store" value={audit === null ? 'not read' : String(audit.length)} tone="green" icon="✓"/><Metric label="Ledger object in view" value={care.detail ? care.detail.status : 'not read'} tone="purple" icon="◎"/></div>
    <section className="panel governance-table"><div className="panel-header"><div><span className="eyebrow">AUTOMATION REGISTER</span><h2>What is helping your team</h2></div><button className="text-btn" onClick={viewLog}>View activity log →</button></div><div className="gov-head"><span>AUTOMATION</span><span>USE</span><span>HUMAN CHECK</span><span>STATUS</span></div>{rows.map(row => <div className="gov-row" key={row.name}><div><div className="automation-icon">✦</div><strong>{row.name}</strong></div><span>{row.use}</span><span>{row.check}</span><span className={`gov-status ${row.status.toLowerCase()}${row.status === 'Draft' ? ' local' : ''}`}><i/>{row.status}</span></div>)}
      {logOpen && <div className="audit-panel">
        <div className="panel-header"><div><span className="eyebrow">ACTIVITY LOG · READ FROM THE API</span><h2>{audit?.length ?? 0} audit rows</h2></div><button className="text-btn" onClick={exportLog}>Export CSV ↓</button></div>
        <div className="audit-head"><span>#</span><span>CASE</span><span>ACTOR</span><span>ACTION</span><span>WHEN</span></div>
        {(audit ?? []).slice().reverse().slice(0, 40).map(item => <div className="audit-row" key={item.id}><b>{item.id}</b><span>{item.case_id ?? '—'}</span><span>{item.actor_id}</span><strong>{item.action}</strong><span>{item.created_at.replace('T', ' ').slice(0, 19)}Z</span></div>)}
        {audit?.length === 0 && <p className="muted-block">The audit table has no rows yet · run the dataset or any case action first.</p>}
        <p className="metric-note">Read-only view of the append-only audit table, opened with X-Actor-ID {care.actorId}. Patients are refused this endpoint by design.</p>
      </div>}
    </section><div className="governance-grid"><section className="panel principle"><span className="eyebrow">CARELOOP PRINCIPLE</span><h2>Automation should make care more human.</h2><p>Every suggestion has a visible owner. Every patient-facing action requires consent. Every decision can be explained.</p><div className="principles"><span>✓ Explainable</span><span>✓ Reversible</span><span>✓ Human-led</span></div></section><section className="panel data-card"><span className="eyebrow">DATA CONTROLS</span><div className="control"><span><strong>Synthetic data</strong><small>Synthetic records cannot reach a real patient.</small></span><b className="toggle on">On</b></div><div className="control"><span><strong>Human review gate</strong><small>Required for patient-facing actions.</small></span><b className="toggle on">On</b></div><div className="control"><span><strong>Model suggestions</strong><small>Visible, reversible, and logged.</small></span><b className="toggle on">On</b></div></section></div></>
}

export default App
