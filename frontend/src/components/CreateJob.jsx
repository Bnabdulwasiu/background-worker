import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import './CreateJob.css';

const JOB_TYPES = ['send_email', 'generate_report', 'upload_file'];
const INTERVALS = [
  { value: '', label: 'None (one-time)' },
  { value: 'every_1_minute', label: 'Every 1 minute' },
  { value: 'every_5_minutes', label: 'Every 5 minutes' },
  { value: 'every_1_hour', label: 'Every 1 hour' },
];

const PAYLOAD_TEMPLATES = {
  send_email: JSON.stringify({ to: 'user@example.com', subject: 'Hello', body: 'Message content' }, null, 2),
  generate_report: JSON.stringify({ report_name: 'Monthly Sales', format: 'pdf' }, null, 2),
  upload_file: JSON.stringify({ bucket: 'my-bucket', file_name: 'report.pdf' }, null, 2),
};

export default function CreateJob() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    type: 'send_email',
    priority: 2,
    payload: PAYLOAD_TEMPLATES.send_email,
    scheduled_at: '',
    interval: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const handleTypeChange = (type) => {
    setForm(f => ({
      ...f,
      type,
      payload: PAYLOAD_TEMPLATES[type] || '{}',
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setSubmitting(true);

    try {
      let payload;
      try {
        payload = JSON.parse(form.payload);
      } catch {
        throw new Error('Invalid JSON in payload field');
      }

      const data = {
        type: form.type,
        priority: Number(form.priority),
        payload,
      };
      if (form.scheduled_at) data.scheduled_at = new Date(form.scheduled_at).toISOString();
      if (form.interval) data.interval = form.interval;

      const job = await api.createJob(data);
      setSuccess(`Job created: ${job.id.slice(0, 8)}...`);

      // Reset form after short delay
      setTimeout(() => {
        navigate('/jobs');
      }, 1200);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="create-page fade-in">
      <h1>Create Job</h1>
      <p className="create-page__subtitle">Submit a new job to the scheduler</p>

      <form className="create-form card" onSubmit={handleSubmit}>
        {/* Job Type */}
        <div className="form-group">
          <label htmlFor="job-type">Job Type</label>
          <div className="type-selector">
            {JOB_TYPES.map((t) => (
              <button
                key={t}
                type="button"
                className={`type-btn ${form.type === t ? 'type-btn--active' : ''}`}
                onClick={() => handleTypeChange(t)}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        {/* Priority */}
        <div className="form-group">
          <label htmlFor="priority">Priority</label>
          <div className="priority-selector">
            {[1, 2, 3].map((p) => (
              <button
                key={p}
                type="button"
                className={`priority-btn priority-btn--${p} ${form.priority === p ? 'priority-btn--active' : ''}`}
                onClick={() => setForm(f => ({ ...f, priority: p }))}
              >
                {({ 1: '🔴 High', 2: '🟡 Medium', 3: '⚪ Low' })[p]}
              </button>
            ))}
          </div>
        </div>

        {/* Payload */}
        <div className="form-group">
          <label htmlFor="payload">Payload (JSON)</label>
          <textarea
            id="payload"
            className="form-input payload-editor"
            rows={6}
            value={form.payload}
            onChange={(e) => setForm(f => ({ ...f, payload: e.target.value }))}
          />
        </div>

        {/* Schedule */}
        <div className="form-row">
          <div className="form-group">
            <label htmlFor="scheduled_at">Scheduled At (optional)</label>
            <input
              id="scheduled_at"
              type="datetime-local"
              className="form-input"
              value={form.scheduled_at}
              onChange={(e) => setForm(f => ({ ...f, scheduled_at: e.target.value }))}
            />
          </div>

          <div className="form-group">
            <label htmlFor="interval">Recurring Interval</label>
            <select
              id="interval"
              className="form-select"
              value={form.interval}
              onChange={(e) => setForm(f => ({ ...f, interval: e.target.value }))}
            >
              {INTERVALS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Error / Success */}
        {error && <div className="create-msg create-msg--error">{error}</div>}
        {success && <div className="create-msg create-msg--success">{success}</div>}

        {/* Submit */}
        <button type="submit" className="btn btn--primary create-submit" disabled={submitting}>
          {submitting ? 'Creating...' : 'Create Job'}
        </button>
      </form>
    </div>
  );
}
