const API_BASE = '/api';

async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const config = {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  };

  const res = await fetch(url, config);

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

export const api = {
  // Jobs
  createJob: (data) => request('/jobs', { method: 'POST', body: JSON.stringify(data) }),
  listJobs: (params = {}) => {
    const query = new URLSearchParams();
    if (params.status) query.set('status', params.status);
    if (params.type) query.set('type', params.type);
    if (params.priority) query.set('priority', params.priority);
    if (params.limit) query.set('limit', params.limit);
    if (params.offset) query.set('offset', params.offset);
    const qs = query.toString();
    return request(`/jobs${qs ? '?' + qs : ''}`);
  },
  getJob: (id) => request(`/jobs/${id}`),
  cancelJob: (id) => request(`/jobs/${id}/cancel`, { method: 'PATCH' }),
  getJobLogs: (id) => request(`/jobs/${id}/logs`),

  // DLQ
  listDLQ: () => request('/dlq'),
  retryDLQ: (id, payload) => request(`/dlq/${id}/retry`, { 
    method: 'POST', 
    body: payload ? JSON.stringify({ payload }) : undefined 
  }),

  // Dashboard
  getStats: () => request('/dashboard/stats'),

  // Workflows
  createWorkflow: (data) => request('/workflows', { method: 'POST', body: JSON.stringify(data) }),
};
