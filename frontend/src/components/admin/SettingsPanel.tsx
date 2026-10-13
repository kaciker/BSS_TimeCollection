import { useEffect, useState } from "react";
import { api } from "../../api";
import { languageOptions, useLanguage } from "../../i18n";

type IntegrationSettings = {
  oracle_enabled: boolean;
  oracle_source_id: string;
  reporter_id_type: string;
};

export function SettingsPanel() {
  const { language, setLanguage, t } = useLanguage();
  const [integration, setIntegration] = useState<IntegrationSettings | null>(null);
  const [integrationError, setIntegrationError] = useState("");

  useEffect(() => {
    let cancelled = false;
    void api.get<IntegrationSettings>("/api/v1/admin/integration-settings")
      .then(value => { if (!cancelled) setIntegration(value); })
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
      {integration ? <div className="form-grid">
        <label>Reporter ID type<input value={integration.reporter_id_type} readOnly /><small>Global backend setting. Default: BADGE.</small></label>
        <label>Source ID<input value={integration.oracle_source_id} readOnly /></label>
        <label>Oracle delivery<input value={integration.oracle_enabled ? "Enabled" : "Disabled"} readOnly /></label>
      </div> : integrationError ? <div className="inline-error" role="alert">{integrationError}</div> : <p className="form-hint">Loading integration settings…</p>}
    </section>
  </div>;
}
