import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import './JobDetail.css';

export default function JobDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState(null);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [jobData, logsData] = await Promise.all([
          api.getJob(id),
          api.getJobLogs(id),
        ]);
        setJob(jobData);
        setLogs(logsData);
      } catch (err) {
        console.error('Failed to load job:', err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id]);

  const handleCancel = async () => {
    if (!confirm('Cancel this job?')) return;
    try {
      await api.cancelJob(id);
      const updated = await api.getJob(id);
      setJob(updated);
    } catch (err) {
      alert(err.message);
    }
  };

  if (loading) return <div className="empty-state pulse">Loading job...</div>;
  if (!job) return <div className="empty-state"><h3>Job not found</h3></div>;

  return (
    <div className="detail-page fade-in">
      <button className="btn btn--secondary" onClick={() => navigate(-1)}>
        ← Back
      </button>

      <div className="detail-header">
        <h1>Job Detail</h1>
        <code className="detail-id">{job.id}</code>
      </div>

      {/* Job Info Card */}
      <div className="detail-grid">
        <div className="card detail-card">
          <h2 className="section-title">Overview</h2>
          <div className="detail-fields">
            <div className="detail-field">
              <span className="detail-label">Type</span>
              <span>{job.type}</span>
            </div>
            <div className="detail-field">
              <span className="detail-label">Status</span>
              <span className={`badge badge--${job.status}`}>{job.status}</span>
            </div>
            <div className="detail-field">
              <span className="detail-label">Priority</span>
              <span className={`badge badge--priority-${job.priority}`}>
                {({ 1: 'High', 2: 'Medium', 3: 'Low' })[job.priority]}
              </span>
            </div>
            <div className="detail-field">
              <span className="detail-label">Effective Priority</span>
              <span>{job.effective_priority.toFixed(2)}</span>
            </div>
            <div className="detail-field">
              <span className="detail-label">Retries</span>
              <span>{job.retry_count} / {job.max_retries}</span>
            </div>
            <div className="detail-field">
              <span className="detail-label">In DLQ</span>
              <span>{job.is_in_dlq ? '💀 Yes' : 'No'}</span>
            </div>
            <div className="detail-field">
              <span className="detail-label">Interval</span>
              <span>{job.interval || '—'}</span>
            </div>
            <div className="detail-field">
              <span className="detail-label">Worker</span>
              <span>{job.worker_id || '—'}</span>
            </div>
          </div>

          {job.error_message && (
            <div className="detail-error">
              <strong>Error:</strong> {job.error_message}
            </div>
          )}

          {(job.status === 'pending' || job.status === 'processing') && (
            <button className="btn btn--danger" onClick={handleCancel} style={{ marginTop: 16 }}>
              Cancel Job
            </button>
          )}
        </div>

        <div className="card detail-card">
          <h2 className="section-title">Timestamps</h2>
          <div className="detail-fields">
            <div className="detail-field">
              <span className="detail-label">Created</span>
              <span>{new Date(job.created_at).toLocaleString()}</span>
            </div>
            <div className="detail-field">
              <span className="detail-label">Scheduled</span>
              <span>{job.scheduled_at ? new Date(job.scheduled_at).toLocaleString() : '—'}</span>
            </div>
            <div className="detail-field">
              <span className="detail-label">Started</span>
              <span>{job.started_at ? new Date(job.started_at).toLocaleString() : '—'}</span>
            </div>
            <div className="detail-field">
              <span className="detail-label">Completed</span>
              <span>{job.completed_at ? new Date(job.completed_at).toLocaleString() : '—'}</span>
            </div>
            <div className="detail-field">
              <span className="detail-label">Updated</span>
              <span>{new Date(job.updated_at).toLocaleString()}</span>
            </div>
          </div>

          <h2 className="section-title" style={{ marginTop: 20 }}>Payload</h2>
          <pre className="detail-payload">{JSON.stringify(job.payload, null, 2)}</pre>
        </div>
      </div>

      {/* Event Logs */}
      <div className="card" style={{ marginTop: 20 }}>
        <h2 className="section-title">Event Log</h2>
        {logs.length === 0 ? (
          <p className="text-muted">No log entries.</p>
        ) : (
          <div className="log-timeline">
            {logs.map((log) => (
              <div key={log.id} className={`log-entry log-entry--${log.event}`}>
                <div className="log-entry__dot" />
                <div className="log-entry__content">
                  <div className="log-entry__header">
                    <span className={`badge badge--${log.event === 'completed' ? 'completed' : log.event === 'failed' ? 'failed' : log.event === 'retry' ? 'pending' : log.event === 'cancelled' ? 'cancelled' : 'processing'}`}>
                      {log.event}
                    </span>
                    <span className="log-entry__time">
                      {new Date(log.created_at).toLocaleString()}
                    </span>
                  </div>
                  <p className="log-entry__message">{log.message}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
