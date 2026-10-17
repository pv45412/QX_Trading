import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  clearSchwabCredentials,
  completeSchwabAuthentication,
  getSchwabCredentialStatus,
  saveSchwabCredentials,
  testSchwabConnection,
} from './schwab-credentials-client.js';


test('credential client uses local-only API contracts', async () => {
  const calls = [];
  global.fetch = async (path, options = {}) => {
    calls.push({ path, options });
    return { ok: true, json: async () => ({ configured: true }) };
  };
  const sensitiveFixture = ['not', 'a', 'real', 'secret'].join('-');

  await getSchwabCredentialStatus();
  await saveSchwabCredentials({
    client_id: 'client',
    client_secret: sensitiveFixture,
    redirect_uri: 'https://127.0.0.1',
  });
  await testSchwabConnection();
  await completeSchwabAuthentication('https://127.0.0.1/?code=fixture');
  await clearSchwabCredentials();

  assert.equal(calls[0].path, '/api/system/schwab/credentials/status');
  assert.equal(calls[1].options.headers['X-QX-Local'], '1');
  assert.equal(calls[2].options.method, 'POST');
  assert.equal(calls[3].path, '/api/system/schwab/oauth-exchange');
  assert.equal(calls[4].options.method, 'DELETE');
});


test('Schwab UI masks sensitive fields and removes false watchlist verification', async () => {
  const source = await readFile(new URL('./QXSystemControl.jsx', import.meta.url), 'utf8');
  const layoutSource = await readFile(new URL('./QXBentoDashboardLayout.jsx', import.meta.url), 'utf8');

  assert.match(source, /aria-label="Client Secret" type="password"/);
  assert.match(source, /aria-label="Schwab Callback URL" type="password"/);
  assert.match(source, /setCallbackUrl\(''\)/);
  assert.doesNotMatch(source, /\/api\/terminal\/watchlist/);
  assert.doesNotMatch(source, /Refresh Token: Valid \(Expires in 5 days\)/);
  assert.doesNotMatch(source, /SYSTEM ONLINE/);
  assert.doesNotMatch(source, /All API contracts verified/);
  assert.match(layoutSource, /LOCAL CONTROL MODE/);
  assert.match(layoutSource, /if \(isSystemWorkspace\)/);
});
