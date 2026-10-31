// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { SettingsPanel } from '../src/components/admin/SettingsPanel';
import { api } from '../src/api';

vi.mock('../src/api', () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));

afterEach(() => { cleanup(); vi.clearAllMocks(); localStorage.clear(); });

const settings = {
  oracle_enabled: false, oracle_source_id: 'HUT_TCD_SUPP1', reporter_id_type: 'PERSON',
  base_url: 'https://oracle.example', api_path: '/timeEventRequests', endpoint: 'https://oracle.example/timeEventRequests',
  auth_mode: 'basic', rest_framework_version: '4', timeout_seconds: 15,
  credentials_configured: true, username: 'oracle-admin', password_configured: true,
  bearer_token_configured: false, connection_status: 'Not tested',
};

it('shows mode-specific inputs and only safe configured state', async () => {
  vi.mocked(api.get).mockResolvedValue(settings as never);
  render(<SettingsPanel />);
  await screen.findByLabelText('Username');
  expect(screen.getByLabelText(/^Password/)).toBeTruthy();
  expect(screen.queryByLabelText('Bearer token')).toBeNull();
  expect(screen.getByText(/Empty leaves the saved password unchanged/)).toBeTruthy();
  fireEvent.change(screen.getByLabelText('Authentication mode'), { target: { value: 'bearer' } });
  expect(screen.getByLabelText(/^Bearer token/)).toBeTruthy();
  expect(screen.queryByLabelText('Password')).toBeNull();
  fireEvent.change(screen.getByLabelText('Authentication mode'), { target: { value: 'none' } });
  expect(screen.queryByLabelText('Username')).toBeNull();
  expect(screen.queryByLabelText('Bearer token')).toBeNull();
  expect(document.body.textContent).not.toContain('private-secret');
});

it('saves unrelated credential settings with blank secrets omitted and reports auth test separately', async () => {
  vi.mocked(api.get).mockResolvedValue(settings as never);
  vi.mocked(api.put).mockResolvedValue({ saved: true, auth_mode: 'basic', username: 'oracle-admin', password_configured: true, bearer_token_configured: false, credentials_configured: true } as never);
  vi.mocked(api.post).mockResolvedValue({ credentials_configured: true, validated: true, result: 'authenticated', http_status: 200, auth_mode: 'basic', duration_ms: 500, detail: 'Oracle accepted the configured credentials and authorized access to the read-only metadata endpoint.' } as never);
  render(<SettingsPanel />);
  fireEvent.click(await screen.findByRole('button', { name: 'Save authentication settings' }));
  await waitFor(() => expect(api.put).toHaveBeenCalled());
  const body = vi.mocked(api.put).mock.calls[0][1] as Record<string, unknown>;
  expect(body.password).toBeUndefined();
  expect(body.bearer_token).toBeUndefined();
  expect(body.clear_credentials).toBe(false);
  expect(await screen.findByText(/Oracle delivery remains disabled/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Test Oracle authentication' }));
  expect(await screen.findByText('Authenticated and authorized')).toBeTruthy();
  expect(screen.getByText('HTTP status: 200')).toBeTruthy();
  expect(screen.getByText('Oracle delivery is disabled. Authentication validation never changes the delivery setting.')).toBeTruthy();
  expect(api.post).toHaveBeenCalledWith('/api/v1/admin/integration-authentication-test', {});
  expect(api.post).not.toHaveBeenCalledWith('/api/v1/admin/integration-connection-test', expect.anything());
});

it('renders none mode without credential controls and keeps delivery visibly disabled', async () => {
  vi.mocked(api.get).mockResolvedValue({ ...settings, auth_mode: 'none', credentials_configured: false, username: '', password_configured: false } as never);
  render(<SettingsPanel />);
  await screen.findByText('None', { selector: 'option' });
  expect(screen.queryByLabelText('Password')).toBeNull();
  expect(screen.queryByLabelText('Bearer token')).toBeNull();
  expect(screen.getByText(/Oracle delivery is DISABLED/)).toBeTruthy();
});


it.each([
  [401, 'authentication_rejected', 'Authentication rejected'],
  [403, 'insufficient_privilege', 'Authenticated, insufficient privilege'],
  [503, 'oracle_error', 'Oracle returned a server error'],
  [null, 'proxy_error', 'Proxy connection failed'],
  [null, 'timeout', 'Oracle authentication test timed out'],
  [null, 'tls_error', 'TLS validation failed'],
  [null, 'connectivity_error', 'Oracle host connectivity failed'],
  [418, 'http_error', 'Oracle HTTP error'],
])('shows a clear authentication result for HTTP %s', async (http_status, result, heading) => {
  vi.mocked(api.get).mockResolvedValue(settings as never);
  vi.mocked(api.post).mockResolvedValue({
    credentials_configured: true, validated: false, result, http_status, auth_mode: 'basic',
    duration_ms: 400, detail: `Safe explanation for HTTP ${http_status}.`,
  } as never);
  render(<SettingsPanel />);
  fireEvent.click(await screen.findByRole('button', { name: 'Test Oracle authentication' }));
  expect(await screen.findByText(heading)).toBeTruthy();
  expect(screen.getByText(`HTTP status: ${http_status ?? 'No response'}`)).toBeTruthy();
  expect(screen.getByText(`Safe explanation for HTTP ${http_status}.`)).toBeTruthy();
});
