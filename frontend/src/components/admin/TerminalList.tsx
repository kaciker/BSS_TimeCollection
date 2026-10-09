import { useState } from "react";
import type { AdminAction, AdminTerminal } from "../../types";
import { TerminalEditor } from "./TerminalEditor";

export function TerminalList({ terminals, actions, onChanged }: {
  terminals: AdminTerminal[]; actions: AdminAction[]; onChanged: (message: string) => void;
}) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [editor, setEditor] = useState<{ terminal: AdminTerminal | null } | null>(null);
  const filtered = terminals.filter(terminal => `${terminal.code} ${terminal.name} ${terminal.external_device_id}`.toLowerCase().includes(search.toLowerCase()) && (!status || terminal.active === (status === "active")));
  return <>
    <div className="page-actions"><div className="list-stats"><strong>{terminals.length}</strong> terminals <span className="stat-separator" /><span className="status-dot" />{terminals.filter(terminal => terminal.active).length} active</div><button className="primary" onClick={() => setEditor({terminal:null})}><span aria-hidden="true">＋</span> New terminal</button></div>
    <section className="admin-card resource-list" aria-label="Terminal list">
      <div className="list-toolbar"><label className="search-field"><span className="sr-only">Search terminals</span><input placeholder="Search by name, code or device ID" value={search} onChange={event => setSearch(event.target.value)} /></label><label><span className="sr-only">Terminal status</span><select value={status} onChange={event => setStatus(event.target.value)}><option value="">All statuses</option><option value="active">Active</option><option value="inactive">Inactive</option></select></label><span className="subtle">{filtered.length} results</span></div>
      <div className="table-wrap"><table><thead><tr><th>Terminal</th><th>Oracle device ID</th><th>Input method</th><th>Assigned actions</th><th>Status</th><th><span className="sr-only">Manage terminal</span></th></tr></thead><tbody>{filtered.map(terminal => <tr key={terminal.code}>
        <td><strong>{terminal.name}</strong><div className="cell-secondary"><code>{terminal.code}</code></div></td><td><code>{terminal.external_device_id}</code></td><td>{terminal.identification_mode === "BOTH" ? "Reader + keypad" : terminal.identification_mode === "RFID" ? "Badge reader" : "Keypad"}</td>
        <td><div className="action-tags">{terminal.action_codes.slice(0,3).map(code => <span key={code}>{actions.find(action => action.code === code)?.label ?? code}</span>)}{terminal.action_codes.length > 3 && <span title={terminal.action_codes.slice(3).join(", ")}>+{terminal.action_codes.length - 3}</span>}{!terminal.action_codes.length && <span className="unconfigured">Not configured</span>}</div></td>
        <td><span className={`resource-status ${terminal.active ? "is-active" : "is-inactive"}`}><span />{terminal.active ? "Active" : "Inactive"}</span></td><td><div className="table-controls"><button className="text-button" aria-label={`Edit terminal ${terminal.code}`} onClick={() => setEditor({terminal})}>Edit</button><a className="text-button" href={`/terminal/${encodeURIComponent(terminal.code)}`} target="_blank" rel="noreferrer" aria-label={`Open terminal ${terminal.code}`}>Open ↗</a></div></td>
      </tr>)}</tbody></table></div>
      {!filtered.length && <div className="empty-state"><h3>No terminals found</h3><p>{terminals.length ? "Try a different search or status filter." : "Create a terminal to configure a factory clock."}</p></div>}
    </section>
    {editor && <TerminalEditor terminal={editor.terminal} actions={actions} onClose={() => setEditor(null)} onSaved={terminal => { setEditor(null); onChanged(`Terminal ${terminal.code} ${editor.terminal ? "updated" : "created"} successfully.`); }} />}
  </>;
}
