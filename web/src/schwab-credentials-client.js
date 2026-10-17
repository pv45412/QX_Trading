const LOCAL_HEADERS = {
  'Content-Type': 'application/json',
  'X-QX-Local': '1',
};

async function request(path, options = {}) {
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `Request failed with status ${response.status}`);
  }
  return payload;
}

export function getSchwabCredentialStatus() {
  return request('/api/system/schwab/credentials/status');
}

export function saveSchwabCredentials(credentials) {
  return request('/api/system/schwab/credentials', {
    method: 'POST',
    headers: LOCAL_HEADERS,
    body: JSON.stringify(credentials),
  });
}

export function clearSchwabCredentials() {
  return request('/api/system/schwab/credentials', {
    method: 'DELETE',
    headers: LOCAL_HEADERS,
  });
}

export function testSchwabConnection() {
  return request('/api/system/schwab/test', {
    method: 'POST',
    headers: LOCAL_HEADERS,
  });
}

export function getSchwabOAuthUrl() {
  return request('/api/system/schwab/oauth-url');
}

export function completeSchwabAuthentication(callbackUrl) {
  return request('/api/system/schwab/oauth-exchange', {
    method: 'POST',
    headers: LOCAL_HEADERS,
    body: JSON.stringify({ callback_url: callbackUrl }),
  });
}
