import { useState } from "react";
import type { AdminAction, AdminTerminal } from "../../types";
import { ActionEditor } from "./ActionEditor";

export function ActionList({ actions, terminals, onChanged }: { actions: AdminAction[]; terminals: AdminTerminal[]; onChanged: (message: string) => void; }) {
  const [search, setSearch] = useState(""); const [effect, setEffect] = useState(""); const [editor, setEditor] = useState<{action: AdminAction | null} | null>(null);
  const filtered = actions.filter(action => `${action.code} ${action.label} ${action.supplier_device_event} ${action.parent_action_code ?? ""}`.toLowerCase().includes(search.toLowerCase()) && (!effect || action.state_effect === effect));
  return <>
    <div className="page-actions"><div className="list-stats"><strong>{actions.length}</strong> actions <span className="stat-separator" />{actions.filter(action => action.active).length} active</div><button className="primary" onClick={() => setEditor({action:null})}><span aria-hidden="true">＋</span> New action</button></div>
    <section className="admin-card resource-list" aria-label="Action list"><div className="list-toolbar"><label className="search-field"><span className="sr-only">Search actions</span><input placeholder="Search by label, code, parent or Oracle event" value={search} onChange={event => setSearch(event.target.value)} /></label><label><span className="sr-only">Filter by effect</span><select value={effect} onChange={event => setEffect(event.target.value)}><option value="">All effects</option><option value="ENTER">Entry · ENTER</option><option value="EXIT">Exit · EXIT</option></select></label><span className="subtle">{filtered.length} results</span></div>
      <div className="table-wrap"><table><thead><tr><th>Action</th><th>Effect / hierarchy</th><th>Oracle supplier event</th><th>Used by</th><th>Order</th><th>Status</th><th /></tr></thead><tbody>{filtered.map(action => <tr key={action.code}>
        <td><strong>{action.parent_action_code ? "↳ " : ""}{action.label}</strong><div className="cell-secondary"><code>{action.code}</code></div></td>
        <td><span className={`effect-tag effect-${action.state_effect.toLowerCase()}`}>{action.state_effect === "ENTER" ? "↗ Entry" : "↙ Exit"}</span><div className="cell-secondary">{action.parent_action_code ? `Sub-action of ${action.parent_action_code}` : action.requires_subaction ? `${action.subaction_codes.length} sub-actions` : "Top level"}</div></td>
        <td><code>{action.supplier_device_event}</code></td><td>{terminals.filter(terminal => terminal.action_codes.includes(action.code)).length} terminals</td><td>{action.display_order}</td><td><span className={`resource-status ${action.active ? "is-active" : "is-inactive"}`}><span />{action.active ? "Active" : "Inactive"}</span></td><td><button className="text-button" onClick={() => setEditor({action})}>Edit</button></td>
      </tr>)}</tbody></table></div>
    </section>
    {editor && <ActionEditor action={editor.action} actions={actions} terminals={terminals} onClose={() => setEditor(null)} onSaved={action => { setEditor(null); onChanged(`Action ${action.code} ${editor.action ? "updated" : "created"} successfully.`); }} />}
  </>;
}
