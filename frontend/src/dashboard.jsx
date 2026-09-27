import React, { useEffect, useRef, useState } from 'react'
import {
  Activity, AlertTriangle, ArrowDownToLine, Bot, Check, CheckCheck, ChevronDown,
  Clock3, Database, Eye, ExternalLink, Filter, Gauge, Layers3, Map, MapPinned,
  MessageCircle, Search, Send, ShieldCheck, Sparkles, Upload, X,
} from 'lucide-react'
import MapView from './map-view'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'
const API_ROOT = API_URL.replace(/\/api\/?$/, '')
const NAV_ITEMS = [
  { id: 'overview', label: 'Overview', icon: Activity },
  { id: 'parcels', label: 'Parcel map', icon: Map },
  { id: 'reconciliation', label: 'Reconciliation', icon: Sparkles },
  { id: 'audit', label: 'Audit log', icon: ShieldCheck },
]
const QUICK_SAMPLES = [
  { id: 'overlap', fileName: 'sih-sample-parcels.geojson', label: 'Overlap + isolated', path: '/sih-sample-parcels.geojson', crs: 'EPSG:4326', description: 'One parcel overlaps 704-B; one has no nearby candidate.' },
  { id: 'duplicate', fileName: 'duplicate-candidate.geojson', label: 'Duplicate candidate', path: '/samples/duplicate-candidate.geojson', crs: 'EPSG:4326', description: 'An identical footprint tests duplicate parcel detection.' },
  { id: 'nearby', fileName: 'nearby-boundary.geojson', label: 'Nearby boundary', path: '/samples/nearby-boundary.geojson', crs: 'EPSG:4326', description: 'A nearby non-overlapping parcel tests proximity matching.' },
  { id: 'mercator', fileName: 'web-mercator.geojson', label: 'Web Mercator import', path: '/samples/web-mercator.geojson', crs: 'EPSG:3857', description: 'Projected coordinates test CRS normalization into WGS 84.' },
]

function getAssistantSessionId() {
  const storageKey = 'landsync-assistant-session'
  const existing = window.localStorage.getItem(storageKey)
  if (existing) return existing
  const created = globalThis.crypto?.randomUUID?.() || `session-${Date.now()}-${Math.random().toString(36).slice(2)}`
  window.localStorage.setItem(storageKey, created)
  return created
}

async function api(path, options) {
  const response = await fetch(`${API_URL}${path}`, options)
  const result = await response.json()
  if (!response.ok) throw new Error(result.detail || result.error || 'Request failed')
  return result
}

async function getApiHealth() {
  const response = await fetch(`${API_ROOT}/health`)
  const result = await response.json()
  if (!response.ok) throw new Error('Health check failed')
  return result
}

function StatusPill({ children, tone = 'neutral' }) {
  return <span className={`status-pill tone-${tone}`}>{children}</span>
}

function getParcelComparison(parcel) {
  const assessment = parcel?.assessment
  if (!assessment) return null
  return assessment.comparison_type === 'source_boundary_comparison'
    ? assessment
    : assessment.candidate_matches?.[0] || null
}

function getSpatialScoreLabel(parcel) {
  if (!parcel?.assessment) return 'Not analyzed'
  if (parcel.assessment.comparison_type === 'cross_parcel_candidate_search' && !parcel.assessment.candidate_matches?.length) return 'No candidate'
  return `${parcel.assessment.match_score}%`
}

function AnalysisCard({ result }) {
  const candidate = result.candidate_matches?.[0]
  const isSourcePair = result.comparison_type === 'source_boundary_comparison'
  const summary = isSourcePair
    ? `IoU ${result.intersection_over_union_percent}% · area delta ${result.geometry_area_delta_m2} m² · boundary ${result.boundary_hausdorff_distance_m} m`
    : candidate
      ? `Candidate ${candidate.parcel_id} · ${candidate.intersection_over_union_percent}% IoU · ${candidate.distance_m} m apart`
      : 'No overlapping or nearby parcel candidate in this dataset.'

  return <article className="event-card">
    <div className="event-top"><span>PARCEL {result.parcel_id}</span><span>{isSourcePair ? 'SOURCE PAIR' : 'CANDIDATE SEARCH'}</span></div>
    <strong>{isSourcePair ? `${result.source_a} vs. ${result.source_b}` : 'Cross-source candidate search'}</strong>
    <p>{summary} {result.reasons.join(' ')}</p>
    <div className="event-bottom"><StatusPill tone={result.requires_review ? 'warning' : 'success'}>{result.requires_review ? 'REVIEW' : 'WITHIN TOLERANCE'}</StatusPill><span>{candidate || isSourcePair ? `Score ${result.match_score}%` : 'No candidate'}</span></div>
  </article>
}

