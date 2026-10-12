import { languageOptions, useLanguage } from "../../i18n";

export function SettingsPanel() {
  const { language, setLanguage, t } = useLanguage();
  return <div className="admin-stack">
    <section className="admin-card">
      <div className="section-heading"><div><h3>{t("language")}</h3><p>{t("languageHelp")}</p></div></div>
      <div className="form-grid"><label>{t("language")}<select value={language} onChange={event => setLanguage(event.target.value as typeof language)}>{languageOptions.map(option => <option value={option.value} key={option.value}>{option.label}</option>)}</select></label></div>
      <p className="form-hint">{t("languageSaved")}</p>
    </section>
  </div>;
}
