import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api } from "../../api";
import type { AdminAction, AdminTerminal, StructureData } from "../../types";
import { exitPolicyLabel, exitPolicyModes } from "./exitPolicyOptions";
import type { ExitPolicyMode } from "./exitPolicyOptions";
import { EditorDialog } from "./EditorDialog";

const LEGACY_STRUCTURE_KEYS = new Set(["Plant", "Workshop", "Cell", "Project"]);
function editableAttributes(attributes: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(attributes).filter(([key]) => !LEGACY_STRUCTURE_KEYS.has(key) && key !== "work_cell"));
}
function preservedLegacyAttributes(attributes: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(attributes).filter(([key]) => LEGACY_STRUCTURE_KEYS.has(key)));
}

function attributeText(attributes: Record<string, unknown>, key: string): string {
  return typeof attributes[key] === "string" ? String(attributes[key]) : "";
}

export function TerminalEditor({ terminal, actions, onClose, onSaved }: { terminal: AdminTerminal | null; actions: AdminAction[]; onClose: () => void; onSaved: (value: AdminTerminal) => void; }) {
  const existingAttributes = terminal?.oracle_attributes ?? {};
  const [selected, setSelected] = useState<string[]>(terminal?.action_codes ?? []); const [enabled, setEnabled] = useState(terminal?.active ?? true); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const [exitPolicy, setExitPolicy] = useState<ExitPolicyMode>(terminal?.exit_policy_mode ?? "INHERIT");
  const [globalPolicy, setGlobalPolicy] = useState<ExitPolicyMode | null>(terminal?.global_exit_policy_mode ?? null);
  const [workCell, setWorkCell] = useState(attributeText(existingAttributes, "work_cell"));
  const [structure, setStructure] = useState<StructureData>({workshops:[],subworkshops:[],project_lines:[]});
  const [workshopId,setWorkshopId] = useState(String(terminal?.workshop_id??""));
  const [subworkshopId,setSubworkshopId] = useState(String(terminal?.subworkshop_id??""));
  const [projectLineId,setProjectLineId] = useState(String(terminal?.project_line_id??""));
  const [customAttributes,setCustomAttributes] = useState(JSON.stringify(editableAttributes(existingAttributes),null,2));
  const effectivePolicy = exitPolicy === "INHERIT" ? globalPolicy : exitPolicy;
  const availableSubs=structure.subworkshops.filter(x=>String(x.workshop_id)===workshopId&&(x.active||String(x.id)===subworkshopId));
  const availableProjects=structure.project_lines.filter(x=>String(x.subworkshop_id)===subworkshopId&&(x.active||String(x.id)===projectLineId));
  useEffect(() => {
    let cancelled = false;
    void api.get<{global_mode:ExitPolicyMode}>("/api/v1/admin/policies/same-terminal-exit")
      .then(value => { if (!cancelled) setGlobalPolicy(value.global_mode); })
      .catch(err => { if (!cancelled) setError((err as Error).message); });
    void api.get<StructureData>("/api/v1/admin/structure").then(value=>{if(!cancelled)setStructure(value);}).catch(err=>{if(!cancelled)setError((err as Error).message);});
    return () => { cancelled = true; };
  }, []);
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
    if (!projectLineId || !workshopId || !subworkshopId) {setError("Select a complete Workshop / Subworkshop / Project / Line path.");return;}
    if (!availableProjects.some(x=>String(x.id)===projectLineId)) {setError("Project / Line does not match Subworkshop.");return;}
    let parsed:unknown;
    try { parsed=JSON.parse(customAttributes||"{}"); } catch {setError("Oracle attributes must be valid JSON.");return;}
    if (!parsed || typeof parsed!=="object" || Array.isArray(parsed)) {setError("Oracle attributes must be a JSON object.");return;}
    const editedAttributes = parsed as Record<string,unknown>;
    if (Object.keys(editedAttributes).some(key => LEGACY_STRUCTURE_KEYS.has(key) || key === "work_cell")) {setError("Operational structure and work_cell are managed above.");return;}
    const oracleAttributes: Record<string,unknown> = {...preservedLegacyAttributes(existingAttributes),...editedAttributes};
    const cell = workCell.trim();
    if (cell) oracleAttributes.work_cell = cell; else delete oracleAttributes.work_cell;
    setBusy(true); setError("");
    const payload = { code:terminal?.code??String(data.get("code")).trim(), reporter_id_type:String(data.get("reporter")).trim(), workshop_id:Number(workshopId), subworkshop_id:Number(subworkshopId), project_line_id:Number(projectLineId), name: String(data.get("name")).trim(), external_device_id: String(data.get("device")).trim(), identification_mode: data.get("mode"), oracle_attributes: oracleAttributes, exit_policy_mode: exitPolicy, active: enabled, action_codes: selected };
    try { const saved = terminal ? await api.put<AdminTerminal>(`/api/v1/admin/terminals/${encodeURIComponent(terminal.code)}`, payload) : await api.post<AdminTerminal>("/api/v1/admin/terminals", payload); onSaved(saved); }
    catch (err) { setError((err as Error).message); setBusy(false); }
  };
  return <EditorDialog title={terminal ? "Edit terminal" : "New terminal"} description="Set terminal identity, operational structure, input method and actions." busy={busy} onClose={onClose}><form onSubmit={submit}>
    <div className="editor-body"><fieldset disabled={busy}>
      <section className="form-section"><h3>Terminal identity</h3><div className="field-grid"><label>Terminal code<input name="code" required maxLength={64} defaultValue={terminal?.code??""} readOnly={!!terminal}/></label><label>Display name<input name="name" required maxLength={160} defaultValue={terminal?.name ?? ""} /></label><label>Oracle device ID<input name="device" required maxLength={128} defaultValue={terminal?.external_device_id ?? ""} /></label><label>Reporter ID type<input name="reporter" required maxLength={16} defaultValue={terminal?.reporter_id_type??"BADGE"}/></label><label>Identification method<select name="mode" defaultValue={terminal?.identification_mode ?? "BOTH"}><option value="BOTH">Badge reader + keypad</option><option value="KEYPAD">Manual keypad</option><option value="RFID">Badge reader (RFID)</option></select></label></div></section>
      <section className="form-section"><h3>Exit policy</h3><p>Override the global Same Terminal Exit policy for this terminal, or inherit its current default.</p><div className="field-grid">
        <label>Same Terminal Exit<select name="exit_policy_mode" value={exitPolicy} onChange={event => setExitPolicy(event.target.value as ExitPolicyMode)}><option value="INHERIT">Inherit global{globalPolicy ? ` (${exitPolicyLabel(globalPolicy)})` : ""}</option>{exitPolicyModes.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
        <label>Work cell<input name="work_cell" value={workCell} onChange={event => setWorkCell(event.target.value)} maxLength={64} placeholder="Not configured" /><small>Used only by the Same Work Cell policy. Matching values are case-sensitive; blank removes the cell.</small></label>
      </div>{effectivePolicy && <p>Effective policy: {exitPolicyLabel(effectivePolicy)}</p>}{effectivePolicy === "SAME_WORK_CELL" && !workCell.trim() && <p className="form-notice">Exits will be rejected until this terminal and the entry terminal have matching configured work cells.</p>}</section>
      <section className="form-section"><h3>Operational structure</h3><div className="field-grid">
        <label>Workshop<select value={workshopId} onChange={event=>{setWorkshopId(event.target.value);setSubworkshopId("");setProjectLineId("");}}><option value="">Select Workshop</option>{structure.workshops.filter(x=>x.active||String(x.id)===workshopId).map(x=><option key={x.id} value={x.id}>{x.code} · {x.description}</option>)}</select></label>
        <label>Subworkshop<select value={subworkshopId} disabled={!workshopId} onChange={event=>{setSubworkshopId(event.target.value);setProjectLineId("");}}><option value="">Select Subworkshop</option>{availableSubs.map(x=><option key={x.id} value={x.id}>{x.code} · {x.description}</option>)}</select></label>
        <label>Project / Line<select value={projectLineId} disabled={!subworkshopId} onChange={event=>setProjectLineId(event.target.value)}><option value="">Select Project / Line</option>{availableProjects.map(x=><option key={x.id} value={x.id}>{x.code} · {x.description}</option>)}</select></label>
      </div><details><summary>Other Oracle attributes</summary><label>Integration attributes (JSON)<textarea rows={6} value={customAttributes} onChange={event=>setCustomAttributes(event.target.value)} spellCheck={false}/></label></details></section>
      <section className="form-section"><div className="section-heading"><div><h3>Availability</h3><p>Inactive terminals cannot capture new events.</p></div><label className="switch-control"><input type="checkbox" role="switch" checked={enabled} onChange={event => setEnabled(event.target.checked)} /><span className="switch-track" /><span>Active terminal</span></label></div></section>
      <section className="form-section"><h3>Worker actions</h3><p>Selecting an exit menu automatically selects its active sub-actions.</p><div className="assignment-group"><label className="field-label" htmlFor="entry-action">Automatic entry</label><select id="entry-action" value={entry?.code ?? ""} onChange={event => event.target.value ? setEntry(event.target.value) : setSelected(selected.filter(code => actions.find(action => action.code === code)?.state_effect !== "ENTER"))}><option value="">Select an entry action</option>{available.filter(action => action.active && action.state_effect === "ENTER").map(action => <option key={action.code} value={action.code}>{action.label} · {action.code}</option>)}</select></div>
        <div className="field-label">Exit reasons <span className="subtle">{topLevelExitCount} top-level selected</span></div><div className="assignment-list">{available.filter(action => action.state_effect === "EXIT").map(action => <label className={`assignment-option ${selected.includes(action.code) ? "selected" : ""}`} key={action.code} style={action.parent_action_code ? {marginLeft:"24px"} : undefined}><input type="checkbox" checked={selected.includes(action.code)} onChange={() => toggleExit(action.code)} /><span><strong>{action.parent_action_code ? "↳ " : ""}{action.label}</strong><small>{action.code}{action.requires_subaction ? ` · ${action.subaction_codes.length} sub-actions` : action.parent_action_code ? ` · child of ${action.parent_action_code}` : ""}</small></span><span className="subtle">EXIT</span></label>)}</div>
      </section>
    </fieldset>{error && <div className="inline-error" role="alert">{error}</div>}</div><div className="editor-footer"><button className="secondary" type="button" onClick={onClose} disabled={busy}>Cancel</button><button className="primary" type="submit" disabled={busy}>{busy ? "Saving…" : terminal ? "Save changes" : "Create terminal"}</button></div>
  </form></EditorDialog>;
}
