import { useState } from "react";
import { api } from "../../api";
import type { AdminAction, AdminTerminal } from "../../types";
import { ActionEditor } from "./ActionEditor";

function actionPayload(action: AdminAction, active: boolean) {
  return {
    label: action.label,
    supplier_device_event: action.supplier_device_event,
    state_effect: action.state_effect,
    oracle_attributes: action.oracle_attributes,
    display_order: action.display_order,
    requires_subaction: action.requires_subaction,
    parent_action_code: action.parent_action_code ?? null,
    visual_key: action.visual_key ?? null,
    show_on_terminal: action.show_on_terminal,
    active,
  };
}

export function ActionList({ actions, terminals, onChanged }: { actions: AdminAction[]; terminals: AdminTerminal[]; onChanged: (message: string) => void; }) {
  const [search, setSearch] = useState("");
  const [effect, setEffect] = useState("");
  const [editor, setEditor] = useState<{action: AdminAction | null} | null>(null);
  const [busyCode, setBusyCode] = useState("");
  const [error, setError] = useState("");

  const filtered = actions.filter(action => `${action.code} ${action.label} ${action.supplier_device_event} ${action.parent_action_code ?? ""}`.toLowerCase().includes(search.toLowerCase()) && (!effect || action.state_effect === effect));

  const deactivate = async (action: AdminAction) => {
    if (!window.confirm(`Deactivate ${action.label}? The action will remain available in historical records.`)) return;
    setBusyCode(action.code);
    setError("");
    try {
      await api.put<AdminAction>(`/api/v1/admin/actions/${encodeURIComponent(action.code)}`, actionPayload(action, false));
      onChanged(`Action ${action.code} deactivated successfully.`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyCode("");
    }
  };

  const remove = async (action: AdminAction) => {
    if (!window.confirm(`Delete ${action.label}? This is only allowed when the action has no recorded history or dependencies.`)) return;
    setBusyCode(action.code);
    setError("");
    try {
      await api.delete<{detail: string}>(`/api/v1/admin/actions/${encodeURIComponent(action.code)}`);
      onChanged(`Action ${action.code} deleted successfully.`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyCode("");
    }
  };

  return <>
    <div className="page-actions"><div className="list-stats"><strong>{actions.length}</strong> actions <span className="stat-separator" />{actions.filter(action => action.active).length} active</div><button className="primary" onClick={() => setEditor({action:null})}><span aria-hidden="true">＋</span> New action</button></div>
    {error && <div className="inline-error" role="alert">{error}</div>}
    <section className="admin-card resource-list" aria-label="Action list"><div className="list-toolbar"><label className="search-field"><span className="sr-only">Search actions</span><input placeholder="Search by label, code, parent or Oracle event" value={search} onChange={event => setSearch(event.target.value)} /></label><label><span className="sr-only">Filter by effect</span><select value={effect} onChange={event => setEffect(event.target.value)}><option value="">All effects</option><option value="ENTER">Entry · ENTER</option><option value="EXIT">Exit · EXIT</option></select></label><span className="subtle">{filtered.length} results</span></div>
      <div className="table-wrap"><table><thead><tr><th>Action</th><th>Effect / hierarchy</th><th>Oracle supplier event</th><th>Used by</th><th>Order</th><th>Status</th><th /></tr></thead><tbody>{filtered.map(action => <tr key={action.code}>
        <td><strong>{action.parent_action_code ? "↳ " : ""}{action.label}</strong><div className="cell-secondary"><code>{action.code}</code></div></td>
        <td><span className={`effect-tag effect-${action.state_effect.toLowerCase()}`}>{action.state_effect === "ENTER" ? "↗ Entry" : "↙ Exit"}</span><div className="cell-secondary">{action.parent_action_code ? `Sub-action of ${action.parent_action_code}` : action.requires_subaction ? `${action.subaction_codes.length} sub-actions` : "Top level"}</div></td>
        <td><code>{action.supplier_device_event}</code></td><td>{terminals.filter(terminal => terminal.action_codes.includes(action.code)).length} terminals</td><td>{action.display_order}</td><td><span className={`resource-status ${action.active ? "is-active" : "is-inactive"}`}><span />{action.active ? "Active" : "Inactive"}</span>{action.active && !action.show_on_terminal && <div className="cell-secondary">Hidden from terminal</div>}</td><td><div className="row-actions"><button className="text-button" disabled={busyCode === action.code} onClick={() => setEditor({action})}>Edit</button>{action.active && <button className="text-button" disabled={busyCode === action.code} onClick={() => void deactivate(action)}>Deactivate</button>}<button className="text-button" disabled={busyCode === action.code} onClick={() => void remove(action)}>Delete</button></div></td>
      </tr>)}</tbody></table></div>
    </section>
    {editor && <ActionEditor action={editor.action} actions={actions} terminals={terminals} onClose={() => setEditor(null)} onSaved={action => { setEditor(null); onChanged(`Action ${action.code} ${editor.action ? "updated" : "created"} successfully.`); }} />}
  </>;
}
