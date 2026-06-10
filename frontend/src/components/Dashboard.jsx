import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { useSSE } from '../hooks/useSSE';
import './Dashboard.css';

const STAT_CONFIG = [
  { key: 'pending', label: 'Pending', icon: '⏳' },
  { key: 'processing', label: 'Processing', icon: '⚙️' },
  { key: 'completed', label: 'Completed', icon: '✅' },
  { key: 'failed', label: 'Failed', icon: '❌' },
  { key: 'cancelled', label: 'Cancelled', icon: '🚫' },
  { key: 'dlq_count', label: 'In DLQ', icon: '💀' },
];

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [recentJobs, setRecentJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const { stats: liveStats } = useSSE();

  // Use live stats from SSE if available, otherwise use fetched stats
  const displayStats = liveStats || stats;

  useEffect(() => {
    async function load() {
      try {
        const [statsData, jobsData] = await Promise.all([
          api.getStats(),
          api.listJobs({ limit: 8 }),
        ]);
        setStats(statsData);
        setRecentJobs(jobsData.jobs || []);
      } catch (err) {
        console.error('Failed to load dashboard:', err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return <div className="empty-state pulse">Loading dashboard...</div>;
  }

  return (
    <div className="dashboard fade-in">
      <div className="dashboard__header">
        <h1>Dashboard</h1>
        <p className="dashboard__subtitle">Real-time job scheduler overview</p>
      </div>

      {/* Stats Cards */}
      <div className="stats-grid">
        {STAT_CONFIG.map(({ key, label, icon }) => (
          <div key={key} className={`stat-card stat-card--${key}`}>
            <div className="stat-card__icon">{icon}</div>
            <div className="stat-card__info">
              <span className="stat-card__value">
                {displayStats?.[key] ?? 0}
              </span>
              <span className="stat-card__label">{label}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Total */}
      <div className="dashboard__total">
        Total Jobs: <strong>{displayStats?.total ?? 0}</strong>
      </div>

      {/* Recent Jobs */}
      <div className="card" style={{ marginTop: 24 }}>
        <h2 className="section-title">Recent Jobs</h2>
        {recentJobs.length === 0 ? (
          <div className="empty-state">
            <h3>No jobs yet</h3>
            <p>Create your first job to get started.</p>
          </div>
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Type</th>
                  <th>Priority</th>
                  <th>Status</th>
                  <th>Retries</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {recentJobs.map((job) => (
                  <tr key={job.id}>
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
                    <td>{new Date(job.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
