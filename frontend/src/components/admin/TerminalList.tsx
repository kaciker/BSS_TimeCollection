import { useRef, useState } from "react";
import { api } from "../../api";
import type { AdminAction, AdminTerminal, TerminalProvisioning } from "../../types";
import { TerminalEditor } from "./TerminalEditor";

export function TerminalList({ terminals, actions, onChanged }: {
  terminals: AdminTerminal[]; actions: AdminAction[]; onChanged: (message: string) => void;
}) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [editor, setEditor] = useState<{ terminal: AdminTerminal | null } | null>(null);
  const [provisioning, setProvisioning] = useState<TerminalProvisioning | null>(null);
  const [provisionError, setProvisionError] = useState("");
  const [copied, setCopied] = useState(false);
  const activationInput = useRef<HTMLInputElement>(null);
  const copyActivationUrl = async () => {
    setProvisionError("");
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(activationUrl);
      } else {
        activationInput.current?.focus();
        activationInput.current?.select();
        if (!document.execCommand("copy")) throw new Error("Select and copy the activation URL manually.");
      }
      setCopied(true);
    } catch { setProvisionError("Could not copy the link. Select and copy the activation URL manually."); }
  };
  const filtered = terminals.filter(terminal => `${terminal.code} ${terminal.name} ${terminal.external_device_id}`.toLowerCase().includes(search.toLowerCase()) && (!status || terminal.active === (status === "active")));
  const activationUrl = provisioning ? `${window.location.origin}/terminal/activate#${provisioning.activation_token}` : "";

  const provision = async (terminal: AdminTerminal) => {
    if (terminal.provisioned && !window.confirm(`Reprovision ${terminal.code}? The existing browser session will be revoked.`)) return;
    setProvisionError("");
    try {
      const value = await api.post<TerminalProvisioning>(`/api/v1/admin/terminals/${encodeURIComponent(terminal.code)}/provision`, {});
      setProvisioning(value);
      setCopied(false);
      onChanged(`Activation link generated for ${terminal.code}.`);
    } catch (err) {
      setProvisionError((err as Error).message);
    }
  };

  return <>
    <div className="page-actions"><div className="list-stats"><strong>{terminals.length}</strong> terminals <span className="stat-separator" /><span className="status-dot" />{terminals.filter(terminal => terminal.active).length} active</div><button className="primary" onClick={() => setEditor({terminal:null})}><span aria-hidden="true">＋</span> New terminal</button></div>
    {provisioning && <section className="admin-card">
      <div className="section-heading"><div><h3>Activation link · {provisioning.code}</h3><p>Open this link once on the physical workstation. The token is consumed, stored as an HttpOnly browser session and removed from the address bar.</p></div><button className="icon-button" aria-label="Close activation link" onClick={() => setProvisioning(null)}>×</button></div>
      <label>One-time activation URL<input ref={activationInput} readOnly value={activationUrl} onFocus={event => event.currentTarget.select()} /></label>
      <div className="page-actions"><button className="secondary" onClick={() => void copyActivationUrl()}>{copied ? "Copied" : "Copy activation URL"}</button></div>
    </section>}
    {provisionError && <div className="inline-error" role="alert">{provisionError}</div>}
    <section className="admin-card resource-list" aria-label="Terminal list">
      <div className="list-toolbar"><label className="search-field"><span className="sr-only">Search terminals</span><input placeholder="Search by name, code or device ID" value={search} onChange={event => setSearch(event.target.value)} /></label><label><span className="sr-only">Terminal status</span><select value={status} onChange={event => setStatus(event.target.value)}><option value="">All statuses</option><option value="active">Active</option><option value="inactive">Inactive</option></select></label><span className="subtle">{filtered.length} results</span></div>
      <div className="table-wrap"><table><thead><tr><th>Terminal</th><th>Oracle device ID</th><th>Input method</th><th>Oracle context</th><th>Browser binding</th><th>Status</th><th><span className="sr-only">Manage terminal</span></th></tr></thead><tbody>{filtered.map(terminal => <tr key={terminal.code}>
        <td><strong>{terminal.name}</strong><div className="cell-secondary"><code>{terminal.code}</code></div></td><td><code>{terminal.external_device_id}</code></td><td>{terminal.identification_mode === "BOTH" ? "Reader + keypad" : terminal.identification_mode === "RFID" ? "Badge reader" : "Keypad"}</td>
        <td><div className="action-tags">{Object.entries(terminal.oracle_attributes).slice(0,3).map(([key, value]) => <span key={key}>{key}: {String(value)}</span>)}{Object.keys(terminal.oracle_attributes).length > 3 && <span>+{Object.keys(terminal.oracle_attributes).length - 3}</span>}{!Object.keys(terminal.oracle_attributes).length && <span className="unconfigured">No context</span>}</div></td>
        <td><span className={`resource-status ${terminal.provisioned ? "is-active" : "is-inactive"}`}><span />{terminal.provisioned ? "Provisioned" : terminal.activation_pending ? "Activation pending" : "Not provisioned"}</span></td>
        <td><span className={`resource-status ${terminal.active ? "is-active" : "is-inactive"}`}><span />{terminal.active ? "Active" : "Inactive"}</span></td><td><div className="table-controls"><button className="text-button" aria-label={`Edit terminal ${terminal.code}`} onClick={() => setEditor({terminal})}>Edit</button><button className="text-button" onClick={() => void provision(terminal)}>{terminal.provisioned ? "Reprovision" : "Provision"}</button></div></td>
      </tr>)}</tbody></table></div>
      {!filtered.length && <div className="empty-state"><h3>No terminals found</h3><p>{terminals.length ? "Try a different search or status filter." : "Create a terminal to configure a factory clock."}</p></div>}
    </section>
    {editor && <TerminalEditor terminal={editor.terminal} actions={actions} onClose={() => setEditor(null)} onSaved={terminal => {
      setEditor(null);
      if (terminal.activation_token) { setProvisioning({code: terminal.code, activation_token: terminal.activation_token}); setCopied(false); }
      onChanged(`Terminal ${terminal.code} ${editor.terminal ? "updated" : "created"} successfully.`);
    }} />}
  </>;
}
