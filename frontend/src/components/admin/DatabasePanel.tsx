import { useEffect, useState } from "react";
import { api } from "../../api";

interface DatabaseStatus {
  backend: string;
  host?: string | null;
  port?: number | null;
  database?: string | null;
  username?: string | null;
  source: "local-compose" | "external";
  connection_test_enabled: boolean;
}

interface TestResult {
  success: boolean;
  backend: string;
  host: string;
  port: number;
  database: string;
  latency_ms: number;
}

export function DatabasePanel() {
  const [status, setStatus] = useState<DatabaseStatus | null>(null);
  const [form, setForm] = useState({ host: "", port: "5432", database: "bss_timecollection", username: "", password: "", sslmode: "prefer" });
  const [result, setResult] = useState<TestResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get<DatabaseStatus>("/api/v1/admin/database").then(setStatus).catch(err => setError((err as Error).message));
  }, []);

  const test = async () => {
    setBusy(true); setError(""); setResult(null);
    try {
      const value = await api.post<TestResult>("/api/v1/admin/database/test", {
        ...form,
        port: Number(form.port),
      });
      setResult(value);
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  };

  return <div className="admin-stack">
    <section className="admin-card">
      <div className="section-heading"><div><h3>Current primary database</h3><p>The password is never exposed through Administration.</p></div></div>
      {status ? <div className="detail-grid">
        <div><span>Mode</span><strong>{status.source === "local-compose" ? "Local Docker PostgreSQL" : "External database"}</strong></div>
        <div><span>Engine</span><strong>{status.backend}</strong></div>
        <div><span>Host</span><strong>{status.host || "—"}</strong></div>
        <div><span>Port</span><strong>{status.port || "—"}</strong></div>
        <div><span>Database</span><strong>{status.database || "—"}</strong></div>
        <div><span>User</span><strong>{status.username || "—"}</strong></div>
      </div> : <div className="loading-state">Loading database status…</div>}
    </section>

    <section className="admin-card">
      <div className="section-heading"><div><h3>External PostgreSQL connection</h3><p>Validate a managed external database before changing the deployment configuration. Credentials are used only for this test and are not stored by the application.</p></div></div>
      {status && !status.connection_test_enabled && <div className="inline-error">Connection testing is disabled on this server. Set <code>DATABASE_ADMIN_TEST_ENABLED=true</code> only on a trusted administration network.</div>}
      <div className="form-grid">
        <label>Host<input value={form.host} onChange={event => setForm({...form, host:event.target.value})} placeholder="postgres.company.local" /></label>
        <label>Port<input value={form.port} onChange={event => setForm({...form, port:event.target.value})} inputMode="numeric" /></label>
        <label>Database<input value={form.database} onChange={event => setForm({...form, database:event.target.value})} /></label>
        <label>Username<input value={form.username} onChange={event => setForm({...form, username:event.target.value})} /></label>
        <label>Password<input type="password" autoComplete="new-password" value={form.password} onChange={event => setForm({...form, password:event.target.value})} /></label>
        <label>SSL mode<select value={form.sslmode} onChange={event => setForm({...form, sslmode:event.target.value})}><option value="prefer">Prefer</option><option value="require">Require</option><option value="verify-ca">Verify CA</option><option value="verify-full">Verify full</option><option value="disable">Disable</option></select></label>
      </div>
      <div className="page-actions"><button className="primary" disabled={busy || !form.host || !form.username || !form.password || !status?.connection_test_enabled} onClick={() => void test()}>{busy ? "Testing…" : "Test connection"}</button></div>
      {result && <div className="success-notice" role="status"><span aria-hidden="true">✓</span>External PostgreSQL connection validated · {result.host}:{result.port}/{result.database} · {result.latency_ms} ms</div>}
      {error && <div className="inline-error" role="alert">{error}</div>}
    </section>

    <section className="admin-card">
      <h3>Activation</h3>
      <p>Changing the primary database is intentionally not performed live from this screen. After validation, set the server <code>DATABASE_URL</code>, run Alembic migrations against the target database and restart/redeploy the API and worker. This keeps credentials outside the application database and makes the change auditable and reversible.</p>
      <p className="subtle">Microsoft SQL Server is not enabled yet. The current production data model and migrations are validated for PostgreSQL.</p>
    </section>
  </div>;
}
