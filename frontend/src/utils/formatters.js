/**
 * Format a UTC ISO string to the user's local time.
 */
export function formatDate(isoString) {
  if (!isoString) return '—';
  return new Date(isoString).toLocaleString();
}

/**
 * Format a UTC ISO string to a relative time (e.g., "2 min ago").
 */
export function timeAgo(isoString) {
  if (!isoString) return '—';
  const seconds = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
  if (seconds < 5) return 'just now';
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return formatDate(isoString);
}

/**
 * Shorten a UUID for display (first 8 chars).
 */
export function shortId(uuid) {
  if (!uuid) return '—';
  return uuid.slice(0, 8);
}

/**
 * Map priority number to label.
 */
export function priorityLabel(p) {
  return { 1: 'High', 2: 'Medium', 3: 'Low' }[p] || `P${p}`;
}
