import { useEffect, useRef, useState } from "react";
import { api } from "../../api";

import { exitPolicyModes } from "./exitPolicyOptions";
import type { ExitPolicyMode } from "./exitPolicyOptions";
import { useLanguage } from "../../i18n";

type Policy = {global_mode:ExitPolicyMode};

export function PoliciesPanel() {
  const { t, language } = useLanguage();
  const [data,setData] = useState<Policy|null>(null);
  const [error,setError] = useState("");
  const [notice,setNotice] = useState("");
  const [busy,setBusy] = useState(false);
  const saving = useRef(false);
  const load = async () => setData(await api.get<Policy>("/api/v1/admin/policies/same-terminal-exit"));
  useEffect(()=>{void load().catch(e=>setError((e as Error).message));},[]);
  const save = async (url:string,payload:unknown) => {
    if (saving.current) return;
    saving.current=true; setBusy(true); setError(""); setNotice("");
    try { await api.put(url,payload); await load(); setNotice(t("policySaved")); }
    catch(e) { setError((e as Error).message); }
    finally { saving.current=false; setBusy(false); }
  };
  return <section className="admin-card policies-panel">
    <h2>{t("sameTerminalExit")}</h2>
    <p>{t("sameTerminalExitHelp")}</p>
    {error && <div className="inline-error" role="alert">{error}</div>}
    {notice && <div className="success-notice" role="status">{notice}</div>}
    {!data && !error && <p role="status">{t("loadingPolicies")}</p>}
    {data && <fieldset disabled={busy} className="policy-settings"><label htmlFor="policy-global">{t("globalDefault")}</label>
      <select id="policy-global" value={data.global_mode} onChange={e=>void save("/api/v1/admin/policies/same-terminal-exit",{mode:e.target.value})}>
        {exitPolicyModes(language).map(m=><option key={m.value} value={m.value}>{m.label}</option>)}
      </select>
      <p>{t("policyHelp")} <a href="/admin/terminals">{t("terminals")}</a> → {t("editExitPolicy")}</p>
      <p>{t("rejectedExitsHelp")}</p>
    </fieldset>}
  </section>;
}
