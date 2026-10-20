import { useState } from "react";
import { actionVisuals } from "../../actionVisuals";
import type { FormEvent } from "react";
import { api } from "../../api";
import type { AdminAction, AdminTerminal } from "../../types";
import { EditorDialog } from "./EditorDialog";



export function ActionEditor({ action, actions, terminals, onClose, onSaved }: {
  action: AdminAction | null; actions: AdminAction[]; terminals: AdminTerminal[]; onClose: () => void; onSaved: (value: AdminAction) => void;
}) {
  const [visualKey, setVisualKey] = useState(action?.visual_key ?? "");
  const [active, setActive] = useState(action?.active ?? true);
  const [showOnTerminal, setShowOnTerminal] = useState(action?.show_on_terminal ?? true);
  const [effect, setEffect] = useState<"ENTER" | "EXIT">(action?.state_effect ?? "EXIT");
  const [requiresSubaction, setRequiresSubaction] = useState(action?.requires_subaction ?? false);
  const [parentCode, setParentCode] = useState(action?.parent_action_code ?? "");
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const assigned = terminals.filter(terminal => action && terminal.action_codes.includes(action.code));
  const parentCandidates = actions.filter(item => item.code !== action?.code && item.active && item.state_effect === "EXIT" && item.requires_subaction && !item.parent_action_code);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget); setError("");
    let attributes: unknown;
    try { attributes = JSON.parse(String(data.get("attributes") || "{}")); } catch { setError("Oracle attributes must be valid JSON."); return; }
    if (!attributes || typeof attributes !== "object" || Array.isArray(attributes)) { setError("Oracle attributes must be a JSON object."); return; }
    const payload = { code: action?.code ?? String(data.get("code")).trim(), label: String(data.get("label")).trim(), supplier_device_event: String(data.get("supplier")).trim(), state_effect: effect, display_order: Number(data.get("order")), oracle_attributes: attributes, requires_subaction: effect === "EXIT" && !parentCode ? requiresSubaction : false, parent_action_code: effect === "EXIT" && parentCode ? parentCode : null, visual_key: visualKey || null, show_on_terminal: showOnTerminal, active };
    setBusy(true);
    try { const saved = action ? await api.put<AdminAction>(`/api/v1/admin/actions/${encodeURIComponent(action.code)}`, payload) : await api.post<AdminAction>("/api/v1/admin/actions", payload); onSaved(saved); }
    catch (err) { setError((err as Error).message); setBusy(false); }
  };
  return <EditorDialog title={action ? "Edit action" : "New action"} description="Define a worker action and its Oracle event mapping. Exit actions can optionally open one level of sub-actions." busy={busy} onClose={onClose}>
    <form onSubmit={submit}><div className="editor-body"><fieldset disabled={busy}>
      <section className="form-section"><h3>Worker action</h3><div className="field-grid">
        <label>Action code<input name="code" required maxLength={64} defaultValue={action?.code ?? ""} readOnly={!!action} placeholder="e.g. FACTORY_EXIT" autoFocus /></label>
        <label>Label (English)<input name="label" required maxLength={120} defaultValue={action?.label ?? ""} placeholder="e.g. Factory exit" /></label>
        <label>Local state effect<select value={effect} onChange={event => { const value = event.target.value as "ENTER" | "EXIT"; setEffect(value); if (value === "ENTER") { setParentCode(""); setRequiresSubaction(false); } }}><option value="ENTER">Entry · ENTER</option><option value="EXIT">Exit · EXIT</option></select></label>
        <label>Display order<input name="order" type="number" required min={0} max={100000} defaultValue={action?.display_order ?? 100} /></label>
      </div></section>
      {effect === "EXIT" && <section className="form-section"><h3>Exit hierarchy</h3><div className="field-grid">
        <label>Parent action<select value={parentCode} onChange={event => { setParentCode(event.target.value); if (event.target.value) setRequiresSubaction(false); }}><option value="">Top-level exit action</option>{parentCandidates.map(item => <option value={item.code} key={item.code}>{item.label} · {item.code}</option>)}</select><small>Choose a parent to make this action a second-level reason.</small></label>
        <label className="switch-control"><input type="checkbox" role="switch" checked={requiresSubaction} disabled={!!parentCode} onChange={event => setRequiresSubaction(event.target.checked)} /><span className="switch-track" aria-hidden="true" /><span>Requires sub-action</span></label>
      </div>{requiresSubaction && <p className="form-notice">This action becomes a menu. Selecting it on the terminal opens its active child actions; the parent itself is not recorded as the final exit event.</p>}</section>}
      <section className="form-section"><h3>Action illustration</h3><p>Optional visual scene displayed on terminal action cards.</p><div className="action-visual-picker">{actionVisuals.map(option => <label className={`action-visual-option ${visualKey === option.key ? "selected" : ""}`} key={option.key}><input type="radio" name="visual_key" checked={visualKey === option.key} onChange={() => setVisualKey(option.key)} />{option.key ? <img src={`/action-visuals/${option.key}.png`} alt="" /> : <span className="no-visual">—</span>}<span>{option.name}</span></label>)}</div></section>
      <section className="form-section"><h3>Oracle mapping</h3><div className="field-grid"><label>Supplier event code<input name="supplier" required maxLength={128} defaultValue={action?.supplier_device_event ?? ""} placeholder="e.g. BSS_FACTORY_EXIT" /></label></div><details className="advanced-fields"><summary>Optional action-specific Oracle attributes</summary><label>Attributes (JSON object)<textarea name="attributes" rows={5} defaultValue={JSON.stringify(action?.oracle_attributes ?? {}, null, 2)} spellCheck={false} /></label></details></section>
      <section className="form-section"><div className="section-heading"><div><h3>Availability</h3><p>Inactive actions are hidden from worker interaction.</p></div><label className="switch-control"><input type="checkbox" role="switch" checked={active} onChange={event => setActive(event.target.checked)} /><span className="switch-track" aria-hidden="true" /><span>Active action</span></label></div><label className="switch-control"><input type="checkbox" role="switch" checked={showOnTerminal} onChange={event => setShowOnTerminal(event.target.checked)} /><span className="switch-track" aria-hidden="true" /><span>Show on terminal</span></label><p className="form-notice">Hidden actions remain active for internal processes, including automatic perimeter exits, but cannot be selected by workers.</p>{assigned.length > 0 && <p className="form-notice">Used by {assigned.map(terminal => terminal.code).join(", ")}.</p>}</section>
    </fieldset>{error && <div className="inline-error" role="alert">{error}</div>}</div>
    <div className="editor-footer"><button className="secondary" type="button" onClick={onClose} disabled={busy}>Cancel</button><button className="primary" type="submit" disabled={busy}>{busy ? "Saving…" : action ? "Save changes" : "Create action"}</button></div></form>
  </EditorDialog>;
}
