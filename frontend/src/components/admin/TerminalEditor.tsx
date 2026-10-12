import { useState } from "react";
import type { FormEvent } from "react";
import { api } from "../../api";
import type { AdminAction, AdminTerminal } from "../../types";
import { EditorDialog } from "./EditorDialog";

export function TerminalEditor({ terminal, actions, onClose, onSaved }: { terminal: AdminTerminal | null; actions: AdminAction[]; onClose: () => void; onSaved: (value: AdminTerminal) => void; }) {
  const [selected, setSelected] = useState<string[]>(terminal?.action_codes ?? []); const [enabled, setEnabled] = useState(terminal?.active ?? true); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const available = actions.filter(action => action.active || selected.includes(action.code));
  const entry = actions.find(action => selected.includes(action.code) && action.active && action.state_effect === "ENTER");
  const topLevelExitCount = actions.filter(action => selected.includes(action.code) && action.active && action.state_effect === "EXIT" && !action.parent_action_code).length;
  const setEntry = (code: string) => setSelected([...selected.filter(value => actions.find(action => action.code === value)?.state_effect !== "ENTER"), code]);
  const toggleExit = (code: string) => {
    const action = actions.find(item => item.code === code); if (!action) return;
    const next = new Set(selected);
    if (next.has(code)) {
      next.delete(code);
      if (action.requires_subaction) action.subaction_codes.forEach(child => next.delete(child));
    } else {
      next.add(code);
      if (action.requires_subaction) action.subaction_codes.filter(child => actions.find(item => item.code === child)?.active).forEach(child => next.add(child));
      if (action.parent_action_code) next.add(action.parent_action_code);
    }
    setSelected([...next]);
  };
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    if (enabled && (!entry || !topLevelExitCount)) { setError("Select one entry action and at least one top-level exit action for an active terminal."); return; }
    let attributes: unknown; try { attributes = JSON.parse(String(data.get("attributes") || "{}")); } catch { setError("Terminal Oracle attributes must be valid JSON."); return; }
    if (!attributes || typeof attributes !== "object" || Array.isArray(attributes)) { setError("Terminal Oracle attributes must be a JSON object."); return; }
    setBusy(true); setError("");
    const payload = { code: terminal?.code ?? String(data.get("code")).trim(), name: String(data.get("name")).trim(), external_device_id: String(data.get("device")).trim(), identification_mode: data.get("mode"), reporter_id_type: String(data.get("reporter")).trim(), oracle_attributes: attributes, active: enabled, action_codes: selected };
    try { const saved = terminal ? await api.put<AdminTerminal>(`/api/v1/admin/terminals/${encodeURIComponent(terminal.code)}`, payload) : await api.post<AdminTerminal>("/api/v1/admin/terminals", payload); onSaved(saved); }
    catch (err) { setError((err as Error).message); setBusy(false); }
  };
  return <EditorDialog title={terminal ? "Edit terminal" : "New terminal"} description="Set the terminal identity, Oracle context, input method and worker actions." busy={busy} onClose={onClose}><form onSubmit={submit}>
    <div className="editor-body"><fieldset disabled={busy}>
      <section className="form-section"><h3>Terminal identity</h3><div className="field-grid"><label>Terminal code<input name="code" required maxLength={64} defaultValue={terminal?.code ?? ""} readOnly={!!terminal} /></label><label>Display name<input name="name" required maxLength={160} defaultValue={terminal?.name ?? ""} /></label><label>Oracle device ID<input name="device" required maxLength={128} defaultValue={terminal?.external_device_id ?? ""} /></label><label>Reporter ID type<input name="reporter" required maxLength={16} defaultValue={terminal?.reporter_id_type ?? "BADGE"} /></label><label>Identification method<select name="mode" defaultValue={terminal?.identification_mode ?? "BOTH"}><option value="BOTH">Badge reader + keypad</option><option value="KEYPAD">Manual keypad</option><option value="RFID">Badge reader (RFID)</option></select></label></div></section>
      <section className="form-section"><h3>Oracle terminal context</h3><label>Attributes (JSON object)<textarea name="attributes" rows={7} defaultValue={JSON.stringify(terminal?.oracle_attributes ?? {}, null, 2)} spellCheck={false} /></label></section>
      <section className="form-section"><div className="section-heading"><div><h3>Availability</h3><p>Inactive terminals cannot capture new events.</p></div><label className="switch-control"><input type="checkbox" role="switch" checked={enabled} onChange={event => setEnabled(event.target.checked)} /><span className="switch-track" /><span>Active terminal</span></label></div></section>
      <section className="form-section"><h3>Worker actions</h3><p>Selecting an exit menu automatically selects its active sub-actions.</p><div className="assignment-group"><label className="field-label" htmlFor="entry-action">Automatic entry</label><select id="entry-action" value={entry?.code ?? ""} onChange={event => event.target.value ? setEntry(event.target.value) : setSelected(selected.filter(code => actions.find(action => action.code === code)?.state_effect !== "ENTER"))}><option value="">Select an entry action</option>{available.filter(action => action.active && action.state_effect === "ENTER").map(action => <option key={action.code} value={action.code}>{action.label} · {action.code}</option>)}</select></div>
        <div className="field-label">Exit reasons <span className="subtle">{topLevelExitCount} top-level selected</span></div><div className="assignment-list">{available.filter(action => action.state_effect === "EXIT").map(action => <label className={`assignment-option ${selected.includes(action.code) ? "selected" : ""}`} key={action.code} style={action.parent_action_code ? {marginLeft:"24px"} : undefined}><input type="checkbox" checked={selected.includes(action.code)} onChange={() => toggleExit(action.code)} /><span><strong>{action.parent_action_code ? "↳ " : ""}{action.label}</strong><small>{action.code}{action.requires_subaction ? ` · ${action.subaction_codes.length} sub-actions` : action.parent_action_code ? ` · child of ${action.parent_action_code}` : ""}</small></span><span className="subtle">EXIT</span></label>)}</div>
      </section>
    </fieldset>{error && <div className="inline-error" role="alert">{error}</div>}</div><div className="editor-footer"><button className="secondary" type="button" onClick={onClose} disabled={busy}>Cancel</button><button className="primary" type="submit" disabled={busy}>{busy ? "Saving…" : terminal ? "Save changes" : "Create terminal"}</button></div>
  </form></EditorDialog>;
}
