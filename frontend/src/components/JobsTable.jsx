import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useSSE } from '../hooks/useSSE';
import './JobsTable.css';

export default function JobsTable() {
  const [jobs, setJobs] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ status: '', type: '', priority: '' });
  const [offset, setOffset] = useState(0);
  const limit = 20;
  const navigate = useNavigate();
  const { lastUpdate } = useSSE();

  const fetchJobs = useCallback(async () => {
    try {
      const params = { limit, offset };
      if (filters.status) params.status = filters.status;
      if (filters.type) params.type = filters.type;
      if (filters.priority) params.priority = filters.priority;
      const data = await api.listJobs(params);
      setJobs(data.jobs || []);
      setTotal(data.total || 0);
    } catch (err) {
      console.error('Failed to load jobs:', err);
    } finally {
      setLoading(false);
    }
  }, [filters, offset]);

  useEffect(() => { fetchJobs(); }, [fetchJobs]);

  // Refresh when SSE pushes a job update
  useEffect(() => {
    if (lastUpdate) fetchJobs();
  }, [lastUpdate]);

  const handleCancel = async (e, jobId) => {
    e.stopPropagation();
    if (!confirm('Cancel this job?')) return;
    try {
      await api.cancelJob(jobId);
      fetchJobs();
    } catch (err) {
      alert(err.message);
    }
  };

  const totalPages = Math.ceil(total / limit);
  const currentPage = Math.floor(offset / limit) + 1;

  return (
    <div className="jobs-page fade-in">
      <div className="jobs-page__header">
        <h1>Jobs</h1>
        <span className="jobs-page__count">{total} total</span>
      </div>

      {/* Filters */}
      <div className="jobs-filters">
        <select
          className="form-select"
          value={filters.status}
          onChange={(e) => { setFilters(f => ({ ...f, status: e.target.value })); setOffset(0); }}
        >
          <option value="">All Statuses</option>
          <option value="pending">Pending</option>
          <option value="processing">Processing</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
          <option value="cancelled">Cancelled</option>
        </select>

        <select
          className="form-select"
          value={filters.type}
          onChange={(e) => { setFilters(f => ({ ...f, type: e.target.value })); setOffset(0); }}
        >
          <option value="">All Types</option>
          <option value="send_email">send_email</option>
          <option value="generate_report">generate_report</option>
          <option value="upload_file">upload_file</option>
        </select>

        <select
          className="form-select"
          value={filters.priority}
          onChange={(e) => { setFilters(f => ({ ...f, priority: e.target.value })); setOffset(0); }}
        >
          <option value="">All Priorities</option>
          <option value="1">High (1)</option>
          <option value="2">Medium (2)</option>
          <option value="3">Low (3)</option>
        </select>
      </div>

      {/* Table */}
      {loading ? (
        <div className="empty-state pulse">Loading jobs...</div>
      ) : jobs.length === 0 ? (
        <div className="empty-state">
          <h3>No jobs found</h3>
          <p>Try adjusting your filters or create a new job.</p>
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
                  <th>Status</th>
                  <th>Retries</th>
                  <th>Scheduled</th>
                  <th>Interval</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr
                    key={job.id}
                    className="jobs-row"
                    onClick={() => navigate(`/jobs/${job.id}`)}
                  >
                    <td><code>{job.id.slice(0, 8)}</code></td>
                    <td>{job.type}</td>
                    <td>
                      <span className={`badge badge--priority-${job.priority}`}>
                        {({ 1: 'High', 2: 'Medium', 3: 'Low' })[job.priority]}
                      </span>
                    </td>
                    <td>
                      <span className={`badge badge--${job.status}`}>
                        {job.status}
                      </span>
                    </td>
                    <td>{job.retry_count}/{job.max_retries}</td>
                    <td>{job.scheduled_at ? new Date(job.scheduled_at).toLocaleString() : '—'}</td>
                    <td>{job.interval || '—'}</td>
                    <td>{new Date(job.created_at).toLocaleString()}</td>
                    <td>
                      {(job.status === 'pending' || job.status === 'processing') && (
                        <button
                          className="btn btn--danger btn--small"
                          onClick={(e) => handleCancel(e, job.id)}
                        >
                          Cancel
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="pagination">
              <button
                className="btn btn--secondary btn--small"
                disabled={offset === 0}
                onClick={() => setOffset(o => Math.max(0, o - limit))}
              >
                ← Prev
              </button>
              <span className="pagination__info">
                Page {currentPage} of {totalPages}
              </span>
              <button
                className="btn btn--secondary btn--small"
                disabled={offset + limit >= total}
                onClick={() => setOffset(o => o + limit)}
              >
                Next →
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
