import React, { useState, useEffect } from 'react';
import { getDevAuthHeaders } from '../lib/authHeaders';
import './FacultyEmailDashboard.css';

/**
 * Faculty Email Dashboard
 * 
 * Displays:
 * - Executive digest (headline, top 5 priorities)
 * - Priority inbox (top 10 ranked emails)
 * - Conversation threads (grouped by topic)
 * 
 * Features:
 * - Real-time Gmail sync
 * - Color-coded urgency levels
 * - Thread collapse/expand
 * - Suggested response templates
 * - Mark as handled action
 */

export const FacultyEmailDashboard = () => {
  const [activeTab, setActiveTab] = useState('digest'); // digest, priorities, threads, followups
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [data, setData] = useState({
    digest: null,
    priority_queue: [],
    threads: [],
    synced_count: 0,
  });
  const [error, setError] = useState(null);
  const [isSetupInfo, setIsSetupInfo] = useState(false);
  const [expandedThreads, setExpandedThreads] = useState(new Set());
  const [selectedEmail, setSelectedEmail] = useState(null);
  const [responseMode, setResponseMode] = useState(null);
  const [customResponse, setCustomResponse] = useState('');
  const [followups, setFollowups] = useState([]);
  const [followupsLoading, setFollowupsLoading] = useState(false);
  const [expandedCampaign, setExpandedCampaign] = useState(null);

  // Fetch email analysis from backend
  const syncInbox = async () => {
    setSyncing(true);
    setError(null);
    setIsSetupInfo(false);
    try {
      const response = await fetch('/api/faculty/emails/sync', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getDevAuthHeaders(),
        },
      });

      let result = {};
      try { result = await response.json(); } catch (_) { result = {}; }

      if (!response.ok) {
        throw new Error(result.detail || result.error || 'Failed to sync Gmail');
      }

      // setup_required means Gmail not connected — show info not error
      if (result.setup_required) {
        setIsSetupInfo(true);
        setError(result.setup_message || 'Connect your Gmail account to enable live sync.');
        setData(result); // still set so stats panels render
      } else {
        setIsSetupInfo(false);
        setData(result);
        setActiveTab('digest');
      }
    } catch (err) {
      setError(err.message || 'Failed to sync inbox');
      console.error('Sync error:', err);
    } finally {
      setSyncing(false);
    }
  };

  // Load data on mount
  useEffect(() => {
    syncInbox();
  }, []);

  // Toggle thread expansion
  const toggleThread = (threadId) => {
    const newExpanded = new Set(expandedThreads);
    if (newExpanded.has(threadId)) {
      newExpanded.delete(threadId);
    } else {
      newExpanded.add(threadId);
    }
    setExpandedThreads(newExpanded);
  };

  // Get urgency badge color
  const getUrgencyColor = (urgency) => {
    switch (urgency?.toLowerCase()) {
      case 'critical':
        return '#dc3545';
      case 'high':
        return '#fd7e14';
      case 'medium':
        return '#ffc107';
      case 'low':
        return '#28a745';
      default:
        return '#6c757d';
    }
  };

  // Get urgency emoji
  const getUrgencyEmoji = (urgency) => {
    switch (urgency?.toLowerCase()) {
      case 'critical':
        return '🔴';
      case 'high':
        return '🟠';
      case 'medium':
        return '🟡';
      case 'low':
        return '🟢';
      default:
        return '⚪';
    }
  };

  // Send response to email
  const sendResponse = async (emailId, responseText) => {
    try {
      const response = await fetch(`/api/faculty/emails/${emailId}/send-response`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getDevAuthHeaders(),
        },
        body: JSON.stringify({
          response_text: responseText,
          mark_as_handled: true,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to send response');
      }

      setResponseMode(null);
      setCustomResponse('');
      setSelectedEmail(null);
      // Refresh data
      await syncInbox();
    } catch (err) {
      setIsSetupInfo(false);
      setError(err.message);
    }
  };

  // Load student follow-up campaigns
  const loadFollowups = async () => {
    setFollowupsLoading(true);
    try {
      const res = await fetch('/api/faculty/students/followups', {
        headers: { ...getDevAuthHeaders() },
      });
      let d = {};
      try { d = await res.json(); } catch (_) {}
      setFollowups(d.campaigns || []);
    } catch (err) {
      console.error('Failed to load followups:', err);
    } finally {
      setFollowupsLoading(false);
    }
  };

  const handleCampaignReply = async (campaignId) => {
    try {
      await fetch(`/api/faculty/students/followup/${campaignId}/reply`, {
        method: 'POST',
        headers: { ...getDevAuthHeaders() },
      });
      await loadFollowups();
    } catch (err) {
      console.error('Mark reply failed:', err);
    }
  };

  const handleCampaignClose = async (campaignId) => {
    try {
      await fetch(`/api/faculty/students/followup/${campaignId}/close`, {
        method: 'POST',
        headers: { ...getDevAuthHeaders() },
      });
      await loadFollowups();
    } catch (err) {
      console.error('Close campaign failed:', err);
    }
  };

  return (
    <div className="faculty-email-dashboard">
      {/* Header */}
      <div className="dashboard-header">
        <div>
          <h1>📧 Faculty Email Assistant</h1>
          <p>AI-powered inbox analysis with threading and priority ranking</p>
        </div>
        <button className="btn-sync" onClick={syncInbox} disabled={syncing}>
          {syncing ? '⟳ Syncing...' : (
            <>
              <span className="pulse-dot"></span> Sync Now
            </>
          )}
        </button>
      </div>

      {/* Error / Info Message */}
      {error && (
        <div
          className={isSetupInfo ? 'alert alert-info' : 'alert alert-error'}
          style={isSetupInfo ? {
            background: 'rgba(59,130,246,0.1)',
            border: '1px solid rgba(59,130,246,0.3)',
            color: '#93c5fd',
            borderRadius: '8px',
            padding: '12px 16px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '12px',
          } : {}}
        >
          {isSetupInfo ? '🔗 ' : ''}{error}
          <button onClick={() => { setError(null); setIsSetupInfo(false); }}>✕</button>
        </div>
      )}

      {/* Sync Status */}
      {data.synced_count > 0 && (
        <div className="sync-status">
          ✅ Synced {data.synced_count} email(s) • {new Date().toLocaleTimeString()}
        </div>
      )}

      {/* Tab Navigation */}
      <div className="tab-navigation">
        <button
          className={`tab-button ${activeTab === 'digest' ? 'active' : ''}`}
          onClick={() => setActiveTab('digest')}
        >
          📊 Digest
        </button>
        <button
          className={`tab-button ${activeTab === 'priorities' ? 'active' : ''}`}
          onClick={() => setActiveTab('priorities')}
        >
          🔴 Priorities ({data.priority_queue?.length || 0})
        </button>
        <button
          className={`tab-button ${activeTab === 'threads' ? 'active' : ''}`}
          onClick={() => setActiveTab('threads')}
        >
          💬 Threads ({data.threads?.length || 0})
        </button>
        <button
          className={`tab-button ${activeTab === 'followups' ? 'active' : ''}`}
          onClick={() => { setActiveTab('followups'); loadFollowups(); }}
          style={{ position: 'relative' }}
        >
          🎯 Student Follow-ups
          {followups.length > 0 && (
            <span style={{ marginLeft: '6px', background: '#ef4444', color: 'white', borderRadius: '10px', padding: '1px 7px', fontSize: '11px', fontWeight: 700 }}>
              {followups.filter(f => f.status !== 'resolved' && f.status !== 'closed').length}
            </span>
          )}
        </button>
      </div>

      {/* Content Area */}
      <div className="dashboard-content">
        {/* DIGEST TAB */}
        {activeTab === 'digest' && (
          <div className="tab-content">
            {data.digest ? (
              <div className="digest-section">
              {/* Headline */}
              <div className="digest-headline">
                <h2>{data.digest.headline}</h2>
              </div>

              {/* Top Priorities */}
              {data.digest.top_priorities && data.digest.top_priorities.length > 0 && (
                <div className="digest-priorities">
                  <h3>🔥 Top Priorities</h3>
                  <div className="priority-list">
                    {data.digest.top_priorities.slice(0, 5).map((item, idx) => (
                      <div
                        key={idx}
                        className="priority-item"
                        onClick={() => {
                          setSelectedEmail(item);
                          setActiveTab('priorities');
                        }}
                        style={{ cursor: 'pointer' }}
                      >
                        <div className="priority-rank">{idx + 1}</div>
                        <div className="priority-info">
                          <div className="priority-subject">{item.subject}</div>
                          <div className="priority-meta">
                            <span className="urgency-badge" style={{ backgroundColor: getUrgencyColor(item.urgency) }}>
                              {getUrgencyEmoji(item.urgency)} {item.urgency}
                            </span>
                            <span className="sender">{item.sender}</span>
                            <span className="score">Score: {Math.round(item.priority_score)}/100</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Threads Overview */}
              {data.digest.threads && data.digest.threads.length > 0 && (
                <div className="digest-threads">
                  <h3>💬 Conversation Threads ({data.digest.threads.length})</h3>
                  <div className="thread-overview">
                    {data.digest.threads.slice(0, 10).map((thread, idx) => (
                      <div key={idx} className="thread-card">
                        <div className="thread-header">
                          <div className="thread-subject">{thread.subject}</div>
                          <div className="thread-stats">
                            <span>{thread.email_count} emails</span>
                            <span>•</span>
                            <span>{thread.sender_count} people</span>
                            <span className="urgency-badge" style={{ backgroundColor: getUrgencyColor(thread.highest_urgency) }}>
                              {getUrgencyEmoji(thread.highest_urgency)}
                            </span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Recommendations */}
              {data.digest.recommendations && data.digest.recommendations.length > 0 && (
                <div className="digest-recommendations">
                  <h3>💡 Recommendations</h3>
                  <ul>
                    {data.digest.recommendations.map((rec, idx) => (
                      <li key={idx}>{rec}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
            ) : (
              <div className="empty-state">
                <div className="empty-state-icon">📭</div>
                <div style={{ fontWeight: 700, fontSize: '15px', color: '#94a3b8' }}>Inbox not synced yet</div>
                <div style={{ fontSize: '13px', color: '#475569', maxWidth: '380px', lineHeight: '1.6', marginTop: '6px' }}>
                  Click <strong style={{color:'#a78bfa'}}>⟳ Sync Now</strong> to fetch and analyse your Gmail inbox.<br/>
                  The AI will rank emails, group threads, and show your daily digest here.
                </div>
              </div>
            )}
          </div>
        )}

        {/* PRIORITIES TAB */}
        {activeTab === 'priorities' && (
          <div className="tab-content">
            {/* What is this tab? */}
            <div style={{
              display:'flex', alignItems:'flex-start', gap:'12px',
              background:'rgba(56,189,248,0.07)', border:'1px solid rgba(56,189,248,0.18)',
              borderRadius:'12px', padding:'14px 18px', marginBottom:'16px', fontSize:'13px',
            }}>
              <span style={{fontSize:'20px'}}>🔴</span>
              <div>
                <div style={{fontWeight:700, color:'#7dd3fc', marginBottom:'4px'}}>Priority Inbox</div>
                <div style={{color:'#94a3b8', lineHeight:'1.6'}}>
                  Your emails ranked <strong style={{color:'#f1f5f9'}}>1–10 by urgency</strong> using AI analysis.
                  Click any email to <strong style={{color:'#f1f5f9'}}>reply instantly</strong> using templates or write a custom response.
                  Deadlines, categories, and confidence scores are shown for each.
                </div>
              </div>
            </div>
            {data.priority_queue && data.priority_queue.length > 0 ? (
              <div className="priorities-list">
                {data.priority_queue.map((email, idx) => (
                  <div
                    key={idx}
                    className={`email-card ${selectedEmail?.id === email.id ? 'selected' : ''}`}
                    onClick={() => setSelectedEmail(email)}
                  >
                    <div className="email-header">
                      <div className="email-priority">
                        <div className="priority-score">{Math.round(email.priority_score)}</div>
                        <div className="priority-rank">#{idx + 1}</div>
                      </div>
                      <div className="email-subject">{email.subject}</div>
                      <div className="email-urgency">
                        <span
                          className="urgency-badge"
                          style={{ backgroundColor: getUrgencyColor(email.urgency) }}
                        >
                          {getUrgencyEmoji(email.urgency)} {email.urgency}
                        </span>
                      </div>
                    </div>

                    <div className="email-meta">
                      <span className="sender">From: {email.sender}</span>
                      <span className="category">Category: {email.category}</span>
                      {email.deadline && <span className="deadline">⏰ {email.deadline}</span>}
                      {email.attachment_hints && email.attachment_hints.length > 0 && (
                        <span className="attachment">📎 Has attachments</span>
                      )}
                      <span className="confidence">Confidence: {(email.confidence * 100).toFixed(0)}%</span>
                    </div>

                    {/* Response section (when selected) */}
                    {selectedEmail?.id === email.id && !responseMode && (
                      <div className="email-actions">
                        <button
                          className="btn-action btn-suggest"
                          onClick={(e) => {
                            e.stopPropagation();
                            setResponseMode('template');
                          }}
                        >
                          💬 Use Suggested Response
                        </button>
                        <button
                          className="btn-action btn-custom"
                          onClick={(e) => {
                            e.stopPropagation();
                            setResponseMode('custom');
                          }}
                        >
                          ✍️ Write Custom Response
                        </button>
                        <button
                          className="btn-action btn-snooze"
                          onClick={(e) => {
                            e.stopPropagation();
                            // Snooze logic would go here
                          }}
                        >
                          ⏱️ Snooze
                        </button>
                      </div>
                    )}

                    {/* Response templates section */}
                    {selectedEmail?.id === email.id && responseMode === 'template' && (
                      <div className="response-section">
                        <h4>Suggested Responses:</h4>
                        <div className="template-list">
                          <button
                            className="template-option"
                            onClick={(e) => {
                              e.stopPropagation();
                              sendResponse(email.id, `Thank you for your message regarding "${email.subject}". I have received it and will review it shortly.`);
                            }}
                          >
                            ✓ "I have received your message and will review it"
                          </button>
                          <button
                            className="template-option"
                            onClick={(e) => {
                              e.stopPropagation();
                              sendResponse(email.id, `Hi, thank you for reaching out about "${email.subject}". Please see my response below.`);
                            }}
                          >
                            ✓ "Thank you, here's my response"
                          </button>
                          <button
                            className="template-option"
                            onClick={(e) => {
                              e.stopPropagation();
                              sendResponse(email.id, `I have noted your request regarding "${email.subject}" and will get back to you soon.`);
                            }}
                          >
                            ✓ "I will get back to you soon"
                          </button>
                          <button
                            className="btn-cancel"
                            onClick={(e) => {
                              e.stopPropagation();
                              setResponseMode(null);
                            }}
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Custom response section */}
                    {selectedEmail?.id === email.id && responseMode === 'custom' && (
                      <div className="response-section">
                        <h4>Write Your Response:</h4>
                        <textarea
                          className="response-textarea"
                          placeholder="Type your response here..."
                          value={customResponse}
                          onChange={(e) => setCustomResponse(e.target.value)}
                          onClick={(e) => e.stopPropagation()}
                        />
                        <div className="response-actions">
                          <button
                            className="btn-send"
                            onClick={(e) => {
                              e.stopPropagation();
                              sendResponse(email.id, customResponse);
                            }}
                            disabled={!customResponse.trim()}
                          >
                            Send
                          </button>
                          <button
                            className="btn-cancel"
                            onClick={(e) => {
                              e.stopPropagation();
                              setResponseMode(null);
                              setCustomResponse('');
                            }}
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state">
                <div className="empty-state-icon">📬</div>
                <div style={{ fontWeight: 700, fontSize: '15px', color: '#94a3b8' }}>No priority emails yet</div>
                <div style={{ fontSize: '13px', color: '#475569', maxWidth: '340px', lineHeight: '1.6' }}>
                  Click <strong style={{color:'#a78bfa'}}>⟳ Sync Now</strong> to connect your Gmail.<br/>
                  Emails will be ranked by urgency, deadline, and topic relevance.
                </div>
              </div>
            )}
          </div>
        )}

        {/* THREADS TAB */}
        {activeTab === 'threads' && (
          <div className="tab-content">
            {/* What is this tab? */}
            <div style={{
              display:'flex', alignItems:'flex-start', gap:'12px',
              background:'rgba(99,102,241,0.07)', border:'1px solid rgba(99,102,241,0.18)',
              borderRadius:'12px', padding:'14px 18px', marginBottom:'16px', fontSize:'13px',
            }}>
              <span style={{fontSize:'20px'}}>💬</span>
              <div>
                <div style={{fontWeight:700, color:'#a5b4fc', marginBottom:'4px'}}>Conversation Threads</div>
                <div style={{color:'#94a3b8', lineHeight:'1.6'}}>
                  Emails grouped by topic across multiple senders.
                  Expand a thread to see <strong style={{color:'#f1f5f9'}}>all participants, deadlines, and categories</strong>.
                  Click <em>View Emails</em> to jump to the related priority emails and reply.
                </div>
              </div>
            </div>
            {data.threads && data.threads.length > 0 ? (
              <div className="threads-list">
                {data.threads.map((thread) => (
                  <div key={thread.thread_id} className="thread-expanded">
                    <div
                      className="thread-toggle"
                      onClick={() => toggleThread(thread.thread_id)}
                    >
                      <span className={`toggle-icon ${expandedThreads.has(thread.thread_id) ? 'open' : ''}`}>▶</span>
                      <div className="thread-title">{thread.subject}</div>
                      <div className="thread-badges">
                        <span className="badge-count">{thread.email_count} emails</span>
                        <span className="badge-people">{thread.sender_count} people</span>
                        <span
                          className="badge-urgency"
                          style={{ backgroundColor: getUrgencyColor(thread.highest_urgency) }}
                        >
                          {getUrgencyEmoji(thread.highest_urgency)} {thread.highest_urgency}
                        </span>
                      </div>
                    </div>

                    {expandedThreads.has(thread.thread_id) && (
                      <div className="thread-details">
                        <div className="senders">
                          <strong>Participants:</strong> {thread.senders?.join(', ') || 'N/A'}
                        </div>
                        <div className="emails-in-thread">
                          <strong>Emails in thread:</strong>
                          {thread.email_count} total
                          {thread.latest_deadline && (
                            <span className="deadline-in-thread">
                              ⏰ Latest deadline: {thread.latest_deadline}
                            </span>
                          )}
                        </div>
                        <div className="category-in-thread">
                          <strong>Primary category:</strong> {thread.primary_category}
                        </div>
                        <button
                          className="btn-action btn-respond-thread"
                          onClick={() => {
                            setSelectedEmail(thread);
                            setActiveTab('priorities');
                          }}
                        >
                          View Emails in Thread
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state">
                <div className="empty-state-icon">💬</div>
                <div style={{ fontWeight: 700, fontSize: '15px', color: '#94a3b8' }}>No threads found</div>
                <div style={{ fontSize: '13px', color: '#475569', maxWidth: '380px', lineHeight: '1.6' }}>
                  Threads group related emails from multiple senders together.<br/>
                  Sync your inbox to see conversation threads automatically grouped by topic.
                </div>
              </div>
            )}
          </div>
        )}
      {/* STUDENT FOLLOW-UPS TAB */}
      {activeTab === 'followups' && (
        <div className="tab-content" style={{ padding: '0 4px' }}>
          {followupsLoading ? (
            <div className="empty-state">Loading campaigns...</div>
          ) : followups.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px 20px', color: '#94a3b8' }}>
              <div style={{ fontSize: '40px', marginBottom: '12px' }}>🎯</div>
              <div style={{ fontSize: '16px', fontWeight: 600, marginBottom: '8px' }}>No Follow-up Campaigns Yet</div>
              <div style={{ fontSize: '13px' }}>Use the chat to mention a student with attendance data.<br/>e.g. <em>"Student: abc@gmail.com (ID: 1234) Attendance: 65% Days Absent: 5"</em></div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {followups.map(campaign => (
                <div key={campaign.id} style={{
                  background: 'linear-gradient(135deg, rgba(15,17,26,0.8), rgba(30,34,52,0.8))',
                  border: `1px solid ${ campaign.status === 'resolved' ? 'rgba(34,197,94,0.3)' : campaign.status === 'escalated' || campaign.status === 'parent_called' ? 'rgba(239,68,68,0.3)' : 'rgba(124,58,237,0.2)' }`,
                  borderRadius: '12px', padding: '16px', cursor: 'pointer',
                }}
                  onClick={() => setExpandedCampaign(expandedCampaign === campaign.id ? null : campaign.id)}
                >
                  {/* Campaign Header */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: '14px', color: '#f1f5f9' }}>
                        {campaign.student_name || campaign.student_email}
                      </div>
                      <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '2px' }}>
                        {campaign.student_email} {campaign.student_id ? `· ID: ${campaign.student_id}` : ''}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                      <span style={{
                        padding: '3px 10px', borderRadius: '20px', fontSize: '11px', fontWeight: 600,
                        background: campaign.status === 'resolved' ? 'rgba(34,197,94,0.15)' : campaign.status === 'escalated' || campaign.status === 'parent_called' ? 'rgba(239,68,68,0.15)' : 'rgba(124,58,237,0.15)',
                        color: campaign.status === 'resolved' ? '#4ade80' : campaign.status === 'escalated' || campaign.status === 'parent_called' ? '#f87171' : '#a78bfa',
                      }}>
                        {campaign.status.replace('_', ' ').toUpperCase()}
                      </span>
                      <span style={{ fontSize: '18px' }}>{expandedCampaign === campaign.id ? '▲' : '▼'}</span>
                    </div>
                  </div>

                  {/* Stats row */}
                  <div style={{ display: 'flex', gap: '16px', marginTop: '10px' }}>
                    <div style={{ background: 'rgba(239,68,68,0.1)', borderRadius: '8px', padding: '6px 12px', fontSize: '12px', color: '#f87171' }}>
                      📊 Attendance: {campaign.attendance_pct}%
                    </div>
                    <div style={{ background: 'rgba(245,158,11,0.1)', borderRadius: '8px', padding: '6px 12px', fontSize: '12px', color: '#fbbf24' }}>
                      📅 Absent: {campaign.days_absent} days
                    </div>
                    {campaign.erp_fetched && (
                      <div style={{ background: 'rgba(34,197,94,0.1)', borderRadius: '8px', padding: '6px 12px', fontSize: '12px', color: '#4ade80' }}>
                        🏫 ERP Synced
                      </div>
                    )}
                  </div>

                  {/* Expanded detail */}
                  {expandedCampaign === campaign.id && (
                    <div style={{ marginTop: '16px', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '16px' }}>
                      {/* Drip Schedule */}
                      <div style={{ marginBottom: '16px' }}>
                        <div style={{ fontSize: '12px', fontWeight: 700, color: '#94a3b8', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Drip Schedule</div>
                        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                          {campaign.schedule.map((step, i) => (
                            <div key={i} style={{
                              padding: '6px 12px', borderRadius: '8px', fontSize: '12px', fontWeight: 500,
                              background: step.status === 'sent' ? 'rgba(34,197,94,0.15)' : step.status === 'failed' ? 'rgba(239,68,68,0.15)' : step.status === 'skipped_reply_received' ? 'rgba(100,116,139,0.15)' : 'rgba(124,58,237,0.1)',
                              color: step.status === 'sent' ? '#4ade80' : step.status === 'failed' ? '#f87171' : step.status === 'skipped_reply_received' ? '#64748b' : '#a78bfa',
                              border: `1px solid ${ step.status === 'sent' ? 'rgba(34,197,94,0.2)' : step.status === 'failed' ? 'rgba(239,68,68,0.2)' : 'rgba(124,58,237,0.1)' }`,
                            }}>
                              {step.status === 'sent' ? '✅' : step.status === 'failed' ? '❌' : step.status === 'skipped_reply_received' ? '⏭️' : '⏳'} Step {step.step}: {step.target === 'parent' ? '👨‍👩‍👧 Parent' : '🎓 Student'} {step.type}
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Interaction Log */}
                      {campaign.interactions.length > 0 && (
                        <div style={{ marginBottom: '16px' }}>
                          <div style={{ fontSize: '12px', fontWeight: 700, color: '#94a3b8', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Interaction Log</div>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                            {campaign.interactions.map((ix, i) => (
                              <div key={i} style={{ display: 'flex', gap: '10px', alignItems: 'flex-start', fontSize: '12px' }}>
                                <span style={{ color: ix.status === 'success' ? '#4ade80' : '#f87171', minWidth: '16px' }}>{ix.status === 'success' ? '✓' : '✗'}</span>
                                <span style={{ color: '#64748b', minWidth: '60px' }}>{new Date(ix.timestamp).toLocaleTimeString()}</span>
                                <span style={{ color: '#94a3b8' }}>[{ix.type}]</span>
                                <span style={{ color: '#cbd5e1' }}>{ix.content}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Parent Info (if escalated) */}
                      {(campaign.status === 'escalated' || campaign.status === 'parent_called') && (
                        <div style={{ background: 'rgba(239,68,68,0.08)', borderRadius: '8px', padding: '12px', marginBottom: '12px' }}>
                          <div style={{ fontSize: '12px', fontWeight: 700, color: '#f87171', marginBottom: '6px' }}>🚨 Escalated to Parent</div>
                          {campaign.parent_email ? (
                            <div style={{ fontSize: '12px', color: '#94a3b8' }}>
                              Email: {campaign.parent_email}<br/>
                              {campaign.parent_phone && <>Phone: {campaign.parent_phone}<br/></>}
                              {campaign.parent_name && <>Name: {campaign.parent_name}</>}
                            </div>
                          ) : (
                            <div style={{ fontSize: '12px', color: '#64748b' }}>No parent contact info. Connect ERP to fetch automatically.</div>
                          )}
                        </div>
                      )}

                      {/* Action Buttons */}
                      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                        {campaign.status !== 'resolved' && campaign.status !== 'closed' && (
                          <button
                            onClick={async (e) => { e.stopPropagation(); await handleCampaignReply(campaign.id); }}
                            style={{ padding: '7px 14px', borderRadius: '8px', border: 'none', background: 'rgba(34,197,94,0.15)', color: '#4ade80', fontSize: '12px', fontWeight: 600, cursor: 'pointer' }}
                          >
                            ✓ Mark Replied
                          </button>
                        )}
                        {campaign.status !== 'closed' && (
                          <button
                            onClick={async (e) => { e.stopPropagation(); await handleCampaignClose(campaign.id); }}
                            style={{ padding: '7px 14px', borderRadius: '8px', border: 'none', background: 'rgba(100,116,139,0.15)', color: '#94a3b8', fontSize: '12px', fontWeight: 600, cursor: 'pointer' }}
                          >
                            ✕ Close Campaign
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      </div>
    </div>
  );
};

export default FacultyEmailDashboard;
