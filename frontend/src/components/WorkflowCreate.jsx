import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import './WorkflowCreate.css';

const JOB_TYPES = ['send_email', 'generate_report', 'upload_file'];

const EMPTY_STEP = { type: 'generate_report', priority: 2, payload: '{}', depends_on_index: [] };

export default function WorkflowCreate() {
  const navigate = useNavigate();
  const [steps, setSteps] = useState([
    { ...EMPTY_STEP, type: 'generate_report', payload: '{"report_name": "Sales Report"}' },
    { ...EMPTY_STEP, type: 'upload_file', payload: '{"bucket": "reports"}', depends_on_index: [0] },
    { ...EMPTY_STEP, type: 'send_email', payload: '{"to": "admin@co.com", "subject": "Report Ready"}', depends_on_index: [1] },
  ]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const updateStep = (idx, field, value) => {
    setSteps(prev => prev.map((s, i) => i === idx ? { ...s, [field]: value } : s));
  };

  const addStep = () => {
    setSteps(prev => [...prev, { ...EMPTY_STEP }]);
  };

  const removeStep = (idx) => {
    if (steps.length <= 1) return;
    setSteps(prev => {
      const updated = prev.filter((_, i) => i !== idx);
      // Fix dependency indices
      return updated.map(s => ({
        ...s,
        depends_on_index: s.depends_on_index
          .map(d => d > idx ? d - 1 : d)
          .filter(d => d !== idx && d >= 0),
      }));
    });
  };

  const toggleDep = (stepIdx, depIdx) => {
    setSteps(prev => prev.map((s, i) => {
      if (i !== stepIdx) return s;
      const deps = s.depends_on_index.includes(depIdx)
        ? s.depends_on_index.filter(d => d !== depIdx)
        : [...s.depends_on_index, depIdx];
      return { ...s, depends_on_index: deps };
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setSubmitting(true);

    try {
      const jobsData = steps.map(s => {
        let payload;
        try { payload = JSON.parse(s.payload); }
        catch { throw new Error(`Invalid JSON in step payload`); }
        return {
          type: s.type,
          priority: s.priority,
          payload,
          depends_on_index: s.depends_on_index,
        };
      });

      const result = await api.createWorkflow({ jobs: jobsData });
      setSuccess(`Workflow created with ${result.jobs.length} jobs!`);
      setTimeout(() => navigate('/jobs'), 1500);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="workflow-page fade-in">
      <h1>🔗 Create Workflow</h1>
      <p className="workflow-page__subtitle">
        Build a DAG of jobs with dependencies. Each step runs only after its dependencies complete.
      </p>

      <form onSubmit={handleSubmit}>
        <div className="workflow-steps">
          {steps.map((step, idx) => (
            <div key={idx} className="card workflow-step">
              <div className="workflow-step__header">
                <span className="workflow-step__num">Step {idx + 1}</span>
                {steps.length > 1 && (
                  <button type="button" className="btn btn--danger btn--small" onClick={() => removeStep(idx)}>
                    Remove
                  </button>
                )}
              </div>

              <div className="workflow-step__fields">
                <div className="form-group">
                  <label>Type</label>
                  <select className="form-select" value={step.type} onChange={(e) => updateStep(idx, 'type', e.target.value)}>
                    {JOB_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>

                <div className="form-group">
                  <label>Priority</label>
                  <select className="form-select" value={step.priority} onChange={(e) => updateStep(idx, 'priority', Number(e.target.value))}>
                    <option value={1}>High (1)</option>
                    <option value={2}>Medium (2)</option>
                    <option value={3}>Low (3)</option>
                  </select>
                </div>

                <div className="form-group">
                  <label>Payload (JSON)</label>
                  <textarea
                    className="form-input"
                    rows={2}
                    value={step.payload}
                    onChange={(e) => updateStep(idx, 'payload', e.target.value)}
                    style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}
                  />
                </div>

                {idx > 0 && (
                  <div className="form-group">
                    <label>Depends on</label>
                    <div className="dep-chips">
                      {steps.slice(0, idx).map((_, depIdx) => (
                        <button
                          key={depIdx}
                          type="button"
                          className={`dep-chip ${step.depends_on_index.includes(depIdx) ? 'dep-chip--active' : ''}`}
                          onClick={() => toggleDep(idx, depIdx)}
                        >
                          Step {depIdx + 1}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Dependency Arrow */}
              {idx < steps.length - 1 && (
                <div className="workflow-arrow">↓</div>
              )}
            </div>
          ))}
        </div>

        <button type="button" className="btn btn--secondary workflow-add" onClick={addStep}>
          + Add Step
        </button>

        {error && <div className="create-msg create-msg--error">{error}</div>}
        {success && <div className="create-msg create-msg--success">{success}</div>}

        <button type="submit" className="btn btn--primary create-submit" disabled={submitting}>
          {submitting ? 'Creating...' : 'Create Workflow'}
        </button>
      </form>
    </div>
  );
}
