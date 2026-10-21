import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api";
import type { AdminAction, AdminTerminal } from "../../types";

type Config = {
  factory_code: string; enabled: boolean; badge_source: "OPEN" | "EXTERNAL";
  dedup_enabled: boolean; dedup_seconds: number; auto_exit_action_code: string | null;
};
type Presence = { factory_code: string; inside: string[]; recent_events: Array<{id: string; badge: string; direction: string; at: string; auto_cell_exit_event_id: string | null}> };
type Role = "CELL" | "PERIMETER_ENTER" | "PERIMETER_EXIT" | "PERIMETER_BOTH";
export function PerimeterPanel({ terminals, actions, onTerminalsChanged }: {terminals: AdminTerminal[]; actions: AdminAction[]; onTerminalsChanged?: () => Promise<void>}) {
  const [terminalRows, setTerminalRows] = useState(terminals);
  useEffect(() => { setTerminalRows(terminals); }, [terminals]);
  const exitActions = actions.filter(a => a.active && a.state_effect === "EXIT" && !a.requires_subaction);
  const [factory, setFactory] = useState(() => {
    const query = new URLSearchParams(window.location.search).get("factory");
    if (query) return query;
    try { return localStorage.getItem("bss-perimeter-factory") || "DEFAULT"; }
    catch { return "DEFAULT"; }
  });
  useEffect(() => {
    if (!factory) return;
    try { localStorage.setItem("bss-perimeter-factory", factory); }
    catch { /* Storage can be disabled by browser policy. */ }
  }, [factory]);
  const requestVersion = useRef(0);
  const changeFactory = (value: string) => {
    // Invalidate pending responses before rendering the next factory.
    requestVersion.current += 1;
    setConfig(null); setPresence(null);
    setFactory(value);
    try { if (value) localStorage.setItem("bss-perimeter-factory", value); }
    catch { /* URL selection still works when browser storage is unavailable. */ }
    const url = new URL(window.location.href);
    if (value) url.searchParams.set("factory", value);
    else url.searchParams.delete("factory");
    window.history.replaceState({}, "", url);
  };
  const [config, setConfig] = useState<Config | null>(null);
  const [presence, setPresence] = useState<Presence | null>(null);
  const [roles, setRoles] = useState<Record<string, Role>>({});
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    if (!factory) return;
    const version = ++requestVersion.current;
    const [settings, state, currentTerminals] = await Promise.all([
      api.get<Config>(`/api/v1/admin/perimeter/${encodeURIComponent(factory)}`),
      api.get<Presence>(`/api/v1/admin/perimeter/${encodeURIComponent(factory)}/presence`),
      api.get<AdminTerminal[]>("/api/v1/admin/terminals")
    ]);
    if (version !== requestVersion.current) return;
    setConfig(settings); setPresence(state);
    if (Array.isArray(currentTerminals)) setTerminalRows(currentTerminals);
  }, [factory]);
  useEffect(() => {
    setNotice(""); setError(""); setConfig(null); setPresence(null);
    void load().catch(e => setError((e as Error).message));
    return () => { requestVersion.current += 1; };
  }, [load]);
  const save = async () => {
    if (!config) return;
    setBusy(true); setError(""); setNotice("");
    try {
      if (config.enabled && !exitActions.some(a => a.code === config.auto_exit_action_code)) { setError("Select an existing active EXIT action without subactions."); return; }
      await api.put(`/api/v1/admin/perimeter/${encodeURIComponent(factory)}`, config);
      await load(); setError(""); setNotice("Factory perimeter configuration saved.");
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const saveRole = async (code: string) => {
    setBusy(true); setError(""); setNotice("");
    try {
      const saved = await api.put<{code: string; factory_code: string; role: Role}>(`/api/v1/admin/perimeter/terminals/${encodeURIComponent(code)}/role`, {role: roles[code] ?? terminalRows.find(t => t.code === code)?.terminal_role ?? "CELL", factory_code: factory});
      setTerminalRows(rows => rows.map(t => t.code === saved.code ? {...t, factory_code: saved.factory_code, terminal_role: saved.role} : t));
      setRoles(previous => { const next = {...previous}; delete next[code]; return next; });
      await onTerminalsChanged?.();
      setError(""); setNotice(`Terminal ${code} updated.`);
    } catch(e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  return <div className="admin-stack perimeter-panel">
    {error && <div className="inline-error" role="alert">{error}</div>}
    {notice && !error && <div className="success-notice" role="status">{notice}</div>}
    <section className="admin-card">
      <div className="section-heading"><div><h3>Factory settings</h3><p>Configure UID presence and repeated scans for each factory.</p></div>
        {config && <span className={`resource-status ${config.enabled ? "is-active" : "is-inactive"}`}><span />{config.enabled ? "Enabled" : "Disabled"}</span>}
      </div>
      <div className="form-grid">
        <label>Factory code<input disabled={busy} value={factory} maxLength={64} onChange={e => changeFactory(e.target.value.toUpperCase().replace(/[^A-Z0-9_-]/g, ""))} /></label>
        {config && <label>Badge validation<select value={config.badge_source} onChange={e => setConfig({...config, badge_source:e.target.value as Config["badge_source"]})}><option value="OPEN">OPEN (any scanned UID)</option><option value="EXTERNAL" disabled={factory !== "ARGANDA"}>EXTERNAL (Arganda SECURITY_DB, 12h)</option></select></label>}
      </div>
      {config && <>
        <div className="perimeter-switches">
          <label className="switch-control"><input type="checkbox" checked={config.enabled} disabled={busy} onChange={e => setConfig({...config, enabled:e.target.checked})} /><span className="switch-track" aria-hidden="true" />Require factory entry before cell entry</label>
          <label className="switch-control"><input type="checkbox" checked={config.dedup_enabled} disabled={busy} onChange={e => setConfig({...config, dedup_enabled:e.target.checked})} /><span className="switch-track" aria-hidden="true" />Ignore repeated scans</label>
        </div>
        <div className="form-grid">
          <label>Scan cooldown (seconds)<input type="number" min="0" max="300" value={config.dedup_seconds} onChange={e => setConfig({...config, dedup_seconds:Number(e.target.value)})} /></label>
          <label>Automatic cell EXIT action<select aria-label="Automatic cell EXIT action" value={config.auto_exit_action_code ?? ""} onChange={e => { setConfig({...config, auto_exit_action_code:e.target.value || null}); setNotice(""); setError(""); }}><option value="">Select an existing EXIT action</option>{config.auto_exit_action_code && !exitActions.some(action => action.code === config.auto_exit_action_code) && <option value={config.auto_exit_action_code} disabled>{config.auto_exit_action_code} (unavailable)</option>}{exitActions.map(action => <option key={action.code} value={action.code}>{action.label} · {action.code}{action.show_on_terminal === false ? " (hidden)" : ""}</option>)}</select>{exitActions.length === 0 && <small>No eligible EXIT actions. Create an active EXIT action without subactions in Actions first.</small>}{config.auto_exit_action_code && !exitActions.some(action => action.code === config.auto_exit_action_code) && <small>Saved action is unavailable; select an active EXIT action before saving.</small>}</label>
        </div>
        <div className="form-actions"><button className="primary" disabled={busy || !factory} onClick={() => void save()}>Save factory settings</button></div>
      </>}
    </section>
    <section className="admin-card">
      <div className="section-heading"><div><h3>Terminal roles</h3><p>The saved factory and role are shown below each terminal. Choose a role and save to assign it to the selected factory.</p></div></div>
      <div className="perimeter-terminal-list">{terminalRows.map(t => <div key={t.code} className="perimeter-terminal-row">
        <div className="perimeter-terminal-name"><strong>{t.name}</strong><div className="cell-secondary">{t.code}<br />Saved factory: <strong>{t.factory_code ?? "DEFAULT"}</strong><br />Saved role: {t.terminal_role === "CELL" ? "Cell" : t.terminal_role === "PERIMETER_ENTER" ? "Factory entrance" : t.terminal_role === "PERIMETER_EXIT" ? "Factory exit" : "Factory entrance / exit"}</div></div>
        <label className="perimeter-role-control"><span className="field-label">Role to save</span><select aria-label={`Role for ${t.code}`} value={roles[t.code] ?? t.terminal_role ?? "CELL"} onChange={e => setRoles({...roles, [t.code]:e.target.value as Role})}>
          <option value="CELL">Cell</option><option value="PERIMETER_ENTER">Factory entrance</option>
          <option value="PERIMETER_EXIT">Factory exit</option><option value="PERIMETER_BOTH">Factory entrance / exit</option>
        </select></label>
        <button className="secondary" disabled={busy || !factory || ((t.factory_code ?? "DEFAULT") === factory && (roles[t.code] ?? t.terminal_role ?? "CELL") === t.terminal_role)} onClick={() => void saveRole(t.code)}>{(t.factory_code ?? "DEFAULT") !== factory ? `Assign to ${factory}` : (roles[t.code] ?? t.terminal_role) !== t.terminal_role ? "Save role" : "Assignment saved"}</button>
      </div>)}</div>
      {!terminalRows.length && <div className="empty-state">No terminals configured.</div>}
    </section>
    {config?.badge_source === "EXTERNAL" ? <section className="admin-card">
      <div className="section-heading"><div><h3>Factory presence</h3><p>Presence is authoritative in Arganda SECURITY_DB. This local BSS view shows historical local gate movements only.</p></div></div>
      <div className="empty-state">External presence is not available in this local movement list.</div>
    </section> : <section className="admin-card">
      <div className="section-heading"><div><h3>Factory presence</h3><p>Cards currently inside the selected factory.</p></div>
        <button className="secondary" disabled={busy} onClick={() => void load().catch(e => setError((e as Error).message))}>Refresh presence</button>
      </div>
      <div className="list-stats"><strong>{presence?.inside.length ?? 0}</strong><span>cards inside factory</span></div>
      {presence?.inside.length ? <div className="action-tags perimeter-presence">{presence.inside.map(badge => <span key={badge}>{badge}</span>)}</div> : <div className="empty-state">No cards currently inside this factory.</div>}
    </section>}
    {config?.badge_source !== "EXTERNAL" && <section className="admin-card resource-list">
      <div className="list-toolbar perimeter-audit-heading"><div className="section-heading"><div><h3>Recent perimeter movements</h3><p>Factory entry, exit and automatic cell exit history.</p></div></div></div>
      {presence?.recent_events.length ? <div className="table-wrap"><table><thead><tr><th>UID</th><th>Direction</th><th>Time</th><th>Auto cell exit</th></tr></thead>
        <tbody>{presence.recent_events.map(e => <tr key={e.id}><td><strong>{e.badge}</strong></td><td><span className="status">{e.direction}</span></td><td>{new Date(e.at).toLocaleString()}</td><td><code>{e.auto_cell_exit_event_id ?? "—"}</code></td></tr>)}</tbody></table></div> : <div className="empty-state">No perimeter movements recorded.</div>}
    </section>}
  </div>;
}
