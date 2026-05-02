import React, { useEffect, useMemo, useState } from 'react'
import {
  Shield, BadgeCheck, FileText, LineChart, RefreshCw, Download,
  CheckCircle2, XCircle, ListChecks, ShieldAlert, Layers,
  AlertTriangle, Activity, Clock, Target, TrendingUp, Users
} from 'lucide-react'
import { apiUrl } from '../lib/apiBase'
import { getDevAuthHeaders } from '../lib/authHeaders'
import './GovernanceHub.css'

const tabs = [
  { id: 'approvals', label: 'Approvals', icon: BadgeCheck },
  { id: 'evidence', label: 'Evidence',  icon: FileText   },
  { id: 'trust',    label: 'Trust',     icon: LineChart   },
  { id: 'policies', label: 'Policies',  icon: ShieldAlert },
  { id: 'packs',    label: 'Workflow Packs', icon: Layers },
]

const RISK_COLOR = { low: '#22c55e', medium: '#f59e0b', high: '#ef4444', critical: '#dc2626' }

function Badge({ label, color = '#6366f1' }) {
  return (
    <span style={{
      padding: '2px 10px', borderRadius: '20px', fontSize: '11px', fontWeight: 700,
      background: `${color}22`, color, border: `1px solid ${color}44`,
    }}>{label}</span>
  )
}

