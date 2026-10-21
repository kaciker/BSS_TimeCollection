import { useEffect, useState } from "react";
import { api } from "../../api";
import { useLanguage } from "../../i18n";

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
  const { t } = useLanguage();
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
      <div className="section-heading"><div><h3>{t("currentDatabase")}</h3><p>{t("passwordNeverExposed")}</p></div></div>
      {status ? <div className="detail-grid database-detail-grid">
        <div><span>{t("mode")}</span><strong>{status.source === "local-compose" ? t("localPostgres") : t("externalDatabase")}</strong></div>
        <div><span>{t("engine")}</span><strong>{status.backend}</strong></div>
        <div><span>{t("host")}</span><strong>{status.host || "—"}</strong></div>
        <div><span>{t("port")}</span><strong>{status.port || "—"}</strong></div>
        <div><span>{t("database")}</span><strong>{status.database || "—"}</strong></div>
        <div><span>{t("user")}</span><strong>{status.username || "—"}</strong></div>
      </div> : <div className="loading-state">{t("loadingDatabase")}</div>}
    </section>

    <section className="admin-card">
      <div className="section-heading"><div><h3>{t("externalPostgres")}</h3><p>{t("externalPostgresHelp")}</p></div></div>
      {status && !status.connection_test_enabled && <div className="info-notice">{t("testDisabled")} <code>DATABASE_ADMIN_TEST_ENABLED=true</code> {t("trustedNetworkOnly")}</div>}
      <div className="form-grid">
        <label>{t("host")}<input value={form.host} onChange={event => setForm({...form, host:event.target.value})} placeholder="postgres.company.local" /></label>
        <label>{t("port")}<input value={form.port} onChange={event => setForm({...form, port:event.target.value})} inputMode="numeric" /></label>
        <label>{t("database")}<input value={form.database} onChange={event => setForm({...form, database:event.target.value})} /></label>
        <label>{t("username")}<input value={form.username} onChange={event => setForm({...form, username:event.target.value})} /></label>
        <label>{t("password")}<input type="password" autoComplete="new-password" value={form.password} onChange={event => setForm({...form, password:event.target.value})} /></label>
        <label>{t("sslMode")}<select value={form.sslmode} onChange={event => setForm({...form, sslmode:event.target.value})}><option value="prefer">{t("prefer")}</option><option value="require">{t("require")}</option><option value="verify-ca">{t("verifyCa")}</option><option value="verify-full">{t("verifyFull")}</option><option value="disable">{t("sslDisable")}</option></select></label>
      </div>
      <div className="form-actions"><button className="primary" disabled={busy || !form.host || !form.username || !form.password || !status?.connection_test_enabled} onClick={() => void test()}>{busy ? t("testing") : t("testConnection")}</button></div>
      {result && <div className="success-notice" role="status"><span aria-hidden="true">✓</span>{t("externalDbValidated")} · {result.host}:{result.port}/{result.database} · {result.latency_ms} ms</div>}
      {error && <div className="inline-error" role="alert">{error}</div>}
    </section>

    <section className="admin-card">
      <div className="section-heading"><div><h3>{t("activation")}</h3><p>{t("activationHelp")}</p></div></div>
      <div className="info-notice">{t("databaseActivationHelp")} <code>DATABASE_URL</code> {t("databaseActivationEnd")}</div>
    </section>
  </div>;
}
