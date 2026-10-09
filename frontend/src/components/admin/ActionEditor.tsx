import { useState } from "react";
import type { FormEvent } from "react";
import { api } from "../../api";
import type { AdminAction, AdminTerminal } from "../../types";
import { EditorDialog } from "./EditorDialog";

export function ActionEditor({ action, terminals, onClose, onSaved }: {
  action: AdminAction | null; terminals: AdminTerminal[]; onClose: () => void; onSaved: (value: AdminAction) => void;
}) {
  const [active, setActive] = useState(action?.active ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const assigned = terminals.filter(terminal => action && terminal.action_codes.includes(action.code));
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setError("");
    let attributes: unknown;
    try { attributes = JSON.parse(String(data.get("attributes") || "{}")); }
    catch { setError("Oracle attributes must be valid JSON."); return; }
    if (!attributes || typeof attributes !== "object" || Array.isArray(attributes)) { setError("Oracle attributes must be a JSON object."); return; }
    const payload = {
      code: action?.code ?? String(data.get("code")).trim(), label: String(data.get("label")).trim(),
      supplier_device_event: String(data.get("supplier")).trim(), state_effect: data.get("effect"),
      display_order: Number(data.get("order")), oracle_attributes: attributes, active,
    };
    setBusy(true);
    try {
      const saved = action
        ? await api.put<AdminAction>(`/api/v1/admin/actions/${encodeURIComponent(action.code)}`, payload)
        : await api.post<AdminAction>("/api/v1/admin/actions", payload);
      onSaved(saved);
    } catch (err) { setError((err as Error).message); setBusy(false); }
  };
  return <EditorDialog title={action ? "Edit action" : "New action"} description="Define a worker action and its Oracle event mapping. Use English labels." busy={busy} onClose={onClose}>
    <form onSubmit={submit}><div className="editor-body"><fieldset disabled={busy}>
      <section className="form-section"><h3>Worker action</h3><div className="field-grid">
        <label>Action code<input name="code" required maxLength={64} defaultValue={action?.code ?? ""} readOnly={!!action} placeholder="e.g. MEAL" autoFocus /><small>{action ? "Stable identifier; cannot be changed." : "Unique internal identifier."}</small></label>
        <label>Label (English)<input name="label" required maxLength={120} defaultValue={action?.label ?? ""} placeholder="e.g. Meal break" /><small>Shown on the terminal and stored with each event.</small></label>
        <label>Local state effect<select name="effect" defaultValue={action?.state_effect ?? "EXIT"}><option value="ENTER">Entry · ENTER</option><option value="EXIT">Exit · EXIT</option></select><small>Controls the next terminal interaction.</small></label>
        <label>Display order<input name="order" type="number" required min={0} max={100000} defaultValue={action?.display_order ?? 100} /><small>Lower numbers appear first.</small></label>
      </div></section>
      <section className="form-section"><h3>Oracle mapping</h3><div className="field-grid">
        <label>Supplier event code<input name="supplier" required maxLength={128} defaultValue={action?.supplier_device_event ?? ""} placeholder="e.g. BSS_MEAL" /><small>Unique supplierDeviceEvent configured in Oracle.</small></label>
      </div><details className="advanced-fields"><summary>Optional action-specific Oracle attributes</summary><label>Attributes (JSON object)<textarea name="attributes" rows={5} defaultValue={JSON.stringify(action?.oracle_attributes ?? {}, null, 2)} spellCheck={false} /><small>Action attributes are merged with the terminal context for future captures.</small></label></details></section>
      <section className="form-section"><div className="section-heading"><div><h3>Availability</h3><p>Inactive actions are hidden from worker interaction.</p></div><label className="switch-control"><input type="checkbox" role="switch" checked={active} onChange={event => setActive(event.target.checked)} /><span className="switch-track" aria-hidden="true" /><span>Active action</span></label></div>
        {assigned.length > 0 && <p className="form-notice">Used by {assigned.map(terminal => terminal.code).join(", ")}. Changes apply to future events; existing event records retain their captured values.</p>}
      </section>
    </fieldset>{error && <div className="inline-error" role="alert">{error}</div>}</div>
    <div className="editor-footer"><button className="secondary" type="button" onClick={onClose} disabled={busy}>Cancel</button><button className="primary" type="submit" disabled={busy}>{busy ? "Saving…" : action ? "Save changes" : "Create action"}</button></div></form>
  </EditorDialog>;
}