function StatCard({ icon: Icon, value, label, color = '#a78bfa' }) {
  return (
    <div style={{
      background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)',
      borderRadius: '12px', padding: '16px 20px', display: 'flex', flexDirection: 'column',
      gap: '6px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color }}>
        <Icon size={16} /> <span style={{ fontSize: '12px', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{label}</span>
      </div>
      <div style={{ fontSize: '28px', fontWeight: 800, color: '#f1f5f9' }}>{value}</div>
    </div>
  )
}

function ProgressBar({ value, color = '#a78bfa' }) {
  const pct = Math.max(0, Math.min(100, Number(value) || 0))
  return (
    <div style={{ background: 'rgba(255,255,255,0.08)', borderRadius: '99px', height: '8px', overflow: 'hidden', flex: 1 }}>
      <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: '99px', transition: 'width 0.6s ease' }} />
    </div>
  )
}

export default function GovernanceHub({ onClose }) {
  const [activeTab, setActiveTab]           = useState('approvals')
  const [loading, setLoading]               = useState(false)
  const [missions, setMissions]             = useState([])
  const [selectedMissionId, setSelectedMissionId] = useState(null)
  const [approvals, setApprovals]           = useState([])
  const [artifacts, setArtifacts]           = useState([])
  const [trust, setTrust]                   = useState(null)
  const [rules, setRules]                   = useState([])
  const [packs, setPacks]                   = useState([])
  const [toast, setToast]                   = useState(null)  // { msg, type }
  const [deciding, setDeciding]             = useState(null)  // step_id being decided
  const [bundleLoading, setBundleLoading]   = useState(false)

  const headers = useMemo(() => getDevAuthHeaders(), [])

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 4000)
  }

  // ─── Load all data ──────────────────────────────────────────────────────────
  const loadAll = async () => {
    setLoading(true)
    try {
      const [missionsRes, approvalsRes, trustRes, rulesRes, packsRes] = await Promise.all([
        fetch(apiUrl('/api/governance/missions'),       { headers }),
        fetch(apiUrl('/api/governance/approvals'),      { headers }),
        fetch(apiUrl('/api/governance/trust'),          { headers }),
        fetch(apiUrl('/api/policies'),                  { headers }),
        fetch(apiUrl('/api/governance/workflow-packs'), { headers }),
      ])

      const safe = async (res) => { try { return res.ok ? await res.json() : null } catch { return null } }

      const [mD, aD, tD, rD, pD] = await Promise.all([safe(missionsRes), safe(approvalsRes), safe(trustRes), safe(rulesRes), safe(packsRes)])

      const missionList = mD?.missions || []
      setMissions(missionList)
      setApprovals(aD?.approvals || [])
      setTrust(tD || null)
      setRules(rD?.rules || [])
      setPacks(pD?.packs || [])

      if (!selectedMissionId && missionList.length > 0) {
        setSelectedMissionId(missionList[0].mission_id)
      }
    } finally {
      setLoading(false)
    }
  }

  const loadArtifacts = async (missionId) => {
    if (!missionId) return
    // Correct URL: /api/evidence/missions/{id}/artifacts
    const res = await fetch(apiUrl(`/api/evidence/missions/${missionId}/artifacts`), { headers })
    const data = res.ok ? await res.json().catch(() => ({})) : {}
    setArtifacts(data.artifacts || [])
  }

  useEffect(() => { loadAll() }, [])
  useEffect(() => { if (selectedMissionId) loadArtifacts(selectedMissionId) }, [selectedMissionId])

  const selectedMission = missions.find(m => m.mission_id === selectedMissionId) || missions[0] || null

  // ─── Approve / Reject ───────────────────────────────────────────────────────
  const decide = async (missionId, stepId, decision) => {
    const label = decision === 'approve' ? 'Approve' : 'Reject'
    const defaultReason = decision === 'approve' ? 'Policy satisfied and reviewed.' : 'Does not meet policy requirements.'
    const reason = window.prompt(
      `${label} — enter reason (min 10 characters):`,
      defaultReason
    )
    if (reason === null) return // cancelled
    if (!reason.trim() || reason.trim().length < 10) {
      showToast('❌ Reason must be at least 10 characters.', 'error')
      return
    }

    setDeciding(stepId)
    try {
      const res = await fetch(apiUrl(`/api/governance/missions/${missionId}/approval`), {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ step_id: stepId, decision, reason: reason.trim() }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        showToast(`❌ ${data.detail || data.error || 'Failed to record decision'}`, 'error')
      } else {
        showToast(`✅ Step ${decision}d successfully!`, 'success')
        await loadAll()
        if (selectedMissionId) await loadArtifacts(selectedMissionId)
      }
    } catch (e) {
      showToast(`❌ Network error: ${e.message}`, 'error')
    } finally {
      setDeciding(null)
    }
  }

  // ─── Export Bundle ──────────────────────────────────────────────────────────
  const exportBundle = async (missionId) => {
    setBundleLoading(true)
    try {
      // Correct URL: /api/governance/missions/{id}/bundle (NOT /api/evidence/)
      const res = await fetch(apiUrl(`/api/governance/missions/${missionId}/bundle`), { headers })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        showToast(`❌ Export failed: ${err.detail || res.status}`, 'error')
        return
      }
      const contentType = res.headers.get('Content-Type') || ''
      if (contentType.includes('application/zip')) {
        // ZIP download
        const blob = await res.blob()
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `evidence_${missionId.slice(0, 8)}.zip`
        a.click()
        URL.revokeObjectURL(url)
        showToast('✅ Bundle downloaded!', 'success')
      } else {
        // JSON bundle — pretty print and offer download
        const data = await res.json()
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `mission_bundle_${missionId.slice(0, 8)}.json`
        a.click()
        URL.revokeObjectURL(url)
        showToast('✅ Bundle exported as JSON!', 'success')
      }
    } catch (e) {
      showToast(`❌ Export error: ${e.message}`, 'error')
    } finally {
      setBundleLoading(false)
    }
  }

  // ─── Render: Approvals ──────────────────────────────────────────────────────
  const renderApprovals = () => (
    <div className="gov-list">
      {approvals.length === 0 ? (
        <div className="gov-empty">
          <CheckCircle2 size={32} color="#22c55e" />
          <div style={{ marginTop: '8px', fontWeight: 600 }}>No approvals waiting</div>
          <div style={{ color: '#64748b', fontSize: '13px' }}>All clear. Actions are running within policy.</div>
        </div>
      ) : approvals.map(item => (
        <div key={`${item.mission_id}-${item.step_id}`} className="gov-card">
          <div className="gov-card-head">
            <strong>{item.mission_title}</strong>
            <Badge label={item.risk_level || 'medium'} color={RISK_COLOR[item.risk_level] || '#f59e0b'} />
          </div>
          <div style={{ fontSize: '14px', color: '#cbd5e1', margin: '6px 0' }}>{item.step_title}</div>
          <div className="gov-meta">Approvers: {(item.approver_roles || []).join(', ') || 'admin, manager'}</div>
          <div className="gov-actions" style={{ marginTop: '12px' }}>
            <button
              className="gov-btn gov-approve"
              disabled={deciding === item.step_id}
              onClick={() => decide(item.mission_id, item.step_id, 'approve')}
            >
              <CheckCircle2 size={14} /> {deciding === item.step_id ? 'Processing…' : 'Approve'}
            </button>
            <button
              className="gov-btn gov-reject"
              disabled={deciding === item.step_id}
              onClick={() => decide(item.mission_id, item.step_id, 'reject')}
            >
              <XCircle size={14} /> Reject
            </button>
          </div>
        </div>
      ))}
    </div>
  )

  // ─── Render: Evidence ───────────────────────────────────────────────────────
  const renderEvidence = () => (
    <div className="gov-layout">
      <div className="gov-sidebar">
        {missions.length === 0 ? (
          <div className="gov-empty" style={{ padding: '20px 12px', fontSize: '13px' }}>No missions yet. Create one from Workflow Packs.</div>
        ) : missions.map(mission => (
          <button
            key={mission.mission_id}
            className={`gov-mission ${selectedMissionId === mission.mission_id ? 'active' : ''}`}
            onClick={() => setSelectedMissionId(mission.mission_id)}
          >
            <span>{mission.title}</span>
            <small>{mission.state}</small>
          </button>
        ))}
      </div>
      <div className="gov-main">
        {selectedMission ? (
          <>
            <div className="gov-card" style={{ marginBottom: '12px' }}>
              <div className="gov-card-head">
                <div>
                  <strong>{selectedMission.title}</strong>
                  <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '4px' }}>{selectedMission.description}</div>
                </div>
                <button
                  className="gov-btn"
                  style={{ opacity: bundleLoading ? 0.6 : 1 }}
                  disabled={bundleLoading}
                  onClick={() => exportBundle(selectedMission.mission_id)}
                >
                  <Download size={14} />
                  {bundleLoading ? ' Exporting…' : ' Export Bundle'}
                </button>
              </div>
              {/* Step compliance bar */}
              {selectedMission.steps?.length > 0 && (
                <div style={{ marginTop: '12px' }}>
                  <div style={{ fontSize: '12px', color: '#64748b', marginBottom: '6px' }}>Step compliance</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {selectedMission.steps.map(step => (
                      <div key={step.id} style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <span style={{ fontSize: '12px', color: '#94a3b8', minWidth: '140px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{step.title}</span>
                        <Badge
                          label={step.state || 'pending'}
                          color={
                            step.state === 'approved' ? '#22c55e' :
                            step.state === 'rejected' ? '#ef4444' :
                            step.state === 'running'  ? '#3b82f6' : '#6366f1'
                          }
                        />
                        {step.requires_approval && !step.approval_decision_id && (
                          <Badge label="⏳ Awaiting approval" color="#f59e0b" />
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="gov-list">
              {artifacts.length === 0 ? (
                <div className="gov-empty">
                  <FileText size={28} color="#475569" />
                  <div style={{ marginTop: '8px', color: '#64748b' }}>No evidence artifacts yet</div>
                  <div style={{ fontSize: '12px', color: '#475569', marginTop: '4px' }}>Evidence is captured automatically when the AI executes steps</div>
                </div>
              ) : artifacts.map(artifact => (
                <div key={artifact.artifact_id} className="gov-card">
                  <div className="gov-card-head">
                    <strong>{artifact.name}</strong>
                    <Badge label={artifact.classification} />
                  </div>
                  <div className="gov-meta">Hash: {(artifact.content_hash || '').slice(0, 16)}…</div>
                  <div className="gov-meta">Step: {artifact.step_id || 'mission'} | {artifact.file_path}</div>
                </div>
              ))}
            </div>
          </>
        ) : (
          <div className="gov-empty">Select a mission from the left panel</div>
        )}
      </div>
    </div>
  )

  // ─── Render: Trust ─────────────────────────────────────────────────────────
  const renderTrust = () => {
    const tc   = Number(trust?.trace_completeness ?? 0)
    const pc   = Number(trust?.policy_compliance  ?? 0)
    const backlog = trust?.approval_backlog ?? 0
    const mCount  = trust?.mission_count   ?? missions.length
    const states  = trust?.mission_states  ?? {}
    const telemetry = trust?.telemetry     ?? {}

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', padding: '4px' }}>
        {/* Top stat cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: '12px' }}>
          <StatCard icon={Shield}     value={`${tc.toFixed(1)}%`}  label="Trace Completeness" color="#a78bfa" />
          <StatCard icon={BadgeCheck} value={`${pc.toFixed(1)}%`}  label="Policy Compliance"  color="#22c55e" />
          <StatCard icon={Clock}      value={backlog}               label="Approval Backlog"    color="#f59e0b" />
          <StatCard icon={Target}     value={mCount}               label="Total Missions"       color="#38bdf8" />
        </div>

        {/* Progress bars */}
        <div className="gov-card">
          <div className="gov-card-head" style={{ marginBottom: '14px' }}><strong>Health Overview</strong></div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {[
              { label: 'Trace Completeness', value: tc, color: '#a78bfa' },
              { label: 'Policy Compliance',  value: pc, color: '#22c55e' },
              { label: 'Approval Flow',      value: backlog === 0 ? 100 : Math.max(0, 100 - backlog * 10), color: '#f59e0b' },
            ].map(row => (
              <div key={row.label} style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span style={{ fontSize: '13px', color: '#94a3b8', minWidth: '160px' }}>{row.label}</span>
                <ProgressBar value={row.value} color={row.color} />
                <span style={{ fontSize: '13px', fontWeight: 700, color: row.color, minWidth: '42px', textAlign: 'right' }}>{row.value.toFixed(0)}%</span>
              </div>
            ))}
          </div>
        </div>

        {/* Mission state breakdown */}
        {Object.keys(states).length > 0 && (
          <div className="gov-card">
            <div className="gov-card-head" style={{ marginBottom: '10px' }}><strong>Mission States</strong></div>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              {Object.entries(states).map(([state, count]) => (
                <div key={state} style={{
                  background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
                  borderRadius: '10px', padding: '8px 14px', textAlign: 'center',
                }}>
                  <div style={{ fontSize: '20px', fontWeight: 800, color: '#f1f5f9' }}>{count}</div>
                  <div style={{ fontSize: '11px', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{state}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Telemetry */}
        {Object.keys(telemetry).length > 0 && (
          <div className="gov-card">
            <div className="gov-card-head" style={{ marginBottom: '10px' }}><strong>Activity Telemetry</strong></div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: '8px' }}>
              {Object.entries(telemetry).slice(0, 8).map(([key, val]) => (
                <div key={key} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                  <span style={{ color: '#94a3b8' }}>{key.replace(/_/g, ' ')}</span>
                  <span style={{ color: '#f1f5f9', fontWeight: 600 }}>{typeof val === 'number' ? val : String(val)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {!trust && (
          <div className="gov-empty">
            <Activity size={32} color="#475569" />
            <div style={{ marginTop: '8px', color: '#64748b' }}>No trust data yet</div>
            <div style={{ fontSize: '12px', color: '#475569', marginTop: '4px' }}>Trust metrics appear after missions are created and executed</div>
          </div>
        )}
      </div>
    )
  }

  // ─── Render: Policies ──────────────────────────────────────────────────────
  const renderPolicies = () => (
    <div className="gov-list">
      {rules.length === 0 ? (
        <div className="gov-empty">
          <ShieldAlert size={32} color="#475569" />
          <div style={{ marginTop: '8px', color: '#64748b' }}>No policy rules configured</div>
          <div style={{ fontSize: '12px', color: '#475569', marginTop: '4px' }}>Policies control what the AI can do without approval</div>
        </div>
      ) : rules.map(rule => (
        <div key={rule.rule_id} className="gov-card">
          <div className="gov-card-head">
            <strong>{rule.name}</strong>
            <Badge label={rule.active ? 'Active' : 'Disabled'} color={rule.active ? '#22c55e' : '#64748b'} />
          </div>
          <div className="gov-meta">Risk: {rule.risk_level} | Min approvals: {rule.min_approvals}</div>
          <div className="gov-muted">Keywords: {(rule.keywords || []).join(', ') || 'none'}</div>
        </div>
      ))}
    </div>
  )

  // ─── Render: Workflow Packs ────────────────────────────────────────────────
  const createMissionFromPack = async (packId) => {
    const res = await fetch(apiUrl('/api/governance/missions/from-pack'), {
      method: 'POST',
      headers: { ...headers, 'Content-Type': 'application/json' },
      body: JSON.stringify({ pack_id: packId }),
    })
    if (res.ok) {
      showToast('✅ Mission created! Check Evidence tab.', 'success')
      await loadAll()
      setActiveTab('evidence')
    } else {
      const e = await res.json().catch(() => ({}))
      showToast(`❌ ${e.detail || 'Failed to create mission'}`, 'error')
    }
  }

  const renderPacks = () => (
    <div className="gov-list">
      {packs.length === 0 ? (
        <div className="gov-empty">
          <Layers size={32} color="#475569" />
          <div style={{ marginTop: '8px', color: '#64748b' }}>No workflow packs found</div>
        </div>
      ) : packs.map(pack => (
        <div key={pack.id} className="gov-card">
          <div className="gov-card-head">
            <strong>{pack.name}</strong>
            <Badge label={`${pack.step_count} steps`} color="#38bdf8" />
          </div>
          <div className="gov-muted" style={{ margin: '6px 0' }}>{pack.description}</div>
          <div className="gov-meta">Tags: {(pack.tags || []).join(', ') || 'none'}</div>
          <div className="gov-actions" style={{ marginTop: '10px' }}>
            <button className="gov-btn gov-approve" onClick={() => createMissionFromPack(pack.id)}>
              <Layers size={14} /> Launch Mission
            </button>
          </div>
        </div>
      ))}
    </div>
  )

  // ─── Main render ───────────────────────────────────────────────────────────
  return (
    <div className="gov-hub">
      {/* Toast notification */}
      {toast && (
        <div style={{
          position: 'absolute', top: '12px', left: '50%', transform: 'translateX(-50%)',
          background: toast.type === 'error' ? 'rgba(239,68,68,0.15)' : 'rgba(34,197,94,0.15)',
          border: `1px solid ${toast.type === 'error' ? 'rgba(239,68,68,0.4)' : 'rgba(34,197,94,0.4)'}`,
          color: toast.type === 'error' ? '#f87171' : '#4ade80',
          padding: '8px 20px', borderRadius: '10px', fontSize: '13px', fontWeight: 600,
          zIndex: 999, whiteSpace: 'nowrap', backdropFilter: 'blur(8px)',
        }}>
          {toast.msg}
        </div>
      )}

      <div className="gov-topbar">
        <div>
          <div className="gov-title">Governance Hub</div>
          <div className="gov-subtitle">Approvals, evidence, trust metrics, and policy rules.</div>
        </div>
        <button className="gov-refresh" onClick={loadAll} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'spin' : ''} />
          {loading ? ' Loading…' : ' Refresh'}
        </button>
      </div>

      <div className="gov-tabs">
        {tabs.map(tab => {
          const Icon = tab.icon
          const badge = tab.id === 'approvals' && approvals.length > 0 ? approvals.length : null
          return (
            <button key={tab.id} className={`gov-tab ${activeTab === tab.id ? 'active' : ''}`} onClick={() => setActiveTab(tab.id)}>
              <Icon size={14} /> {tab.label}
              {badge && (
                <span style={{ marginLeft: '6px', background: '#ef4444', color: 'white', borderRadius: '10px', padding: '1px 6px', fontSize: '10px', fontWeight: 700 }}>
                  {badge}
                </span>
              )}
            </button>
          )
        })}
      </div>

      <div className="gov-body">
        {activeTab === 'approvals' && renderApprovals()}
        {activeTab === 'evidence' && renderEvidence()}
        {activeTab === 'trust'    && renderTrust()}
        {activeTab === 'policies' && renderPolicies()}
        {activeTab === 'packs'    && renderPacks()}
      </div>

      <div className="gov-footer">
        {selectedMission ? `Selected mission: ${selectedMission.title}` : 'No mission selected'}
        {onClose && <button className="gov-close" onClick={onClose}>Close</button>}
      </div>
    </div>
  )
}