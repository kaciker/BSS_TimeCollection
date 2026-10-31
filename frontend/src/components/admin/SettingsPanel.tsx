import { useEffect, useState } from "react";
import { api } from "../../api";
import { languageOptions, useLanguage } from "../../i18n";

type IntegrationSettings = {
  oracle_enabled: boolean;
  oracle_source_id: string;
  reporter_id_type: string;
  base_url: string;
  api_path: string;
  endpoint: string;
  auth_mode: string;
  rest_framework_version: string;
  timeout_seconds: number;
  credentials_configured: boolean;
  username: string;
  password_configured: boolean;
  bearer_token_configured: boolean;
  password: string;
  bearer_token: string;
  connection_status: string;
};

type OracleConnectivityResult = {
  reachable: boolean;
  tls: boolean | null;
  http_status: number | null;
  detail: string;
};

type OracleAuthenticationResult = {
  credentials_configured: boolean;
  validated: boolean;
  result: string;
  http_status: number | null;
  auth_mode: string;
  duration_ms?: number;
  detail: string;
};

function authenticationResultTitle(result: string): string {
  const titles: Record<string, string> = {
    authenticated: "Authenticated and authorized",
    authentication_rejected: "Authentication rejected",
    insufficient_privilege: "Authenticated, insufficient privilege",
    proxy_error: "Proxy connection failed",
    timeout: "Oracle authentication test timed out",
    tls_error: "TLS validation failed",
    connectivity_error: "Oracle host connectivity failed",
    oracle_error: "Oracle returned a server error",
    http_error: "Oracle HTTP error",
    credentials_missing: "Oracle credentials not configured",
    unsupported_auth_mode: "Unsupported authentication mode",
    request_error: "Authentication test request failed",
  };
  return titles[result] ?? "Oracle authentication test failed";
}

