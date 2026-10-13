import { useEffect, useRef, useState } from "react";
import { api } from "../../api";

import { exitPolicyModes } from "./exitPolicyOptions";
import type { ExitPolicyMode } from "./exitPolicyOptions";

type Policy = {global_mode:ExitPolicyMode};

export function PoliciesPanel() {
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
    try { await api.put(url,payload); await load(); setNotice("Policy settings saved."); }
    catch(e) { setError((e as Error).message); }
    finally { saving.current=false; setBusy(false); }
  };
  return <section className="admin-card policies-panel">
    <h2>Same Terminal Exit</h2>
    <p>Restrict the exit terminal relative to the latest recorded entry. Default: Disabled.</p>
    {error && <div className="inline-error" role="alert">{error}</div>}
    {notice && <div className="success-notice" role="status">{notice}</div>}
    {!data && !error && <p role="status">Loading policies…</p>}
    {data && <fieldset disabled={busy} className="policy-settings"><label htmlFor="policy-global">Global default</label>
      <select id="policy-global" value={data.global_mode} onChange={e=>void save("/api/v1/admin/policies/same-terminal-exit",{mode:e.target.value})}>
        {exitPolicyModes.map(m=><option key={m.value} value={m.value}>{m.label}</option>)}
      </select>
      <p>Individual policies and work cells are configured in <a href="/admin/terminals">Terminals</a> → Edit → Exit policy. Terminals inherit this global default unless an override is selected.</p>
      <p>Rejected exits are not recorded or queued for Oracle.</p>
    </fieldset>}
  </section>;
}
