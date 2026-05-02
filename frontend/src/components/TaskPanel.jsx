import React, { useState, useEffect, useCallback } from 'react'
import { 
  CheckCircle, 
  Clock, 
  AlertCircle, 
  Loader, 
  ChevronRight,
  Bell,
  X,
  RefreshCw
} from 'lucide-react'
import { apiUrl } from '../lib/apiBase'
import { getDevAuthHeaders } from '../lib/authHeaders'
import './TaskPanel.css'

/**
 * TaskPanel - Shows real-time task progress
 * 
 * Features:
 * - List of active tasks with progress bars
 * - Substep breakdown for each task
 * - Real-time updates via polling (WebSocket can be added)
 * - Notifications
 */
export default function TaskPanel({ userId, refreshTrigger = 0, onIterate }) {
  const [tasks, setTasks] = useState([])
  const [notifications, setNotifications] = useState([])
  const [selectedTask, setSelectedTask] = useState(null)
  const [loading, setLoading] = useState(false)
  const [lastUpdate, setLastUpdate] = useState(null)
  const [iterateTextByTaskId, setIterateTextByTaskId] = useState({})

  // Fetch tasks
  const fetchTasks = useCallback(async () => {
    if (!userId) return;
    try {
      const res = await fetch(apiUrl('/api/v2/tasks'), { headers: getDevAuthHeaders() })
      if (res.ok) {
        let data = []
        try { data = await res.json() } catch (_) { /* invalid JSON */ }
        setTasks(data || [])
        setLastUpdate(new Date())
      }
    } catch (err) {
      console.error('Failed to fetch tasks:', err)
    }
  }, [userId])

  // Refresh when refreshTrigger changes (task confirmed)
  useEffect(() => {
    if (refreshTrigger > 0) {
      fetchTasks()
      fetchNotifications()
    }
  }, [refreshTrigger])

  // Fetch notifications
  const fetchNotifications = useCallback(async () => {
    if (!userId) return;
    try {
      const res = await fetch(apiUrl('/api/v2/tasks/notifications?unread_only=true'), { headers: getDevAuthHeaders() })
      if (res.ok) {
        let data = []
        try { data = await res.json() } catch (_) { /* invalid JSON */ }
        setNotifications(data || [])
      }
    } catch (err) {
      console.error('Failed to fetch notifications:', err)
    }
  }, [userId])

  // Initial load and polling
  useEffect(() => {
    fetchTasks()
    fetchNotifications()

    // Poll every 10 seconds
    const interval = setInterval(() => {
      fetchTasks()
      fetchNotifications()
    }, 10000)

    return () => clearInterval(interval)
  }, [fetchTasks, fetchNotifications])

  // Mark notification as read
  const dismissNotification = async (notificationId) => {
    try {
      await fetch(apiUrl(`/api/v2/tasks/notifications/${notificationId}/read`), {
        method: 'PUT',
        headers: getDevAuthHeaders(),
      })
      setNotifications(prev => prev.filter(n => n.id !== notificationId))
    } catch (err) {
      console.error('Failed to dismiss notification:', err)
    }
  }

  // Get status icon
  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="icon-completed" />
      case 'in_progress':
        return <Loader className="icon-progress spinning" />
      case 'waiting_input':
        return <AlertCircle className="icon-waiting" />
      case 'failed':
        return <X className="icon-failed" />
      default:
        return <Clock className="icon-pending" />
    }
  }

  // Get progress bar color
  const getProgressColor = (percent) => {
    if (percent === 100) return '#10b981' // green
    if (percent >= 50) return '#3b82f6'   // blue
    if (percent >= 25) return '#f59e0b'   // amber
    return '#6b7280'                       // gray
  }

  // Format time
  const formatTime = (isoString) => {
    if (!isoString) return ''
    const date = new Date(isoString)
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  const handleIterate = async (task) => {
    const text = (iterateTextByTaskId[task?.id] || '').trim()
    if (!text) return
    try {
      if (typeof onIterate === 'function') {
        await onIterate(task, text)
      }
    } finally {
      setIterateTextByTaskId(prev => ({ ...prev, [task.id]: '' }))
    }
  }

  return (
    <div className="task-panel">
      {/* Header */}
      <div className="task-panel-header">
        <h2>Tasks</h2>
        <div className="header-actions">
          <button 
            className="refresh-btn" 
            onClick={() => { fetchTasks(); fetchNotifications(); }}
            title="Refresh"
          >
            <RefreshCw size={16} />
          </button>
          <div className="notification-badge">
            <Bell size={16} />
            {notifications.length > 0 && (
              <span className="badge">{notifications.length}</span>
            )}
          </div>
        </div>
      </div>

      {/* Notifications */}
      {notifications.length > 0 && (
        <div className="notifications">
          {notifications.slice(0, 3).map(notif => (
            <div key={notif.id} className="notification-item">
              <div className="notif-content">
                <strong>{notif.title}</strong>
                <p>{notif.body}</p>
              </div>
              <button 
                className="notif-dismiss"
                onClick={() => dismissNotification(notif.id)}
              >
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Task List */}
      <div className="task-list">
        {tasks.length === 0 ? (
          <div className="no-tasks">
            <div className="no-tasks-icon-wrap">
              <RefreshCw size={40} className="no-tasks-icon" />
            </div>
            <h3>No Active Missions</h3>
            <p>Ready to orchestrate your next goal. Ask me to:</p>
            <div className="task-suggestions">
              <button onClick={() => onIterate(null, "Create an e-commerce website with React")}>"Build an e-commerce site"</button>
              <button onClick={() => onIterate(null, "Schedule a meeting with the team for tomorrow")}>"Schedule a team meeting"</button>
              <button onClick={() => onIterate(null, "Research the latest trends in AI agents")}>"Research AI agent trends"</button>
            </div>
          </div>
        ) : (
          tasks.map(task => (
            <div 
              key={task.id} 
              className={`task-card ${selectedTask?.id === task.id ? 'selected' : ''} ${task.status}`}
              onClick={() => setSelectedTask(selectedTask?.id === task.id ? null : task)}
            >
              {/* Task Header */}
              <div className="task-header">
                <div className="status-indicator">
                  {getStatusIcon(task.status)}
                </div>
                <div className="task-info">
                  <div className="task-title-row">
                    <h3>{task.title}</h3>
                    <div className="task-badges">
                       {task.status === 'waiting_input' && <span className="badge warning">Action Needed</span>}
                       {task.status === 'in_progress' && <span className="badge processing">Live</span>}
                    </div>
                  </div>
                  <span className="task-type">{task.task_type}{task.created_at ? ` • ${formatTime(task.created_at)}` : ''}</span>
                </div>
                <button 
                  className={`modify-btn ${selectedTask?.id === task.id ? 'active' : ''}`}
                  onClick={(e) => { e.stopPropagation(); setSelectedTask(selectedTask?.id === task.id ? null : task); }}
                >
                  {selectedTask?.id === task.id ? 'Close' : 'Modify'}
                </button>
              </div>

              {/* Progress Bar */}
              <div className="progress-section">
                <div className="progress-meta">
                   <span className="progress-label">Progress</span>
                   <span className="progress-value">{task.progress_percent}%</span>
                </div>
                <div className="progress-container">
                  <div 
                    className="progress-bar"
                    style={{ 
                      width: `${task.progress_percent}%`,
                      backgroundColor: getProgressColor(task.progress_percent)
                    }}
                  >
                    {task.status === 'in_progress' && <div className="progress-shimmer" />}
                  </div>
                </div>
              </div>


              {/* ETA */}
              {task.estimated_completion && (
                <div className="task-eta">
                  <Clock size={12} />
                  <span>ETA: {formatTime(task.estimated_completion)}</span>
                </div>
              )}

              {/* Expanded Substeps */}
              {selectedTask?.id === task.id && (
                <div className="substeps">
                  {(task.substeps || []).map((step, idx) => (
                    <div key={step.id || idx} className={`substep ${step.status}`}>
                      <div className="substep-indicator">
                        {step.status === 'completed' ? (
                          <CheckCircle size={14} className="step-completed" />
                        ) : step.status === 'in_progress' ? (
                          <Loader size={14} className="step-progress spinning" />
                        ) : step.status === 'waiting' ? (
                          <Clock size={14} className="step-waiting" />
                        ) : (
                          <div className="step-dot" />
                        )}
                      </div>
                      <div className="substep-info">
                        <span className="substep-title">{step.title}</span>
                        {step.scheduled_at && step.status === 'pending' && (
                          <span className="substep-time">
                            <Clock size={10} />
                            {formatTime(step.scheduled_at)}
                          </span>
                        )}
                        {step.error_message && (
                          <span className="substep-error">{step.error_message}</span>
                        )}
                      </div>
                      <span className="substep-weight">{step.progress_weight}%</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Iterate on this task */}
              {selectedTask?.id === task.id && (
                <div className="iterate-section" onClick={e => e.stopPropagation()}>
                  <div className="iterate-header">
                    <span>Re-iterate Mission</span>
                    <RefreshCw size={12} />
                  </div>
                  <textarea
                    value={iterateTextByTaskId[task.id] || ''}
                    onChange={(e) => setIterateTextByTaskId(prev => ({ ...prev, [task.id]: e.target.value }))}
                    rows={2}
                    placeholder="Provide updated instructions or changes..."
                    autoFocus
                  />
                  <div className="iterate-actions">
                    <button
                      className="iterate-send-btn"
                      onClick={() => handleIterate(task)}
                      disabled={!(iterateTextByTaskId[task.id] || '').trim()}
                    >
                      Update Mission
                    </button>
                  </div>
                </div>
              )}

              {/* Quick Re-run Button (visible when task is completed) */}
              {!selectedTask && task.status === 'completed' && (
                <div style={{padding: '8px 12px', display: 'flex', gap: '8px', position: 'relative', zIndex: 10}}>
                  <button
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setIterateTextByTaskId(prev => ({ ...prev, [task.id]: task.title }));
                      setSelectedTask(task);
                    }}
                    style={{
                      flex: 1,
                      padding: '8px 12px',
                      background: 'rgba(99, 102, 241, 0.15)',
                      border: '1px solid rgba(99, 102, 241, 0.3)',
                      borderRadius: '6px',
                      color: '#818cf8',
                      fontSize: '11px',
                      fontWeight: 500,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '4px',
                      transition: 'all 0.2s',
                      position: 'relative',
                      zIndex: 20
                    }}
                    onMouseEnter={(e) => {
                      e.target.style.background = 'rgba(99, 102, 241, 0.25)';
                      e.target.style.borderColor = 'rgba(99, 102, 241, 0.5)';
                    }}
                    onMouseLeave={(e) => {
                      e.target.style.background = 'rgba(99, 102, 241, 0.15)';
                      e.target.style.borderColor = 'rgba(99, 102, 241, 0.3)';
                    }}
                  >
                    <RefreshCw size={10} /> Re-run
                  </button>
                </div>
              )}


              {/* User Input Required */}
              {task.needs_user_input && (
                <div className="user-input-required">
                  <AlertCircle size={14} />
                  <span>{task.input_prompt || 'Your input is needed'}</span>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Last Update */}
      {lastUpdate && (
        <div className="last-update">
          Last updated: {lastUpdate.toLocaleTimeString()}
        </div>
      )}
    </div>
  )
}
