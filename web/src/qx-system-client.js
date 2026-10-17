async function requestJson(path, options = {}) {
  const response = await fetch(path, {signal: options.signal});
  if (!response.ok) throw new Error(`System status unavailable (${response.status})`);
  return response.json();
}

export function fetchSystemOverview(options = {}) {
  return requestJson('/api/system/overview', options);
}

export function fetchSystemJobStatus(options = {}) {
  return requestJson('/api/system/jobs/status', options);
}

