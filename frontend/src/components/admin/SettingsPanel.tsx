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
      <div className="section-heading"><div><h3>{t("oracleIntegration")}</h3><p>{t("globalIntegrationHelp")}</p></div></div>
      {integration ? <div className="form-grid">
        <label>{t("reporterIdType")}<input value={integration.reporter_id_type} readOnly /><small>{t("globalBackendDefault")}</small></label>
        <label>{t("sourceId")}<input value={integration.oracle_source_id} readOnly /></label>
        <label>{t("oracleDelivery")}<input value={integration.oracle_enabled ? t("enabled") : t("disabled")} readOnly /></label>
      </div> : integrationError ? <div className="inline-error" role="alert">{integrationError}</div> : <p className="form-hint">{t("loadingIntegration")}</p>}
    </section>
  </div>;
}
