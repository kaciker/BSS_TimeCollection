import { useEffect, useState } from "react";
import { api } from "../../api";
import type { AdminAction, AdminTerminal } from "../../types";

type Config = {
  factory_code: string; enabled: boolean; badge_source: "OPEN" | "EXTERNAL";
  dedup_enabled: boolean; dedup_seconds: number; auto_exit_action_code: string | null;
};
type Presence = { factory_code: string; inside: string[]; recent_events: Array<{id: string; badge: string; direction: string; at: string; auto_cell_exit_event_id: string | null}> };
type Role = "CELL" | "PERIMETER_ENTER" | "PERIMETER_EXIT" | "PERIMETER_BOTH";
export function PerimeterPanel({ terminals, actions }: {terminals: AdminTerminal[]; actions: AdminAction[]}) {
  const exitActions = actions.filter(a => a.active && a.state_effect === "EXIT" && !a.requires_subaction);
  const [factory, setFactory] = useState("DEFAULT");
  const [config, setConfig] = useState<Config | null>(null);
  const [presence, setPresence] = useState<Presence | null>(null);
  const [roles, setRoles] = useState<Record<string, Role>>({});
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const load = async () => {
    const [settings, state] = await Promise.all([
      api.get<Config>(`/api/v1/admin/perimeter/${encodeURIComponent(factory)}`),
      api.get<Presence>(`/api/v1/admin/perimeter/${encodeURIComponent(factory)}/presence`)
    ]);
    setConfig(settings); setPresence(state);
  };
  useEffect(() => { setNotice(""); setError(""); void load().catch(e => setError((e as Error).message)); }, [factory]);
  const save = async () => {
    if (!config) return;
    setBusy(true); setError(""); setNotice(""); setNotice("");
    try {
      if (config.enabled && !exitActions.some(a => a.code === config.auto_exit_action_code)) { setError("Select an existing active EXIT action without subactions."); return; }
      await api.put(`/api/v1/admin/perimeter/${encodeURIComponent(factory)}`, config);
      await load(); setError(""); setNotice("Factory perimeter configuration saved.");
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const saveRole = async (code: string) => {
    setBusy(true); setError("");
    try {
      await api.put(`/api/v1/admin/perimeter/terminals/${encodeURIComponent(code)}/role`, {role: roles[code] ?? terminals.find(t => t.code === code)?.terminal_role ?? "CELL", factory_code: factory});
      setError(""); setNotice(`Terminal ${code} updated.`);
    } catch(e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  return <section className="admin-card policies-panel">
    <h2>Factory Perimeter</h2>
    <p>Optional UID-only presence control. Disabled by default. No employee identity data is stored.</p>
    <label>Factory code <input value={factory} maxLength={64} onChange={e => setFactory(e.target.value.toUpperCase().replace(/[^A-Z0-9_-]/g, ""))} /></label>
    {error && <div className="inline-error" role="alert">{error}</div>}
    {notice && <div className="success-notice" role="status">{notice}</div>}
    {config && <div className="policy-settings">
      <label><input type="checkbox" checked={config.enabled} onChange={e => setConfig({...config, enabled:e.target.checked})} /> Require factory entry before cell entry</label>
      <label>Badge validation <select value={config.badge_source} onChange={e => setConfig({...config, badge_source:e.target.value as Config["badge_source"]})}><option value="OPEN">OPEN (any scanned UID)</option><option value="EXTERNAL" disabled>EXTERNAL (future integration)</option></select></label>
      <label><input type="checkbox" checked={config.dedup_enabled} onChange={e => setConfig({...config, dedup_enabled:e.target.checked})} /> Ignore repeated scans</label>
      <label>Scan cooldown (seconds) <input type="number" min="0" max="300" value={config.dedup_seconds} onChange={e => setConfig({...config, dedup_seconds:Number(e.target.value)})} /></label>
      <label>Automatic cell EXIT action <select value={config.auto_exit_action_code ?? ""} onChange={e => { setConfig({...config, auto_exit_action_code:e.target.value || null}); setNotice(""); setError(""); }}><option value="">Select an existing EXIT action</option>{exitActions.map(action => <option key={action.code} value={action.code}>{action.label} · {action.code}{!action.show_on_terminal ? " (hidden)" : ""}</option>)}</select>{exitActions.length === 0 && <small>No eligible EXIT actions. Create an active EXIT action without subactions in Actions first.</small>}{config.auto_exit_action_code && !exitActions.some(action => action.code === config.auto_exit_action_code) && <small>Previously selected action is no longer eligible; select another.</small>}</label>
      <button className="primary" disabled={busy || !factory} onClick={() => void save()}>Save factory settings</button>
    </div>}
    <h3>Terminal roles</h3>
    <p>Assign perimeter readers to a factory. All existing terminals remain CELL unless changed.</p>
    {terminals.map(t => <div key={t.code} className="policy-settings"><strong>{t.name} ({t.code})</strong>
      <select aria-label={`Role for ${t.code}`} value={roles[t.code] ?? t.terminal_role ?? "CELL"} onChange={e => setRoles({...roles, [t.code]:e.target.value as Role})}>
        <option value="CELL">Cell</option><option value="PERIMETER_ENTER">Factory entrance</option>
        <option value="PERIMETER_EXIT">Factory exit</option><option value="PERIMETER_BOTH">Factory entrance / exit</option>
      </select>
      <button disabled={busy} onClick={() => void saveRole(t.code)}>Apply role to {factory}</button>
    </div>)}
    <h3>Factory presence</h3>
    <button disabled={busy} onClick={() => void load().catch(e => setError((e as Error).message))}>Refresh presence</button>
    <p>Inside factory: {presence?.inside.length ?? 0} cards</p>
    <p>{presence?.inside.join(", ") || "No active cards in the latest history window."}</p>
    <h3>Recent perimeter movements</h3>
    <table><thead><tr><th>UID</th><th>Direction</th><th>Time</th><th>Auto cell exit</th></tr></thead>
      <tbody>{presence?.recent_events.map(e => <tr key={e.id}><td>{e.badge}</td><td>{e.direction}</td><td>{new Date(e.at).toLocaleString()}</td><td>{e.auto_cell_exit_event_id ?? "—"}</td></tr>)}</tbody></table>
  </section>;
}
