import React, { useState, useEffect } from 'react';
import './PipelineBuilder.css';

const STEP_TYPES = [
  { id: 'send_email', label: 'Send Email', icon: '📧', color: '#4CAF50' },
  { id: 'wait', label: 'Wait/Delay', icon: '⏱️', color: '#FF9800' },
  { id: 'check_condition', label: 'Check Condition', icon: '❓', color: '#2196F3' },
  { id: 'query_erp', label: 'Query ERP', icon: '🔍', color: '#9C27B0' },
  { id: 'escalate', label: 'Escalate', icon: '⬆️', color: '#F44336' },
  { id: 'log_action', label: 'Log Action', icon: '📝', color: '#607D8B' },
];

const SCENARIO_TEMPLATES = [
  { id: 'attendance', name: 'Student Attendance Follow-up', description: 'Track attendance and escalate to parents' },
  { id: 'assignment', name: 'Assignment Deadline Reminders', description: 'Remind students and track submissions' },
  { id: 'fee', name: 'Fee Payment Collection', description: 'Send reminders and escalate unpaid fees' },
  { id: 'exam', name: 'Exam Preparation Tracking', description: 'Provide study materials and mock tests' },
  { id: 'conduct', name: 'Conduct Issue Management', description: 'Handle behavior problems with escalation' },
  { id: 'scholarship', name: 'Scholarship Eligibility', description: 'Remind eligible students about applications' },
];

