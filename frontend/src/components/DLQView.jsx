import { useEffect, useState } from 'react';
import { api } from '../api/client';
import './DLQView.css';

export default function DLQView() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [retrying, setRetrying] = useState(null);
  const [editingJob, setEditingJob] = useState(null);
  const [payloadText, setPayloadText] = useState('');
  const [jsonError, setJsonError] = useState(null);

  const fetchDLQ = async () => {
    try {
      const data = await api.listDLQ();
      setJobs(data);
    } catch (err) {
      console.error('Failed to load DLQ:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchDLQ(); }, []);

  const handleRetry = async (jobId) => {
    setRetrying(jobId);
    try {
      await api.retryDLQ(jobId);
      fetchDLQ();
    } catch (err) {
      alert(err.message);
    } finally {
      setRetrying(null);
    }
  };

  const openEditModal = (job) => {
    setEditingJob(job);
    setPayloadText(JSON.stringify(job.payload, null, 2));
    setJsonError(null);
  };

  const closeEditModal = () => {
    setEditingJob(null);
    setPayloadText('');
    setJsonError(null);
  };

  const handleEditAndRetry = async (e) => {
    e.preventDefault();
    try {
      const parsedPayload = JSON.parse(payloadText);
      if (typeof parsedPayload !== 'object' || parsedPayload === null || Array.isArray(parsedPayload)) {
        throw new Error('Payload must be a JSON object');
      }
      setJsonError(null);
      const jobId = editingJob.id;
      setRetrying(jobId);
      setEditingJob(null);
      await api.retryDLQ(jobId, parsedPayload);
      fetchDLQ();
    } catch (err) {
      setJsonError(err.message);
    } finally {
      setRetrying(null);
    }
  };

  if (loading) {
    return <div className="empty-state pulse">Loading DLQ...</div>;
  }

  return (
    <>
    <div className="dlq-page fade-in">
      <div className="dlq-page__header">
        <h1>Dead Letter Queue</h1>
        <span className="dlq-page__count">
          {jobs.length} job{jobs.length !== 1 ? 's' : ''}
        </span>
      </div>

      {jobs.length > 0 && jobs.length >= 10 && (
        <div className="dlq-alert">
          ⚠️ DLQ threshold reached — {jobs.length} failed jobs require attention.
        </div>
      )}

      {jobs.length === 0 ? (
        <div className="empty-state">
          <h3>DLQ is empty</h3>
          <p>No failed jobs — everything is running smoothly.</p>
        </div>
      ) : (
        <div className="card">
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Type</th>
                  <th>Priority</th>
                  <th>Retries</th>
                  <th>Error</th>
                  <th>Failed At</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.id}>
                    <td><code>{job.id.slice(0, 8)}</code></td>
                    <td>{job.type}</td>
                    <td>
                      <span className={`badge badge--priority-${job.priority}`}>
                        {({ 1: 'High', 2: 'Medium', 3: 'Low' })[job.priority]}
                      </span>
                    </td>
                    <td>{job.retry_count}/{job.max_retries}</td>
                    <td className="dlq-error-cell">
                      <span className="dlq-error-text" title={job.error_message}>
                        {job.error_message?.slice(0, 60) || '—'}
                        {job.error_message?.length > 60 ? '...' : ''}
                      </span>
                    </td>
                    <td>{new Date(job.updated_at).toLocaleString()}</td>
                    <td>
                      <div className="dlq-actions">
                        <button
                          className="btn btn--primary btn--small"
                          disabled={retrying === job.id}
                          onClick={() => handleRetry(job.id)}
                        >
                          {retrying === job.id ? 'Retrying...' : '🔄 Retry'}
                        </button>
                        <button
                          className="btn btn--secondary btn--small"
                          disabled={retrying === job.id}
                          onClick={() => openEditModal(job)}
                        >
                          ✏️ Edit & Retry
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>

    {editingJob && (
      <div className="modal-overlay" onClick={closeEditModal}>
        <div className="modal-content card" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h2>Edit Payload & Retry</h2>
            <button className="modal-close-btn" onClick={closeEditModal}>&times;</button>
          </div>
          <p className="modal-subtitle">
            Job ID: <code>{editingJob.id}</code> ({editingJob.type})
          </p>
          <form onSubmit={handleEditAndRetry}>
            <div className="form-group" style={{ marginBottom: 16 }}>
              <label htmlFor="payload-editor">Job Payload (JSON)</label>
              <textarea
                id="payload-editor"
                className="form-input dlq-payload-textarea"
                value={payloadText}
                onChange={(e) => setPayloadText(e.target.value)}
                rows={8}
              />
              {jsonError && (
                <span className="dlq-error-text" style={{ marginTop: 8 }}>
                  ⚠️ {jsonError}
                </span>
              )}
            </div>
            <div className="modal-actions">
              <button
                type="button"
                className="btn btn--secondary"
                onClick={closeEditModal}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="btn btn--primary"
              >
                Confirm & Retry
              </button>
            </div>
          </form>
        </div>
      </div>
    )}
    </>
  );
}
