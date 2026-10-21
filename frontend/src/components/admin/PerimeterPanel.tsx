import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api";
import type { AdminAction, AdminTerminal } from "../../types";
import { useLanguage } from "../../i18n";

type Config = {
  factory_code: string; enabled: boolean; badge_source: "OPEN" | "EXTERNAL";
  dedup_enabled: boolean; dedup_seconds: number; auto_exit_action_code: string | null;
};
type Presence = { factory_code: string; inside: string[]; recent_events: Array<{id: string; badge: string; direction: string; at: string; auto_cell_exit_event_id: string | null}> };
type Role = "CELL" | "PERIMETER_ENTER" | "PERIMETER_EXIT" | "PERIMETER_BOTH";
export function PerimeterPanel({ terminals, actions, onTerminalsChanged }: {terminals: AdminTerminal[]; actions: AdminAction[]; onTerminalsChanged?: () => Promise<void>}) {
  const { t: tr, language } = useLanguage();
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
      if (config.enabled && !exitActions.some(a => a.code === config.auto_exit_action_code)) { setError(tr("selectEligibleExitError")); return; }
      await api.put(`/api/v1/admin/perimeter/${encodeURIComponent(factory)}`, config);
      await load(); setError(""); setNotice(tr("perimeterSaved"));
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
      setError(""); setNotice(`${tr("terminal")} ${code} ${tr("factoryRoleUpdated")}`);
    } catch(e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  return <div className="admin-stack perimeter-panel">
    {error && <div className="inline-error" role="alert">{error}</div>}
    {notice && !error && <div className="success-notice" role="status">{notice}</div>}
    <section className="admin-card">
      <div className="section-heading"><div><h3>{tr("factorySettings")}</h3><p>{tr("factorySettingsHelp")}</p></div>
        {config && <span className={`resource-status ${config.enabled ? "is-active" : "is-inactive"}`}><span />{config.enabled ? tr("enabled") : tr("disabled")}</span>}
      </div>
      <div className="form-grid">
        <label>{tr("factoryCode")}<input disabled={busy} value={factory} maxLength={64} onChange={e => changeFactory(e.target.value.toUpperCase().replace(/[^A-Z0-9_-]/g, ""))} /></label>
        {config && <label>{tr("badgeValidation")}<select value={config.badge_source} onChange={e => setConfig({...config, badge_source:e.target.value as Config["badge_source"]})}><option value="OPEN">{tr("openAnyUid")}</option><option value="EXTERNAL" disabled>{tr("externalFuture")}</option></select></label>}
      </div>
      {config && <>
        <div className="perimeter-switches">
          <label className="switch-control"><input type="checkbox" checked={config.enabled} disabled={busy} onChange={e => setConfig({...config, enabled:e.target.checked})} /><span className="switch-track" aria-hidden="true" />{tr("requireFactoryEntry")}</label>
          <label className="switch-control"><input type="checkbox" checked={config.dedup_enabled} disabled={busy} onChange={e => setConfig({...config, dedup_enabled:e.target.checked})} /><span className="switch-track" aria-hidden="true" />{tr("ignoreRepeatedScans")}</label>
        </div>
        <div className="form-grid">
          <label>{tr("scanCooldown")}<input type="number" min="0" max="300" value={config.dedup_seconds} onChange={e => setConfig({...config, dedup_seconds:Number(e.target.value)})} /></label>
          <label>{tr("autoExitAction")}<select aria-label={tr("autoExitAction")} value={config.auto_exit_action_code ?? ""} onChange={e => { setConfig({...config, auto_exit_action_code:e.target.value || null}); setNotice(""); setError(""); }}><option value="">{tr("selectExistingExit")}</option>{config.auto_exit_action_code && !exitActions.some(action => action.code === config.auto_exit_action_code) && <option value={config.auto_exit_action_code} disabled>{config.auto_exit_action_code} ({tr("unavailable")})</option>}{exitActions.map(action => <option key={action.code} value={action.code}>{action.label} · {action.code}{action.show_on_terminal === false ? ` (${tr("hidden")})` : ""}</option>)}</select>{exitActions.length === 0 && <small>{tr("noEligibleExit")}</small>}{config.auto_exit_action_code && !exitActions.some(action => action.code === config.auto_exit_action_code) && <small>{tr("savedActionUnavailable")}</small>}</label>
        </div>
        <div className="form-actions"><button className="primary" disabled={busy || !factory} onClick={() => void save()}>{tr("saveFactorySettings")}</button></div>
      </>}
    </section>
    <section className="admin-card">
      <div className="section-heading"><div><h3>{tr("terminalRoles")}</h3><p>{tr("terminalRolesHelp")}</p></div></div>
      <div className="perimeter-terminal-list">{terminalRows.map(terminal => <div key={terminal.code} className="perimeter-terminal-row">
        <div className="perimeter-terminal-name"><strong>{terminal.name}</strong><div className="cell-secondary">{terminal.code}<br />{tr("savedFactory")}: <strong>{terminal.factory_code ?? "DEFAULT"}</strong><br />{tr("savedRole")}: {terminal.terminal_role === "CELL" ? tr("cell") : terminal.terminal_role === "PERIMETER_ENTER" ? tr("factoryEntrance") : terminal.terminal_role === "PERIMETER_EXIT" ? tr("factoryExit") : tr("factoryEntranceExit")}</div></div>
        <label className="perimeter-role-control"><span className="field-label">{tr("roleToSave")}</span><select aria-label={`${tr("roleToSave")} ${terminal.code}`} value={roles[terminal.code] ?? terminal.terminal_role ?? "CELL"} onChange={e => setRoles({...roles, [terminal.code]:e.target.value as Role})}>
          <option value="CELL">{tr("cell")}</option><option value="PERIMETER_ENTER">{tr("factoryEntrance")}</option>
          <option value="PERIMETER_EXIT">{tr("factoryExit")}</option><option value="PERIMETER_BOTH">{tr("factoryEntranceExit")}</option>
        </select></label>
        <button className="secondary" disabled={busy || !factory || ((terminal.factory_code ?? "DEFAULT") === factory && (roles[terminal.code] ?? terminal.terminal_role ?? "CELL") === terminal.terminal_role)} onClick={() => void saveRole(terminal.code)}>{(terminal.factory_code ?? "DEFAULT") !== factory ? `${tr("assignTo")} ${factory}` : (roles[terminal.code] ?? terminal.terminal_role) !== terminal.terminal_role ? tr("saveRole") : tr("assignmentSaved")}</button>
      </div>)}</div>
      {!terminalRows.length && <div className="empty-state">{tr("noTerminalsConfigured")}</div>}
    </section>
    <section className="admin-card">
      <div className="section-heading"><div><h3>{tr("factoryPresence")}</h3><p>{tr("cardsInsideSelected")}</p></div>
        <button className="secondary" disabled={busy} onClick={() => void load().catch(e => setError((e as Error).message))}>{tr("refreshPresence")}</button>
      </div>
      <div className="list-stats"><strong>{presence?.inside.length ?? 0}</strong><span>{tr("cardsInsideFactory")}</span></div>
      {presence?.inside.length ? <div className="action-tags perimeter-presence">{presence.inside.map(badge => <span key={badge}>{badge}</span>)}</div> : <div className="empty-state">{tr("noCardsInside")}</div>}
    </section>
    <section className="admin-card resource-list">
      <div className="list-toolbar perimeter-audit-heading"><div className="section-heading"><div><h3>{tr("recentMovements")}</h3><p>{tr("perimeterHistoryHelp")}</p></div></div></div>
      {presence?.recent_events.length ? <div className="table-wrap"><table><thead><tr><th>{tr("uid")}</th><th>{tr("direction")}</th><th>{tr("time")}</th><th>{tr("autoCellExit")}</th></tr></thead>
        <tbody>{presence.recent_events.map(e => <tr key={e.id}><td><strong>{e.badge}</strong></td><td><span className="status">{e.direction}</span></td><td>{new Date(e.at).toLocaleString(language)}</td><td><code>{e.auto_cell_exit_event_id ?? "—"}</code></td></tr>)}</tbody></table></div> : <div className="empty-state">{tr("noMovements")}</div>}
    </section>
  </div>;
}