function SamplePreview({ preview, busy, onClose, onImport }) {
  const features = preview.payload.features || []
  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <section className="sample-dialog" role="dialog" aria-modal="true" aria-labelledby="sample-dialog-title">
        <header className="dialog-header"><div><span className="eyebrow">QUICK-CHECK DATASET</span><h2 id="sample-dialog-title">{preview.sample.label}</h2></div><button className="icon-button" aria-label="Close sample preview" onClick={onClose}><X size={17} /></button></header>
        <div className="sample-file-name"><Database size={15} /><span>{preview.sample.fileName}</span><span className="crs-tag">{preview.sample.crs}</span></div>
        <p className="sample-description">{preview.sample.description}</p>
        <div className="sample-feature-list">{features.map((feature, index) => <div className="sample-feature" key={`${feature.properties?.parcel_id || 'feature'}-${index}`}><span>FEATURE {index + 1}</span><strong>{feature.properties?.parcel_id || 'Unlabelled parcel'}</strong><small>{feature.properties?.source || 'No source label'} · {feature.properties?.area ?? 'area not supplied'} m²</small></div>)}</div>
        <details className="sample-json"><summary>View GeoJSON excerpt</summary><pre>{JSON.stringify({ type: preview.payload.type, name: preview.payload.name, source_crs: preview.payload.source_crs, feature_count: features.length, features: features.slice(0, 2) }, null, 2)}</pre></details>
        <footer className="dialog-actions"><button className="button secondary" onClick={onClose}>Close</button><button className="button primary" disabled={busy} onClick={onImport}><Upload size={15} /> {busy ? 'Importing...' : 'Import and analyze'}</button></footer>
      </section>
    </div>
  )
}

function AssistantPanel({ messages, input, busy, onInput, onClose, onSend, endRef }) {
  const suggestions = ['What is the spatial score?', 'Which parcels need review?', 'Why did a boundary get flagged?']
  return (
    <section className="assistant-panel" aria-label="LandSync spatial assistant">
      <header className="assistant-header"><div className="assistant-brand"><span className="assistant-avatar"><Bot size={18} /></span><span><strong>LandSync assistant</strong><small><span className="online-indicator" /> Workspace-aware · remembers this chat</small></span></div><button className="icon-button" aria-label="Close assistant" onClick={onClose}><X size={17} /></button></header>
      <div className="assistant-disclosure">Answers use this workspace and may search Wikipedia for general geospatial references. Verify standards with their issuing authority.</div>
      <div className="assistant-messages" aria-live="polite">
        {!messages.length && <div className="assistant-welcome"><span className="welcome-mark"><Sparkles size={20} /></span><strong>What would you like to inspect?</strong><p>Ask about a parcel, a geometry flag, coordinate systems, or the review workflow.</p><div className="assistant-suggestions">{suggestions.map((suggestion) => <button key={suggestion} disabled={busy} onClick={() => onSend(suggestion)}>{suggestion}</button>)}</div></div>}
        {messages.map((message, index) => <article className={`assistant-message ${message.role}`} key={`${message.role}-${index}`}><span className="message-role">{message.role === 'user' ? 'YOU' : 'LANDSYNC'}</span><p>{message.content}</p>{message.sources?.map((source) => <a className="assistant-source" href={source.url} target="_blank" rel="noreferrer" key={source.url}><ExternalLink size={12} /><span><strong>{source.title}</strong><small>{source.snippet}</small></span></a>)}</article>)}
        {busy && <div className="assistant-thinking"><span /><span /><span /> Looking up workspace and public references</div>}
        <div ref={endRef} />
      </div>
      <form className="assistant-composer" onSubmit={(event) => { event.preventDefault(); onSend() }}><textarea value={input} maxLength={2000} rows={2} placeholder="Ask about this workspace..." aria-label="Message LandSync assistant" onChange={(event) => onInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); onSend() } }} /><button className="send-button" type="submit" aria-label="Send message" disabled={!input.trim() || busy}><Send size={16} /></button></form>
      <div className="assistant-footer">Workspace answers + public web references · Not a legal opinion</div>
    </section>
  )
}

