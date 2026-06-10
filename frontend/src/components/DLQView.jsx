import { useEffect, useState } from 'react';
import { api } from '../api/client';
import './DLQView.css';

export default function DLQView() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [retrying, setRetrying] = useState(null);

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

  if (loading) {
    return <div className="empty-state pulse">Loading DLQ...</div>;
  }

  return (
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
                      <button
                        className="btn btn--primary btn--small"
                        disabled={retrying === job.id}
                        onClick={() => handleRetry(job.id)}
                      >
                        {retrying === job.id ? 'Retrying...' : '🔄 Retry'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
