import { FormEvent, useEffect, useState } from "react";
import { api } from "../api";
import type { AdminAction, AdminEvent, AdminTerminal, IdentificationMode } from "../types";

export function AdminPage() {
  const [terminals, setTerminals] = useState<AdminTerminal[]>([]);
  const [actions, setActions] = useState<AdminAction[]>([]);
  const [events, setEvents] = useState<AdminEvent[]>([]);
  const [error, setError] = useState("");

  const refresh = async () => {
    try {
      const [terminalData, actionData, eventData] = await Promise.all([
        api.get<AdminTerminal[]>("/api/v1/admin/terminals"),
        api.get<AdminAction[]>("/api/v1/admin/actions"),
        api.get<AdminEvent[]>("/api/v1/admin/events?limit=50"),
      ]);
      setTerminals(terminalData);
      setActions(actionData);
      setEvents(eventData);
      setError("");
    } catch (err) {
      setError((err as Error).message);
    }
  };

  useEffect(() => { void refresh(); }, []);

  const createTerminal = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    await api.post("/api/v1/admin/terminals", {
      code: data.get("code"), name: data.get("name"), external_device_id: data.get("device"), identification_mode: data.get("mode") as IdentificationMode,
    });
    event.currentTarget.reset();
    await refresh();
  };

  const setActionsForTerminal = async (terminal: AdminTerminal, actionCode: string, enabled: boolean) => {
    const next = new Set(terminal.action_codes);
    enabled ? next.add(actionCode) : next.delete(actionCode);
    await api.put(`/api/v1/admin/terminals/${encodeURIComponent(terminal.code)}/actions`, { action_codes: Array.from(next) });
    await refresh();
  };

  return (
    <main className="admin-shell">
      <header className="admin-header"><div><div className="eyebrow">BSS TIME COLLECTION</div><h1>Administration</h1></div><div className="open-badge">Authentication disabled</div></header>
      {error && <div className="inline-error">{error}</div>}

      <section className="admin-card">
        <h2>Terminals</h2>
        <form className="admin-form" onSubmit={createTerminal}>
          <input name="code" placeholder="Terminal code" required />
          <input name="name" placeholder="Name" required />
          <input name="device" placeholder="Oracle deviceId" required />
          <select name="mode" defaultValue="BOTH"><option>RFID</option><option>KEYPAD</option><option>BOTH</option></select>
          <button className="primary" type="submit">Add terminal</button>
        </form>
        <div className="table-wrap"><table><thead><tr><th>Terminal</th><th>Device ID</th><th>Input</th><th>Enabled actions</th></tr></thead><tbody>
          {terminals.map((terminal) => <tr key={terminal.code}><td><strong>{terminal.code}</strong><br/><span>{terminal.name}</span></td><td>{terminal.external_device_id}</td><td>{terminal.identification_mode}</td><td><div className="checks">{actions.map((action) => <label key={action.code}><input type="checkbox" checked={terminal.action_codes.includes(action.code)} onChange={(e) => void setActionsForTerminal(terminal, action.code, e.target.checked)} />{action.label}</label>)}</div></td></tr>)}
        </tbody></table></div>
      </section>

      <section className="admin-card">
        <h2>Actions</h2>
        <div className="table-wrap"><table><thead><tr><th>Code</th><th>Label</th><th>Oracle supplier event</th><th>Effect</th></tr></thead><tbody>
          {actions.map((action) => <tr key={action.code}><td>{action.code}</td><td>{action.label}</td><td><code>{action.supplier_device_event}</code></td><td>{action.state_effect}</td></tr>)}
        </tbody></table></div>
        <p className="muted">Action creation/editing remains available through the admin REST API; this screen focuses on terminal assignment in v0.1.</p>
      </section>

      <section className="admin-card">
        <h2>Latest events</h2>
        <div className="table-wrap"><table><thead><tr><th>Time</th><th>Terminal</th><th>Badge</th><th>Action</th><th>Delivery</th><th>Attempts</th></tr></thead><tbody>
          {events.map((item) => <tr key={item.id}><td>{new Date(item.event_datetime).toLocaleString()}</td><td>{item.terminal_code}</td><td>{item.reporter_id}</td><td>{item.action_label}</td><td><span className={`status status-${item.delivery_status.toLowerCase()}`}>{item.delivery_status}</span></td><td>{item.attempt_count}</td></tr>)}
        </tbody></table></div>
      </section>
    </main>
  );
}