function Dashboard() {
  const [view, setView] = useState('overview')
  const [overview, setOverview] = useState(null)
  const [apiHealth, setApiHealth] = useState(null)
  const [parcels, setParcels] = useState([])
  const [harmonization, setHarmonization] = useState([])
  const [queue, setQueue] = useState([])
  const [audit, setAudit] = useState([])
  const [selectedId, setSelectedId] = useState('704-B')
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('All statuses')
  const [layers, setLayers] = useState({ cadastral: true, municipal: true })
  const [busyId, setBusyId] = useState('')
  const [sourceCrs, setSourceCrs] = useState('EPSG:4326')
  const [selectedSampleId, setSelectedSampleId] = useState(QUICK_SAMPLES[0].id)
  const [samplePreview, setSamplePreview] = useState(null)
  const [sampleBusy, setSampleBusy] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [notice, setNotice] = useState(null)
  const [loading, setLoading] = useState(true)
  const [assistantOpen, setAssistantOpen] = useState(false)
  const [assistantSessionId] = useState(getAssistantSessionId)
  const [assistantMessages, setAssistantMessages] = useState([])
  const [assistantInput, setAssistantInput] = useState('')
  const [assistantBusy, setAssistantBusy] = useState(false)
  const [assistantLoaded, setAssistantLoaded] = useState(false)
  const searchRef = useRef(null)
  const assistantEndRef = useRef(null)
  const selectedSample = QUICK_SAMPLES.find((sample) => sample.id === selectedSampleId) || QUICK_SAMPLES[0]

  async function refresh() {
    setLoading(true)
    try {
      const [nextOverview, nextParcels, nextHarmonization, nextQueue, nextAudit, nextApiHealth] = await Promise.all([
        api('/overview'), api('/parcels'), api('/harmonization'), api('/review-queue'), api('/audit'), getApiHealth(),
      ])
      setOverview(nextOverview)
      setApiHealth(nextApiHealth)
      setParcels(nextParcels)
      setHarmonization(nextHarmonization)
      setQueue(nextQueue)
      setAudit(nextAudit)
      setSelectedId((current) => nextParcels.some((parcel) => parcel.id === current) ? current : nextParcels[0]?.id)
      setNotice(null)
    } catch (error) {
      setNotice({ type: 'error', text: `${error.message}. Check that the API is running.` })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { refresh() }, [])

  useEffect(() => {
    function handleSearchShortcut(event) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        searchRef.current?.focus()
      }
    }
    window.addEventListener('keydown', handleSearchShortcut)
    return () => window.removeEventListener('keydown', handleSearchShortcut)
  }, [])

  useEffect(() => {
    if (!notice) return undefined
    const timer = window.setTimeout(() => setNotice(null), 5500)
    return () => window.clearTimeout(timer)
  }, [notice])

  useEffect(() => {
    assistantEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [assistantMessages, assistantBusy])

  const selectedParcel = parcels.find((parcel) => parcel.id === selectedId)
  const filteredParcels = parcels.filter((parcel) => {
    const matchesQuery = `${parcel.id} ${parcel.owner} ${parcel.source}`.toLowerCase().includes(query.toLowerCase())
    const matchesStatus = statusFilter === 'All statuses' || parcel.status === statusFilter
    return matchesQuery && matchesStatus
  })
  const openCases = queue.filter((item) => !['Approved', 'Rejected'].includes(item.review_status)).length

  async function makeDecision(item, decision, note = '') {
    setBusyId(item.case_id)
    try {
      const labels = { approve: 'approved', reject: 'rejected', escalate: 'escalated' }
      await api(`/review/${encodeURIComponent(item.case_id)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision, actor: 'District Review Officer', note }),
      })
      await refresh()
      setNotice({ type: 'success', text: `${item.parcel_id} ${labels[decision]}. The decision was added to the audit log.` })
    } catch (error) {
      setNotice({ type: 'error', text: error.message })
    } finally {
      setBusyId('')
    }
  }

  async function importDataset(payload, crs, sourceLabel) {
    const result = await api(`/ingest?source_crs=${encodeURIComponent(crs)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const analysis = await api('/harmonize', { method: 'POST' })
    await refresh()
    setView('reconciliation')
    setNotice({ type: 'success', text: `${sourceLabel}: ${result.imported_count} feature${result.imported_count === 1 ? '' : 's'} normalized to WGS 84; ${analysis.flagged_count} geometry comparison${analysis.flagged_count === 1 ? '' : 's'} flagged for officer review.` })
  }

  async function importFile(event) {
    const file = event.target.files?.[0]
    if (!file) return
    try {
      const payload = JSON.parse(await file.text())
      await importDataset(payload, sourceCrs, file.name)
    } catch (error) {
      setNotice({ type: 'error', text: error instanceof SyntaxError ? 'Could not read this file as GeoJSON.' : error.message })
    } finally {
      event.target.value = ''
    }
  }

  async function readQuickSample(sample = selectedSample) {
    const response = await fetch(sample.path)
    if (!response.ok) throw new Error(`Could not load ${sample.fileName}`)
    return response.json()
  }

  async function previewQuickSample() {
    setSampleBusy(true)
    try {
      const payload = await readQuickSample()
      setSamplePreview({ sample: selectedSample, payload })
    } catch (error) {
      setNotice({ type: 'error', text: error.message })
    } finally {
      setSampleBusy(false)
    }
  }

  async function importQuickSample(sample = selectedSample) {
    setSampleBusy(true)
    try {
      const payload = await readQuickSample(sample)
      const runTag = globalThis.crypto?.randomUUID?.().slice(0, 8) || `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
      const uniquePayload = {
        ...payload,
        features: payload.features.map((feature, index) => ({
          ...feature,
          properties: {
            ...feature.properties,
            parcel_id: `${feature.properties?.parcel_id || `QUICK-${index + 1}`}-RUN-${runTag}-${index + 1}`,
          },
        })),
      }
      setSourceCrs(sample.crs)
      setSamplePreview(null)
      await importDataset(uniquePayload, sample.crs, sample.fileName)
    } catch (error) {
      setNotice({ type: 'error', text: error instanceof SyntaxError ? 'The selected sample is not valid GeoJSON.' : error.message })
    } finally {
      setSampleBusy(false)
    }
  }

  async function openAssistant() {
    setAssistantOpen(true)
    if (assistantLoaded) return
    try {
      const history = await api(`/assistant/session/${encodeURIComponent(assistantSessionId)}`)
      setAssistantMessages(history.messages || [])
      setAssistantLoaded(true)
    } catch (error) {
      setAssistantMessages([{ role: 'assistant', content: `I could not load saved chat history: ${error.message}` }])
    }
  }

  async function sendAssistantMessage(message = assistantInput) {
    const content = message.trim()
    if (!content || assistantBusy) return
    setAssistantInput('')
    setAssistantBusy(true)
    setAssistantMessages((current) => [...current, { role: 'user', content }])
    try {
      const result = await api('/assistant/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: assistantSessionId, message: content }),
      })
      setAssistantMessages((current) => [...current, { role: 'assistant', content: result.reply, sources: result.sources || [] }])
    } catch (error) {
      setAssistantMessages((current) => [...current, { role: 'assistant', content: `I could not complete that lookup: ${error.message}` }])
    } finally {
      setAssistantBusy(false)
      setAssistantLoaded(true)
    }
  }
  async function runHarmonization() {
    setAnalyzing(true)
    try {
      const result = await api('/harmonize', { method: 'POST' })
      await refresh()
      setNotice({ type: 'success', text: `Analyzed ${result.analyzed_count} parcel geometries; ${result.flagged_count} comparison${result.flagged_count === 1 ? '' : 's'} require human review.` })
    } catch (error) {
      setNotice({ type: 'error', text: error.message })
    } finally {
      setAnalyzing(false)
    }
  }

  function exportParcels() {
    const columns = ['id', 'owner', 'status', 'source', 'spatial_score', 'recorded_area', 'municipal_area']
    const encodeCell = (value) => {
      const text = String(value ?? '')
      const safeText = /^[=+\-@\t\r]/.test(text) ? `'${text}` : text
      return `"${safeText.replaceAll('"', '""')}"`
    }
    const rows = filteredParcels.map((parcel) => columns.map((key) => encodeCell(parcel[key])).join(','))
    const csv = [columns.join(','), ...rows].join('\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = 'landsync-parcels.csv'
    link.click()
    URL.revokeObjectURL(url)
    setNotice({ type: 'success', text: `${filteredParcels.length} parcel records exported as CSV.` })
  }

  const title = NAV_ITEMS.find((item) => item.id === view)?.label || 'Overview'

  return (
    <div className="workspace">
      <aside className="sidebar">
        <a className="brand" href="#overview" onClick={() => setView('overview')}>
          <span className="brand-mark"><MapPinned size={21} /></span>
          <span><strong>LandSync<span>.AI</span></strong><small>GEO HARMON-X</small></span>
        </a>

        <div className="workspace-label">WORKSPACE</div>
        <div className="district-select"><span className="district-dot" /> East Ridge District</div>

        <div className="sidebar-label">OPERATIONS</div>
        <nav className="side-nav" aria-label="Main navigation">
          {NAV_ITEMS.map(({ id, label, icon: Icon }) => (
            <button key={id} className={`nav-item${view === id ? ' active' : ''}`} onClick={() => setView(id)}>
              <Icon size={17} strokeWidth={1.8} />
              <span>{label}</span>
              {id === 'reconciliation' && openCases > 0 && <span className="nav-count">{openCases}</span>}
            </button>
          ))}
        </nav>

        <div className="sidebar-label source-label">DATA SOURCES</div>
        <div className="source-row"><span className="source-square cadastral" /> Cadastral registry <StatusPill>SAMPLE</StatusPill></div>
        <div className="source-row"><span className="source-square municipal" /> Municipal GIS <StatusPill>SAMPLE</StatusPill></div>
        <div className="source-row"><span className="source-square survey" /> Field survey <StatusPill>SAMPLE</StatusPill></div>

        <div className="sidebar-bottom">
          <div className="integrity-card">
            <span className="integrity-icon"><ShieldCheck size={16} /></span>
            <div><strong>Spatial store</strong><small>{apiHealth ? `${apiHealth.storage.toUpperCase()} · persisted` : loading ? 'Checking API' : 'API unavailable'}</small></div>
            <span className="online-indicator" />
          </div>
          <div className="profile-row"><span className="avatar">DR</span><span><strong>District Reviewer</strong><small>Land administration</small></span></div>
        </div>
      </aside>

      <main className="main-area">
        <header className="main-header">
          <div className="breadcrumbs"><span>East Ridge District</span><span className="crumb-sep">/</span><strong>{title}</strong></div>
          <div className="header-tools">
            <label className="global-search"><Search size={16} /><input ref={searchRef} value={query} onChange={(event) => { setQuery(event.target.value); if (event.target.value) setView('parcels') }} placeholder="Search parcel, owner, source..." /><kbd>Ctrl K</kbd></label>
            <span className="header-status"><span className="online-indicator" /> {loading ? 'Syncing' : 'All systems normal'}</span>
            <button className="icon-button" aria-label="Refresh data" title="Refresh data" onClick={refresh}><Activity size={17} /></button>
            <button className="user-button" aria-label="Open app assistant" title="Open app assistant" onClick={openAssistant}><MessageCircle size={18} /></button>
          </div>
        </header>

        <div className="page-content">
          {notice && <div className={`notice ${notice.type}`} role="status"><span>{notice.text}</span><button aria-label="Dismiss message" onClick={() => setNotice(null)}><X size={16} /></button></div>}

          <div className="page-heading">
            <div><div className="eyebrow">GEOSPATIAL LAND ADMINISTRATION</div><h1>{view === 'overview' ? 'District overview' : title}</h1><p>{view === 'overview' ? 'Compare source boundaries, inspect measured differences, and route uncertain matches to human review.' : view === 'parcels' ? 'Inspect normalized source boundaries, compare parcel footprints, and export the current inventory.' : view === 'reconciliation' ? 'Review computed spatial evidence. Human approval remains the authority for record changes.' : 'A traceable history of imports, analyses, and officer decisions.'}</p></div>
            <div className="heading-actions">
              <label className="crs-control" title="Coordinate reference system for the incoming GeoJSON coordinates"><span>Input CRS</span><select value={sourceCrs} onChange={(event) => setSourceCrs(event.target.value)}><option value="EPSG:4326">EPSG:4326</option><option value="EPSG:3857">EPSG:3857</option><option value="EPSG:32643">EPSG:32643</option><option value="EPSG:32743">EPSG:32743</option></select></label>
              <label className="button secondary upload-button"><Upload size={15} /> Import GeoJSON<input type="file" accept=".json,.geojson,application/geo+json,application/json" onChange={importFile} /></label>
              <div className="sample-picker"><select aria-label="Quick-check GeoJSON file" value={selectedSampleId} onChange={(event) => { const sample = QUICK_SAMPLES.find((item) => item.id === event.target.value); setSelectedSampleId(event.target.value); if (sample) setSourceCrs(sample.crs) }}>{QUICK_SAMPLES.map((sample) => <option key={sample.id} value={sample.id}>{sample.fileName}</option>)}</select><button className="icon-button sample-preview-button" aria-label={`Preview ${selectedSample.fileName}`} title={`Preview ${selectedSample.fileName}`} disabled={sampleBusy} onClick={previewQuickSample}><Eye size={16} /></button></div>
              <div className="export-analysis-group"><button className="button secondary" onClick={exportParcels}><ArrowDownToLine size={16} /> Export CSV</button><button className="button primary" disabled={analyzing || loading} onClick={runHarmonization}><Gauge size={15} /> {analyzing ? 'Analyzing...' : 'Analyze boundaries'}</button></div>
            </div>
          </div>

          <section className="metric-strip" aria-label="District metrics">
            {(overview?.metrics || []).map((metric, index) => {
              const MetricIcon = [MapPinned, Database, Clock3, CheckCheck][index] || Activity
              return <article className="metric" key={metric.label}><span className="metric-icon"><MetricIcon size={17} /></span><div><span className="metric-label">{metric.label}</span><strong>{metric.value}</strong></div><span className="metric-note">{index === 2 ? 'needs attention' : 'demo workspace'}</span></article>
            })}
          </section>

          {view === 'overview' && <OverviewView parcels={parcels} harmonization={harmonization} selectedParcel={selectedParcel} selectedId={selectedId} setSelectedId={setSelectedId} layers={layers} setLayers={setLayers} queue={queue} setView={setView} />}
          {view === 'parcels' && <ParcelsView parcels={filteredParcels} selectedParcel={selectedParcel} selectedId={selectedId} setSelectedId={setSelectedId} layers={layers} setLayers={setLayers} statusFilter={statusFilter} setStatusFilter={setStatusFilter} setView={setView} />}
          {view === 'reconciliation' && <ReconciliationView queue={queue} parcels={parcels} busyId={busyId} onDecision={makeDecision} onInspectParcel={(id) => { setSelectedId(id); setQuery(''); setStatusFilter('All statuses'); setView('parcels') }} />}
          {view === 'audit' && <AuditView audit={audit} />}

          <footer className="page-footer"><span><ShieldCheck size={14} /> LandSync AI · SIH 2026 prototype</span><span>Sample data only · Not an official land record</span></footer>
        </div>
      </main>
      {samplePreview && <SamplePreview preview={samplePreview} busy={sampleBusy} onClose={() => setSamplePreview(null)} onImport={() => importQuickSample(samplePreview.sample)} />}
      {assistantOpen ? <AssistantPanel messages={assistantMessages} input={assistantInput} busy={assistantBusy} onInput={setAssistantInput} onClose={() => setAssistantOpen(false)} onSend={sendAssistantMessage} endRef={assistantEndRef} /> : <button className="assistant-launcher" aria-label="Open LandSync assistant" title="Open LandSync assistant" onClick={openAssistant}><Bot size={21} /><span>Ask LandSync</span></button>}
    </div>
  )
}

function OverviewView({ parcels, harmonization, selectedParcel, selectedId, setSelectedId, layers, setLayers, queue, setView }) {
  const pendingCount = queue.filter((item) => !['Approved', 'Rejected'].includes(item.review_status)).length
  return (
    <>
      <div className="overview-grid">
        <section className="panel map-panel">
          <PanelHeading eyebrow="DISTRICT PARCEL LAYERS" title="Boundary comparison" trailing={<span className="crs-tag">EPSG:4326</span>} />
          <LayerControls layers={layers} setLayers={setLayers} />
          <MapView parcels={parcels} selectedParcel={selectedParcel} layers={layers} onSelectParcel={setSelectedId} />
          <div className="map-legend-row"><span><i className="legend-mark cadastral" /> Cadastral boundary</span><span><i className="legend-mark municipal" /> Municipal boundary</span><span className="map-hint">Select a parcel boundary to inspect</span></div>
        </section>
        <ParcelInspector parcel={selectedParcel} setView={setView} />
      </div>

      <div className="lower-grid">
        <section className="panel inventory-panel">
          <PanelHeading eyebrow="PARCEL INVENTORY" title="Recently inspected" trailing={<button className="text-button" onClick={() => setView('parcels')}>View all <span>→</span></button>} />
          <ParcelTable parcels={parcels.slice(0, 5)} selectedId={selectedId} onSelect={(id) => { setSelectedId(id); setView('parcels') }} />
        </section>
        <section className="panel attention-panel">
          <PanelHeading eyebrow="NEEDS ATTENTION" title="Review queue" trailing={<StatusPill tone={pendingCount ? 'warning' : 'success'}>{pendingCount} OPEN</StatusPill>} />
          <div className="attention-list">
            {queue.filter((item) => !['Approved', 'Rejected'].includes(item.review_status)).slice(0, 3).map((item) => (
              <button className="attention-item" key={item.case_id} onClick={() => { setSelectedId(item.parcel_id); setView('reconciliation') }}>
                <span className="attention-icon"><AlertTriangle size={16} /></span><span className="attention-copy"><strong>Parcel {item.parcel_id}</strong><small>{item.issue}</small></span><span className="attention-arrow">→</span>
              </button>
            ))}
            {!pendingCount && <div className="empty-state compact"><Check size={18} /> No cases are waiting for a decision.</div>}
          </div>
          <button className="queue-link" onClick={() => setView('reconciliation')}>Open reconciliation workspace <span>→</span></button>
        </section>
      </div>
      <section className="panel activity-panel">
        <PanelHeading eyebrow="EXPLAINABLE SPATIAL CHECKS" title="Latest geometry analysis" trailing={<StatusPill tone={harmonization.some((item) => item.requires_review) ? 'warning' : 'neutral'}>{harmonization.length} CHECKS</StatusPill>} />
        {harmonization.length ? <div className="event-grid">{harmonization.slice(0, 3).map((result) => <AnalysisCard key={result.parcel_id} result={result} />)}</div> : <div className="empty-state compact"><Gauge size={17} />No geometry analysis yet. Select Analyze boundaries to calculate overlap, area variance, and boundary distance.</div>}
      </section>
      <p className="decision-note"><ShieldCheck size={15} /> Harmonization scores are recommendations only. Legal decisions require authorized officer review.</p>
    </>
  )
}

function ParcelsView({ parcels, selectedParcel, selectedId, setSelectedId, layers, setLayers, statusFilter, setStatusFilter, setView }) {
  return (
    <div className="parcel-workspace">
      <section className="panel map-panel full-map-panel">
        <PanelHeading eyebrow="SOURCE OVERLAY" title="Explore parcel boundaries" trailing={<label className="filter-select"><Filter size={14} /><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option>All statuses</option><option>Inspection Complete</option><option>Flagged</option><option>Validated</option><option>Needs review</option></select><ChevronDown size={14} /></label>} />
        <LayerControls layers={layers} setLayers={setLayers} />
        <MapView parcels={parcels} selectedParcel={selectedParcel} layers={layers} onSelectParcel={setSelectedId} />
        <div className="map-legend-row"><span><i className="legend-mark cadastral" /> Cadastral boundary</span><span><i className="legend-mark municipal" /> Municipal boundary</span><span className="map-hint">{parcels.length} visible parcels</span></div>
      </section>
      <div className="parcel-details-grid">
        <section className="panel inventory-panel"><PanelHeading eyebrow="PARCEL REGISTER" title="Available records" trailing={<span className="record-count">{parcels.length} records</span>} /><ParcelTable parcels={parcels} selectedId={selectedId} onSelect={setSelectedId} /></section>
        <ParcelInspector parcel={selectedParcel} setView={setView} />
      </div>
    </div>
  )
}

function ReconciliationView({ queue, parcels, busyId, onDecision, onInspectParcel }) {
  const [notes, setNotes] = useState({})
  return (
    <section className="panel reconciliation-panel">
      <PanelHeading eyebrow="HUMAN-IN-THE-LOOP" title="Cases requiring a decision" trailing={<span className="record-count">{queue.length} total cases</span>} />
      <div className="safety-banner"><ShieldCheck size={17} /><span><strong>Spatial analysis informs; officers decide.</strong> Review source records and geometry before approving any change. Decisions are recorded in the audit log.</span></div>
      <div className="case-list">
        {queue.map((item) => {
          const parcel = parcels.find((record) => record.id === item.parcel_id)
          const comparison = getParcelComparison(parcel)
          const closed = ['Approved', 'Rejected'].includes(item.review_status)
          return <article className="case-card" key={item.case_id}>
            <div className="case-card-top"><div><span className="case-number">{item.case_id}</span><h3>Parcel {item.parcel_id}</h3></div><StatusPill tone={item.review_status === 'Approved' ? 'success' : item.review_status === 'Rejected' ? 'danger' : item.review_status.startsWith('Escalated') ? 'warning' : 'neutral'}>{item.review_status}</StatusPill></div>
            <p className="case-issue">{item.issue}</p>
            <div className="case-facts"><span>Record holder<strong>{item.owner}</strong></span><span>Sources<strong>{parcel?.source || 'Imported GeoJSON'}</strong></span><span>Spatial score<strong>{getSpatialScoreLabel(parcel)}</strong></span><span>Geometry delta<strong>{comparison ? `${comparison.geometry_area_delta_m2} m²` : parcel?.assessment ? 'No candidate' : 'Run analysis'}</strong></span></div>
            {parcel?.assessment && <div className="analysis-reasons">{parcel.assessment.reasons.map((reason) => <span key={reason}>{reason}</span>)}{parcel.assessment.candidate_matches?.map((candidate) => <span key={candidate.parcel_id}>Candidate: {candidate.parcel_id} · {candidate.intersection_over_union_percent}% IoU · {candidate.distance_m} m</span>)}</div>}
            <label className="review-note"><span>Officer rationale <small>Optional · stored in the audit log</small></span><textarea value={notes[item.case_id] || ''} maxLength={1000} placeholder="Add a short reason for this decision" onChange={(event) => setNotes((current) => ({ ...current, [item.case_id]: event.target.value }))} /></label>
            <div className="case-card-actions"><button className="button tertiary" onClick={() => onInspectParcel(item.parcel_id)}><MapPinned size={15} /> Inspect parcel</button><div className="decision-actions"><button className="button danger-outline" disabled={closed || busyId === item.case_id} onClick={() => onDecision(item, 'reject', notes[item.case_id] || '')}><X size={15} /> Reject</button><button className="button secondary" disabled={closed || busyId === item.case_id} onClick={() => onDecision(item, 'escalate', notes[item.case_id] || '')}><AlertTriangle size={15} /> Escalate</button><button className="button primary" disabled={closed || busyId === item.case_id} onClick={() => onDecision(item, 'approve', notes[item.case_id] || '')}><Check size={15} /> Approve</button></div></div>
          </article>
        })}
        {!queue.length && <div className="empty-state"><CheckCheck size={22} />No review cases yet. Import a GeoJSON parcel dataset to begin.</div>}
      </div>
    </section>
  )
}

function AuditView({ audit }) {
  return <section className="panel audit-panel"><PanelHeading eyebrow="PROVENANCE & ACCOUNTABILITY" title="Audit history" trailing={<span className="record-count">{audit.length} events</span>} /><div className="audit-intro"><ShieldCheck size={19} /><span>Every import and human review action is recorded with actor, parcel, and decision context.</span></div><div className="audit-list">{audit.map((event) => <article className="audit-row" key={event.id}><div className="audit-symbol"><Activity size={16} /></div><div className="audit-main"><div className="audit-title-row"><strong>{event.action}</strong><time>{event.time}</time></div><p>{event.detail}</p><div className="audit-meta"><span>{event.id}</span><span>Parcel {event.parcel_id}</span><span>{event.actor}</span></div></div></article>)}{!audit.length && <div className="empty-state">No audit events recorded yet.</div>}</div></section>
}

function ParcelInspector({ parcel, setView }) {
  if (!parcel) return <aside className="panel inspector-panel empty-state"><MapPinned size={22} />Import GeoJSON to add parcels, or wait for the API to load sample records.</aside>
  const comparison = getParcelComparison(parcel)
  const assessment = parcel.assessment
  const score = assessment?.match_score
  const matchedGeometryArea = comparison?.first_geometry_area_m2 ?? assessment?.geometry_area_m2
  const firstAreaLabel = assessment?.comparison_type === 'source_boundary_comparison' ? 'Cadastral geometry footprint' : 'Imported geometry footprint'
  const secondAreaLabel = assessment?.comparison_type === 'source_boundary_comparison' ? 'Municipal geometry footprint' : `Candidate ${assessment?.candidate_matches?.[0]?.parcel_id || ''} footprint`
  return (
    <aside className="panel inspector-panel">
      <div className="inspector-heading"><div><div className="eyebrow">SELECTED PARCEL</div><h2>{parcel.id}</h2></div><StatusPill tone={parcel.status === 'Validated' || parcel.status === 'Inspection Complete' ? 'success' : parcel.status === 'Flagged' ? 'warning' : 'neutral'}>{parcel.status}</StatusPill></div>
      <div className="inspector-location"><MapPinned size={15} /> East Ridge District <span>·</span> WGS 84</div>
      <div className="confidence-block"><div><span>Geometry agreement score</span><strong>{getSpatialScoreLabel(parcel)}</strong></div>{comparison && <div className="confidence-track"><span style={{ width: `${score}%` }} /></div>}<small>Weighted spatial heuristic: overlap 55%, area agreement 25%, boundary agreement 20%. Not a legal determination.</small></div>
      <div className="inspector-section-title">SOURCE RECORD COMPARISON</div>
      <div className="comparison-row"><span><i className="legend-mark cadastral" /> Cadastral registry</span><strong>{Number(parcel.recorded_area || 0).toLocaleString('en-IN')} m²</strong></div>
      <div className="comparison-row"><span><i className="legend-mark municipal" /> Municipal GIS</span><strong>{Number(parcel.municipal_area || 0).toLocaleString('en-IN')} m²</strong></div>
      <div className="comparison-row"><span>{firstAreaLabel}</span><strong>{matchedGeometryArea !== undefined ? `${matchedGeometryArea.toLocaleString('en-IN')} m²` : 'Run analysis'}</strong></div>
      {comparison && <div className="comparison-row"><span>{secondAreaLabel}</span><strong>{comparison.second_geometry_area_m2.toLocaleString('en-IN')} m²</strong></div>}
      <div className="delta-banner"><AlertTriangle size={15} /><span>Measured geometry variance <strong>{comparison ? `${comparison.geometry_area_delta_m2.toLocaleString('en-IN')} m² (${comparison.geometry_area_delta_percent.toFixed(1)}%)` : assessment ? 'No candidate comparison' : 'Not analyzed'}</strong></span></div>
      {assessment?.reasons?.length > 0 && <div className="analysis-reasons inspector-reasons">{assessment.reasons.map((reason) => <span key={reason}>{reason}</span>)}</div>}
      <div className="inspector-section-title">RECORD PROVENANCE</div>
      <div className="provenance-row"><span>Record holder</span><strong>{parcel.owner}</strong></div>
      <div className="provenance-row"><span>Source datasets</span><strong>{parcel.source}</strong></div>
      <div className="provenance-row"><span>Current determination</span><strong>{parcel.resolution}</strong></div>
      <button className="button secondary inspector-action" onClick={() => setView('reconciliation')}>Open review case <span>→</span></button>
    </aside>
  )
}

function ParcelTable({ parcels, selectedId, onSelect }) {
  return <div className="table-scroll"><table className="parcel-table"><thead><tr><th>PARCEL</th><th>RECORD HOLDER</th><th>SOURCE SYSTEMS</th><th>SPATIAL SCORE</th><th>STATUS</th></tr></thead><tbody>{parcels.map((parcel) => <tr key={parcel.id} className={selectedId === parcel.id ? 'selected-row' : ''} onClick={() => onSelect(parcel.id)}><td><strong>{parcel.id}</strong><small>EPSG:4326</small></td><td>{parcel.owner}</td><td>{parcel.source}</td><td><span className="table-confidence">{getSpatialScoreLabel(parcel)}</span></td><td><StatusPill tone={parcel.status === 'Validated' || parcel.status === 'Inspection Complete' ? 'success' : parcel.status === 'Flagged' ? 'warning' : 'neutral'}>{parcel.status}</StatusPill></td></tr>)}</tbody></table>{!parcels.length && <div className="empty-state">No parcels match this search and filter.</div>}</div>
}

function LayerControls({ layers, setLayers }) {
  function toggle(key) { setLayers((current) => ({ ...current, [key]: !current[key] })) }
  return <div className="layer-controls"><span className="layer-label"><Layers3 size={15} /> Layers</span><label className="layer-toggle"><input type="checkbox" checked={layers.cadastral} onChange={() => toggle('cadastral')} /><span className="layer-swatch cadastral" /> Cadastral</label><label className="layer-toggle"><input type="checkbox" checked={layers.municipal} onChange={() => toggle('municipal')} /><span className="layer-swatch municipal" /> Municipal GIS</label><span className="layer-spacer" /><span className="tile-provider">OpenStreetMap</span></div>
}

function PanelHeading({ eyebrow, title, trailing }) {
  return <div className="panel-heading"><div><div className="eyebrow">{eyebrow}</div><h2>{title}</h2></div>{trailing}</div>
}

export default Dashboard