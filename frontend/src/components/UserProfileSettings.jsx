import React, { useState, useEffect } from 'react'
import { User, Settings, Save, Loader, AlertCircle, CheckCircle, Trash2, Plus, Brain } from 'lucide-react'
import { apiUrl } from '../lib/apiBase'
import { getDevAuthHeaders } from '../lib/authHeaders'
import './AISettings.css'

export default function UserProfileSettings({ userId }) {
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)

  const [name, setName] = useState('')
  const [preferences, setPreferences] = useState({})
  const [memories, setMemories] = useState([])
  
  const [newPrefKey, setNewPrefKey] = useState('')
  const [newPrefValue, setNewPrefValue] = useState('')

  useEffect(() => {
    loadProfile()
  }, [userId])

  const loadProfile = async () => {
    setLoading(true)
    try {
      const res = await fetch(apiUrl(`/api/users/profile/${userId}`), {
        headers: getDevAuthHeaders()
      })
      if (!res.ok) throw new Error('Failed to load profile')
      let data = {}
      try { data = await res.json() } catch (_) { throw new Error('Invalid server response') }
      setName(data.name || '')
      setPreferences(data.preferences || {})
      setMemories(data.memories || [])
    } catch (err) {
      console.error(err)
      setError('Failed to load user profile.')
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      const res = await fetch(apiUrl(`/api/users/profile/${userId}`), {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...getDevAuthHeaders()
        },
        body: JSON.stringify({ name, preferences })
      })
      if (!res.ok) throw new Error('Failed to save profile')
      setSuccess('Profile saved successfully! The AI will now use these details.')
      setTimeout(() => setSuccess(null), 3000)
    } catch (err) {
      console.error(err)
      setError('Failed to save profile.')
    } finally {
      setSaving(false)
    }
  }

  const handleAddPreference = () => {
    if (!newPrefKey || !newPrefValue) return
    setPreferences(prev => ({ ...prev, [newPrefKey]: newPrefValue }))
    setNewPrefKey('')
    setNewPrefValue('')
  }

  const handleRemovePreference = (key) => {
    const newPrefs = { ...preferences }
    delete newPrefs[key]
    setPreferences(newPrefs)
  }

  if (loading) {
    return (
      <div className="settings-loading" style={{ padding: '40px' }}>
        <Loader className="spin" size={32} />
        <span>Loading profile...</span>
      </div>
    )
  }

  return (
    <div className="tab-content" style={{ padding: '24px' }}>
      <div className="section-intro">
        <User size={20} />
        <p>Personalize your AI experience. The AI will securely remember your name, custom preferences, and facts to provide a tailored context in every conversation.</p>
      </div>

      {error && (
        <div className="alert error">
          <AlertCircle size={16} />
          {error}
        </div>
      )}

      {success && (
        <div className="alert success">
          <CheckCircle size={16} />
          {success}
        </div>
      )}

      <div className="form-group">
        <label>Your Name</label>
        <div className="input-with-icon">
          <User size={16} />
          <input
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="How should the AI call you?"
          />
        </div>
        <small>The AI will use this name when addressing you.</small>
      </div>

      <div className="quick-signup" style={{ marginBottom: '24px' }}>
        <h4 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Settings size={18} style={{ color: 'var(--tw-accent-primary)' }} />
          AI Preferences
        </h4>
        <p>Define global rules or formatting preferences for how the AI should respond.</p>

        <div className="services-list" style={{ marginBottom: '16px' }}>
          {Object.entries(preferences).map(([k, v]) => (
            <div key={k} className="service-item" style={{ padding: '12px 16px' }}>
              <div className="service-info">
                <strong style={{ fontSize: '0.9rem', marginBottom: '2px' }}>{k}</strong>
                <span className="service-email">{v}</span>
              </div>
              <button 
                onClick={() => handleRemovePreference(k)}
                style={{ background: 'none', border: 'none', color: 'var(--tw-text-muted)', cursor: 'pointer' }}
                title="Remove"
              >
                <Trash2 size={16} />
              </button>
            </div>
          ))}
          {Object.keys(preferences).length === 0 && (
            <div className="empty-state" style={{ padding: '16px' }}>
              <p style={{ margin: 0 }}>No custom preferences set.</p>
            </div>
          )}
        </div>

        <div style={{ display: 'flex', gap: '8px' }}>
          <input
            type="text"
            value={newPrefKey}
            onChange={e => setNewPrefKey(e.target.value)}
            placeholder="Key (e.g. tone)"
            style={{ flex: 1, padding: '10px 14px', background: 'rgba(0,0,0,0.2)', border: '1px solid var(--tw-border)', borderRadius: '12px', color: 'var(--tw-text-primary)' }}
          />
          <input
            type="text"
            value={newPrefValue}
            onChange={e => setNewPrefValue(e.target.value)}
            placeholder="Value (e.g. formal)"
            style={{ flex: 2, padding: '10px 14px', background: 'rgba(0,0,0,0.2)', border: '1px solid var(--tw-border)', borderRadius: '12px', color: 'var(--tw-text-primary)' }}
          />
          <button 
            onClick={handleAddPreference}
            disabled={!newPrefKey || !newPrefValue}
            className="signup-btn"
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 16px' }}
          >
            <Plus size={16} />
          </button>
        </div>
      </div>

      {memories.length > 0 && (
        <div className="quick-signup" style={{ marginBottom: '24px' }}>
          <h4 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Brain size={18} style={{ color: 'var(--tw-success)' }} />
            Remembered Facts
          </h4>
          <p>These are facts the AI has autonomously learned about you through conversation.</p>
          
          <div className="services-list" style={{ marginBottom: 0 }}>
            {memories.map(m => (
              <div key={m.id || m.key} className="service-item" style={{ padding: '12px 16px' }}>
                <div className="service-info">
                  <strong style={{ fontSize: '0.9rem', marginBottom: '2px' }}>{m.key}</strong>
                  <span className="service-email">{m.value}</span>
                </div>
                <div className="service-status">
                  <span className="badge success" style={{ fontSize: '0.7rem', padding: '4px 8px' }}>
                    <CheckCircle size={10} /> Learned
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <button 
        className="save-btn"
        onClick={handleSave}
        disabled={saving}
      >
        {saving ? (
          <>
            <Loader className="spin" size={16} />
            Saving Profile...
          </>
        ) : (
          <>
            <Save size={16} />
            Save Profile Configuration
          </>
        )}
      </button>
    </div>
  )
}