export function SettingsPanel() {
  const { language, setLanguage, t } = useLanguage();
  const [integration, setIntegration] = useState<IntegrationSettings | null>(null);
  const [integrationError, setIntegrationError] = useState("");
  const [connectionTest, setConnectionTest] = useState<OracleConnectivityResult | null>(null);
  const [testingConnection, setTestingConnection] = useState(false);
  const [authMode, setAuthMode] = useState("none");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [bearerToken, setBearerToken] = useState("");
  const [clearCredentials, setClearCredentials] = useState(false);
  const [savingCredentials, setSavingCredentials] = useState(false);
  const [credentialMessage, setCredentialMessage] = useState("");
  const [authenticationTest, setAuthenticationTest] = useState<OracleAuthenticationResult | null>(null);
  const [testingAuthentication, setTestingAuthentication] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void api.get<IntegrationSettings>("/api/v1/admin/integration-settings")
      .then(value => { if (!cancelled) { setIntegration(value); setAuthMode(value.auth_mode); setUsername(value.username); } })
      .catch(error => { if (!cancelled) setIntegrationError((error as Error).message); });
    return () => { cancelled = true; };
  }, []);

  return <div className="admin-stack">
    <section className="admin-card">
      <div className="section-heading"><div><h3>{t("language")}</h3><p>{t("languageHelp")}</p></div></div>
      <div className="form-grid"><label>{t("language")}<select value={language} onChange={event => setLanguage(event.target.value as typeof language)}>{languageOptions.map(option => <option value={option.value} key={option.value}>{option.label}</option>)}</select></label></div>
      <p className="form-hint">{t("languageSaved")}</p>
    </section>
    <section className="admin-card">
      <div className="section-heading"><div><h3>Oracle integration</h3><p>Global integration values apply to every terminal. They are not configured per terminal.</p></div></div>
      {integration ? <><div className="form-grid">
        <label>Environment / target server<input value={integration.base_url.replace(/^https:\/\//, "").split(".")[0]} readOnly /></label>
        <label>Base URL<input value={integration.base_url} readOnly /></label>
        <label>API endpoint<input value={integration.endpoint} readOnly /></label>
        <label>Source ID<input value={integration.oracle_source_id} readOnly /></label>
        <label>Authentication mode<select value={authMode} onChange={event => { setAuthMode(event.target.value); setCredentialMessage(""); }}><option value="none">None</option><option value="basic">Basic</option><option value="bearer">Bearer</option></select></label>
        <label>Reporter type<input value={integration.reporter_id_type} readOnly /></label>
        <label>REST Framework Version<input value={integration.rest_framework_version} readOnly /></label>
        <label>Timeout (seconds)<input value={integration.timeout_seconds} readOnly /></label>
        <label>Oracle delivery<input value={integration.oracle_enabled ? "Enabled" : "Disabled"} readOnly /></label>
        <label>Connection test status<input value={integration.connection_status} readOnly /></label>
      </div><p className="form-notice">Credentials: {integration.credentials_configured ? "Configured" : "Not configured"}. Passwords and tokens are never returned to the browser. Oracle delivery is {integration.oracle_enabled ? "ENABLED" : "DISABLED"} and remains separate from credential configuration.</p>
      <div className="form-grid">
        {authMode === "basic" && <>
          <label>Username<input autoComplete="off" value={username} onChange={event => setUsername(event.target.value)} /></label>
          <label>Password<input type="password" autoComplete="new-password" value={password} onChange={event => setPassword(event.target.value)} placeholder={integration.password_configured ? "Configured — enter a new value to replace" : "Not configured"} /><small>{integration.password_configured ? "Configured" : "Not configured"}. Empty leaves the saved password unchanged.</small></label>
        </>}
        {authMode === "bearer" && <label>Bearer token<input type="password" autoComplete="new-password" value={bearerToken} onChange={event => setBearerToken(event.target.value)} placeholder={integration.bearer_token_configured ? "Configured — enter a new value to replace" : "Not configured"} /><small>{integration.bearer_token_configured ? "Configured" : "Not configured"}. Empty leaves the saved token unchanged.</small></label>}
      </div>
      {authMode !== "none" && (integration.password_configured || integration.bearer_token_configured) && <label className="form-hint"><input type="checkbox" checked={clearCredentials} onChange={event => setClearCredentials(event.target.checked)} /> Explicitly clear the configured credential</label>}
      <button className="primary" type="button" disabled={savingCredentials} onClick={() => { setSavingCredentials(true); setCredentialMessage(""); void api.put<{saved:boolean;auth_mode:string;username:string;password_configured:boolean;bearer_token_configured:boolean;credentials_configured:boolean}>("/api/v1/admin/integration-credentials", { auth_mode: authMode, username: authMode === "basic" ? username : undefined, password: password || undefined, bearer_token: bearerToken || undefined, clear_credentials: clearCredentials }).then(result => { setIntegration({...integration, auth_mode:result.auth_mode, username:result.username, password_configured:result.password_configured, bearer_token_configured:result.bearer_token_configured, credentials_configured:result.credentials_configured}); setPassword(""); setBearerToken(""); setClearCredentials(false); setCredentialMessage("Oracle authentication settings saved. Oracle delivery remains disabled."); }).catch(error => setCredentialMessage((error as Error).message)).finally(() => setSavingCredentials(false)); }}>{savingCredentials ? "Saving…" : "Save authentication settings"}</button>
      {credentialMessage && <p role="status" className="form-hint">{credentialMessage}</p>}
      <div className="section-heading"><div><h4>Oracle host connectivity</h4><p>Checks network/TLS and the HTTP response from the Oracle host. This does not validate credentials or change delivery.</p></div></div>
      <button className="secondary" type="button" disabled={testingConnection} onClick={() => { setTestingConnection(true); setConnectionTest(null); void api.post<OracleConnectivityResult>("/api/v1/admin/integration-connection-test", {}).then(result => setConnectionTest(result)).catch(error => { const message = (error as Error).message; const status = message.match(/HTTP\s+(\d{3})/i); setConnectionTest({ reachable: false, tls: null, http_status: null, detail: `Connectivity test request failed${status ? ` · HTTP ${status[1]}` : ""}: ${message}` }); }).finally(() => setTestingConnection(false)); }}>{testingConnection ? "Testing host…" : "Test Oracle host connectivity"}</button>
      {testingConnection && <p role="status" className="form-hint">Checking Oracle host connectivity…</p>}
      {connectionTest && <div className={`oracle-connectivity-result ${connectionTest.reachable ? "success-notice" : "inline-error"}`} role={connectionTest.reachable ? "status" : "alert"} aria-live="polite">
        <strong>{connectionTest.reachable ? "Host reachable" : "Connectivity test failed"}</strong>
        <span>TLS: {connectionTest.tls === null ? "Handshake status unavailable" : connectionTest.tls ? `HTTPS configured · handshake ${connectionTest.reachable ? "confirmed" : "not confirmed"}` : "Not using HTTPS"}</span>
        <span>HTTP status: {connectionTest.http_status ?? "No response"}</span>
        <span>{connectionTest.detail}</span>
      </div>}
      <div className="section-heading"><div><h4>Oracle authentication validation</h4><p>Tests the stored credentials against Oracle’s read-only time event metadata endpoint. This sends GET only; no time event is created and delivery stays disabled.</p></div></div>
      <button className="secondary" type="button" disabled={testingAuthentication || !integration.credentials_configured} onClick={() => { setTestingAuthentication(true); setAuthenticationTest(null); void api.post<OracleAuthenticationResult>("/api/v1/admin/integration-authentication-test", {}).then(result => setAuthenticationTest(result)).catch(() => setAuthenticationTest({ credentials_configured: integration.credentials_configured, validated: false, result: "request_error", http_status: null, auth_mode: authMode, detail: "The authentication test could not reach the BSS API. See the connection status for Oracle host connectivity." })).finally(() => setTestingAuthentication(false)); }}>{testingAuthentication ? "Testing Oracle authentication…" : "Test Oracle authentication"}</button>
      {testingAuthentication && <p role="status" className="form-hint">Checking stored credentials against Oracle metadata…</p>}
      {authenticationTest && <div className={`oracle-connectivity-result ${authenticationTest.validated ? "success-notice" : "inline-error"}`} role={authenticationTest.validated ? "status" : "alert"} aria-live="polite">
        <strong>{authenticationResultTitle(authenticationTest.result)}</strong>
        <span>Result: {authenticationTest.result.replaceAll("_", " ")}</span>
        <span>HTTP status: {authenticationTest.http_status ?? "No response"}</span>
        {authenticationTest.duration_ms !== undefined && <span>Duration: {authenticationTest.duration_ms} ms</span>}
        <span>{authenticationTest.detail}</span>
      </div>}
      <p className="form-notice" role="status">Oracle delivery is {integration.oracle_enabled ? "enabled" : "disabled"}. Authentication validation never changes the delivery setting.</p>
      </> : integrationError ? <div className="inline-error" role="alert">{integrationError}</div> : <p className="form-hint">Loading integration settings…</p>}
    </section>
  </div>;
}