const PipelineBuilder = ({ onClose, onSave, existingPipeline = null }) => {
  const [mode, setMode] = useState('template'); // 'template' | 'builder' | 'monitor'
  const [pipelineData, setPipelineData] = useState({
    name: existingPipeline?.name || '',
    description: existingPipeline?.description || '',
    scenario_type: existingPipeline?.scenario_type || '',
    steps: existingPipeline?.steps || [],
  });

  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [selectedStep, setSelectedStep] = useState(null);
  const [activeInstances, setActiveInstances] = useState([]);
  const [loading, setLoading] = useState(false);

  // Load template
  const handleLoadTemplate = async (templateId) => {
    setLoading(true);
    try {
      const response = await fetch(
        `/api/workflows/from-scenario?scenario_type=${templateId}&name=Custom ${templateId}&created_by=current_user`,
        { method: 'POST' }
      );
      let data = {};
      try { data = await response.json(); } catch (_) { /* invalid JSON */ }
      setSelectedTemplate(templateId);
      setPipelineData({
        name: data.name || `${templateId} Pipeline`,
        description: '',
        scenario_type: templateId,
        steps: [],
      });
      setMode('builder');
    } catch (error) {
      console.error('Error loading template:', error);
      alert('Failed to load template');
    } finally {
      setLoading(false);
    }
  };

  // Save pipeline
  const handleSavePipeline = async () => {
    if (!pipelineData.name || !pipelineData.scenario_type) {
      alert('Please enter a pipeline name and select a scenario type');
      return;
    }

    setLoading(true);
    try {
      const response = await fetch('/api/workflows/from-scenario', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenario_type: pipelineData.scenario_type,
          name: pipelineData.name,
          description: pipelineData.description,
          created_by: 'current_user',
        }),
      });
      let data = {};
      try { data = await response.json(); } catch (_) { /* invalid JSON */ }
      alert(`Pipeline saved! ID: ${data.workflow_id}`);
      if (onSave) onSave(data);
    } catch (error) {
      console.error('Error saving pipeline:', error);
      alert('Failed to save pipeline');
    } finally {
      setLoading(false);
    }
  };

  // Execute pipeline
  const handleExecutePipeline = async (workflowId) => {
    setLoading(true);
    try {
      const response = await fetch(`/api/workflows/${workflowId}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workflow_definition_id: workflowId,
          subject_email: 'abc@gmail.com',
          subject_id: '1234554321',
          metadata: { course: 'Math 101' },
        }),
      });
      let data = {};
      try { data = await response.json(); } catch (_) { /* invalid JSON */ }
      alert(`Pipeline executed! Instance ID: ${data.instance_id}`);
      setActiveInstances([...activeInstances, data]);
    } catch (error) {
      console.error('Error executing pipeline:', error);
      alert('Failed to execute pipeline');
    } finally {
      setLoading(false);
    }
  };

  // Template Selection View
  if (mode === 'template') {
    return (
      <div className="pipeline-builder">
        <div className="pipeline-header">
          <h2>📊 Pipeline Builder - Select Template</h2>
          <button className="close-btn" onClick={onClose}>✕</button>
        </div>

        <div className="template-grid">
          {SCENARIO_TEMPLATES.map((template) => (
            <div key={template.id} className="template-card">
              <h3>{template.name}</h3>
              <p>{template.description}</p>
              <button 
                className="load-btn"
                onClick={() => handleLoadTemplate(template.id)}
                disabled={loading}
              >
                {loading && selectedTemplate === template.id ? 'Loading...' : 'Use Template'}
              </button>
            </div>
          ))}
        </div>

        <div className="builder-actions">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
        </div>
      </div>
    );
  }

  // Builder View
  if (mode === 'builder') {
    return (
      <div className="pipeline-builder">
        <div className="pipeline-header">
          <h2>🔧 Pipeline Builder - {pipelineData.name}</h2>
          <button className="close-btn" onClick={onClose}>✕</button>
        </div>

        <div className="builder-container">
          {/* Left Panel - Step Library */}
          <div className="step-library">
            <h3>Available Steps</h3>
            <div className="step-list">
              {STEP_TYPES.map((step) => (
                <div
                  key={step.id}
                  className="step-item"
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.effectAllowed = 'copy';
                    e.dataTransfer.setData('stepType', JSON.stringify(step));
                  }}
                  style={{ borderLeft: `4px solid ${step.color}` }}
                >
                  <span className="step-icon">{step.icon}</span>
                  <span className="step-label">{step.label}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Middle Panel - Canvas */}
          <div className="canvas">
            <h3>Pipeline Flow</h3>
            <div
              className="drop-zone"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                const stepType = JSON.parse(e.dataTransfer.getData('stepType'));
                setPipelineData({
                  ...pipelineData,
                  steps: [
                    ...pipelineData.steps,
                    {
                      id: `step_${Date.now()}`,
                      name: `${stepType.label} ${pipelineData.steps.length + 1}`,
                      step_type: stepType.id,
                      order: pipelineData.steps.length,
                      config: {},
                    },
                  ],
                });
              }}
            >
              {pipelineData.steps.length === 0 ? (
                <div className="empty-state">
                  <p>📌 Drag steps here to build your pipeline</p>
                </div>
              ) : (
                <div className="steps-preview">
                  {pipelineData.steps.map((step, index) => {
                    const stepDef = STEP_TYPES.find((s) => s.id === step.step_type);
                    return (
                      <div key={step.id}>
                        <div
                          className="step-preview"
                          style={{ borderColor: stepDef?.color || '#999' }}
                          onClick={() => setSelectedStep(step)}
                        >
                          <span className="step-number">{index + 1}</span>
                          <span>{stepDef?.icon}</span>
                          <span className="step-name">{step.name}</span>
                          <button
                            className="delete-step"
                            onClick={() => {
                              setPipelineData({
                                ...pipelineData,
                                steps: pipelineData.steps.filter((s) => s.id !== step.id),
                              });
                            }}
                          >
                            🗑️
                          </button>
                        </div>
                        {index < pipelineData.steps.length - 1 && (
                          <div className="arrow">⬇️</div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Right Panel - Configuration */}
          <div className="config-panel">
            <h3>Configuration</h3>
            {selectedStep ? (
              <div className="step-config">
                <div className="form-group">
                  <label>Step Name</label>
                  <input
                    type="text"
                    value={selectedStep.name}
                    onChange={(e) => {
                      const updated = { ...selectedStep, name: e.target.value };
                      setPipelineData({
                        ...pipelineData,
                        steps: pipelineData.steps.map((s) =>
                          s.id === selectedStep.id ? updated : s
                        ),
                      });
                      setSelectedStep(updated);
                    }}
                  />
                </div>

                {selectedStep.step_type === 'send_email' && (
                  <>
                    <div className="form-group">
                      <label>Recipient Type</label>
                      <select
                        value={selectedStep.config.recipient_type || 'student'}
                        onChange={(e) => {
                          selectedStep.config.recipient_type = e.target.value;
                          setSelectedStep({ ...selectedStep });
                        }}
                      >
                        <option value="student">Student</option>
                        <option value="parent">Parent</option>
                        <option value="both">Student & Parent</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label>Email Subject</label>
                      <input
                        type="text"
                        value={selectedStep.config.subject || ''}
                        onChange={(e) => {
                          selectedStep.config.subject = e.target.value;
                          setSelectedStep({ ...selectedStep });
                        }}
                        placeholder="Email subject..."
                      />
                    </div>
                    <div className="form-group">
                      <label>Email Body</label>
                      <textarea
                        value={selectedStep.config.body || ''}
                        onChange={(e) => {
                          selectedStep.config.body = e.target.value;
                          setSelectedStep({ ...selectedStep });
                        }}
                        placeholder="Email body..."
                      />
                    </div>
                  </>
                )}

                {selectedStep.step_type === 'wait' && (
                  <div className="form-group">
                    <label>Delay (hours)</label>
                    <input
                      type="number"
                      value={selectedStep.config.delay_hours || 24}
                      onChange={(e) => {
                        selectedStep.config.delay_hours = parseInt(e.target.value);
                        setSelectedStep({ ...selectedStep });
                      }}
                    />
                  </div>
                )}

                <small>Step ID: {selectedStep.id}</small>
              </div>
            ) : (
              <div className="empty-config">
                <p>Select a step to configure</p>
              </div>
            )}
          </div>
        </div>

        <div className="builder-actions">
          <button className="btn-secondary" onClick={() => setMode('template')}>
            ← Back
          </button>
          <div className="right-actions">
            <input
              type="text"
              placeholder="Pipeline name..."
              value={pipelineData.name}
              onChange={(e) =>
                setPipelineData({ ...pipelineData, name: e.target.value })
              }
            />
            <button
              className="btn-primary"
              onClick={handleSavePipeline}
              disabled={loading}
            >
              {loading ? 'Saving...' : 'Save Pipeline'}
            </button>
            <button className="btn-secondary" onClick={onClose}>
              Cancel
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Monitor View
  if (mode === 'monitor') {
    return (
      <div className="pipeline-builder">
        <div className="pipeline-header">
          <h2>📊 Active Pipelines</h2>
          <button className="close-btn" onClick={onClose}>✕</button>
        </div>

        <div className="instances-list">
          {activeInstances.length === 0 ? (
            <p>No active pipeline instances</p>
          ) : (
            activeInstances.map((instance) => (
              <div key={instance.instance_id} className="instance-card">
                <h4>Instance: {instance.instance_id}</h4>
                <p>State: <strong>{instance.current_state}</strong></p>
                <p>Step: {instance.current_step}</p>
                <details>
                  <summary>Execution Log</summary>
                  <pre>{JSON.stringify(instance.execution_log, null, 2)}</pre>
                </details>
              </div>
            ))
          )}
        </div>

        <div className="builder-actions">
          <button className="btn-secondary" onClick={() => setMode('template')}>
            ← Back
          </button>
          <button className="btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    );
  }
};

export default PipelineBuilder;
