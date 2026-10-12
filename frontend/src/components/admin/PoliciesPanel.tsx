import { useEffect, useState } from "react";
import { api } from "../../api";

type Mode = "DISABLED" | "SAME_TERMINAL" | "SAME_WORK_CELL" | "INHERIT";
type Terminal = {code:string; name:string; mode:Mode; effective_mode:Mode; work_cell:string|null};
type Policy = {global_mode:Mode; terminals:Terminal[]};
const modes: {value:Mode; label:string}[] = [
  {value:"DISABLED",label:"Disabled — any terminal"},
  {value:"SAME_TERMINAL",label:"Same Terminal — original entry terminal"},
  {value:"SAME_WORK_CELL",label:"Same Work Cell — matching configured cell"},
];

export function PoliciesPanel() {
  const [data,setData] = useState<Policy|null>(null);
  const [error,setError] = useState("");
  const [notice,setNotice] = useState("");
  const load = async () => { try { setData(await api.get<Policy>("/api/v1/admin/policies/same-terminal-exit")); setError(""); } catch(e) { setError((e as Error).message); } };
  useEffect(()=>{void load();},[]);
  const save = async (url:string,mode:Mode) => {
    try { await api.put(url,{mode}); setNotice("Policy saved"); await load(); }
    catch(e) { setError((e as Error).message); }
  };
  return <div className="admin-card" style={{padding:24}}>
    <h2>Same Terminal Exit</h2>
    <p>Restrict the exit terminal relative to the latest recorded entry. Default: Disabled.</p>
    {error && <div className="inline-error" role="alert">{error}</div>}
    {notice && <div className="success-notice" role="status">{notice}</div>}
    {data && <><label htmlFor="policy-global">Global default</label>
      <select id="policy-global" value={data.global_mode} onChange={e=>void save("/api/v1/admin/policies/same-terminal-exit",e.target.value as Mode)}>
        {modes.map(m=><option key={m.value} value={m.value}>{m.label}</option>)}
      </select>
      <h3>Terminal overrides</h3>
      {data.terminals.map(t=><div key={t.code} style={{display:"flex",gap:16,alignItems:"center",margin:"12px 0",flexWrap:"wrap"}}>
        <div style={{minWidth:180}}><strong>{t.name}</strong><div>{t.code} · Cell: {t.work_cell || "Not configured"}</div></div>
        <select aria-label={`Exit policy for ${t.code}`} value={t.mode} onChange={e=>void save(`/api/v1/admin/policies/same-terminal-exit/terminals/${encodeURIComponent(t.code)}`,e.target.value as Mode)}>
          <option value="INHERIT">Inherit global ({data.global_mode})</option>
          {modes.map(m=><option key={m.value} value={m.value}>{m.label}</option>)}
        </select>
        <small>Effective: {t.effective_mode}</small>
      </div>)}
      <p>Same Work Cell requires an exact work_cell value in both terminals' Oracle attributes. Missing or different values block the exit.</p>
    </>}
  </div>;
}
