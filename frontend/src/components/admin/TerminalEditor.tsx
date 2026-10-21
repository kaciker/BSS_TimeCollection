import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api } from "../../api";
import type { AdminAction, AdminTerminal, StructureData } from "../../types";
import { exitPolicyLabel, exitPolicyModes } from "./exitPolicyOptions";
import type { ExitPolicyMode } from "./exitPolicyOptions";
import { EditorDialog } from "./EditorDialog";
import { useLanguage } from "../../i18n";

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
  const { t, language } = useLanguage();
  const [perimeterOnly, setPerimeterOnly] = useState(!!terminal && terminal.terminal_role !== "CELL");
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
    if (!perimeterOnly && enabled && (!entry || !topLevelExitCount)) { setError(t("terminalEditError")); return; }
    if (!perimeterOnly && (!projectLineId || !workshopId || !subworkshopId)) {setError(t("completeStructureError"));return;}
    if (!perimeterOnly && !availableProjects.some(x=>String(x.id)===projectLineId)) {setError(t("projectMismatchError"));return;}
    let parsed:unknown;
    try { parsed=perimeterOnly ? {} : JSON.parse(customAttributes||"{}"); } catch {setError(t("oracleJsonError"));return;}
    if (!parsed || typeof parsed!=="object" || Array.isArray(parsed)) {setError(t("oracleObjectError"));return;}
    const editedAttributes = parsed as Record<string,unknown>;
    if (Object.keys(editedAttributes).some(key => LEGACY_STRUCTURE_KEYS.has(key) || key === "work_cell")) {setError(t("managedAttributesError"));return;}
    const oracleAttributes: Record<string,unknown> = {...preservedLegacyAttributes(existingAttributes),...editedAttributes};
    const cell = workCell.trim();
    if (cell) oracleAttributes.work_cell = cell; else delete oracleAttributes.work_cell;
    setBusy(true); setError("");
    const payload = { perimeter_only:perimeterOnly, workshop_id:perimeterOnly ? null : Number(workshopId), subworkshop_id:perimeterOnly ? null : Number(subworkshopId), project_line_id:perimeterOnly ? null : Number(projectLineId), name: String(data.get("name")).trim(), external_device_id: perimeterOnly ? undefined : String(data.get("device")).trim(), identification_mode: data.get("mode"), oracle_attributes: perimeterOnly ? {} : oracleAttributes, exit_policy_mode: perimeterOnly ? "DISABLED" : exitPolicy, active: enabled, action_codes: perimeterOnly ? [] : selected };
    try { const saved = terminal ? await api.put<AdminTerminal>(`/api/v1/admin/terminals/${encodeURIComponent(terminal.code)}`, payload) : await api.post<AdminTerminal>("/api/v1/admin/terminals", payload); onSaved(saved); }
    catch (err) { setError((err as Error).message); setBusy(false); }
  };
  return <EditorDialog title={terminal ? t("editTerminal") : t("newTerminalTitle")} description={t("terminalEditorHelp")} busy={busy} onClose={onClose}><form onSubmit={submit}>
    <div className="editor-body"><fieldset disabled={busy}>
      <section className="form-section"><div className="section-heading"><div><h3>{t("perimeterTerminal")}</h3><p>{t("perimeterTerminalHelp")}</p></div><label className="switch-control"><input type="checkbox" role="switch" checked={perimeterOnly} onChange={event => setPerimeterOnly(event.target.checked)} /><span className="switch-track" aria-hidden="true" /><span>{t("perimeterOnly")}</span></label></div>{perimeterOnly && <p className="form-notice">{t("perimeterAfterSave")}</p>}</section>
      <section className="form-section"><h3>{t("terminalIdentity")}</h3><div className="field-grid"><label>{t("terminalCode")}<input value={terminal?.code ?? t("assignedAutomatically")} readOnly /><small>{t("managedByApp")}</small></label><label>{t("displayName")}<input name="name" required maxLength={160} defaultValue={terminal?.name ?? ""} /></label><label>{t("oracleDeviceId")}<input name="device" disabled={perimeterOnly} required={!perimeterOnly} maxLength={40} defaultValue={terminal?.external_device_id ?? ""} /></label><label>{t("identificationMethod")}<select name="mode" defaultValue={terminal?.identification_mode ?? "BOTH"}><option value="BOTH">{t("readerKeypad")}</option><option value="KEYPAD">{t("manualKeypad")}</option><option value="RFID">{t("badgeReaderRfid")}</option></select></label></div></section>
      <section className="form-section"><fieldset disabled={perimeterOnly}><h3>{t("exitPolicy")}</h3><p>{t("overrideGlobalPolicy")}</p><div className="field-grid">
        <label>{t("sameTerminalExit")}<select name="exit_policy_mode" value={exitPolicy} onChange={event => setExitPolicy(event.target.value as ExitPolicyMode)}><option value="INHERIT">{t("inheritGlobal")}{globalPolicy ? ` (${exitPolicyLabel(globalPolicy, language)})` : ""}</option>{exitPolicyModes(language).map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
        <label>{t("workCell")}<input name="work_cell" value={workCell} onChange={event => setWorkCell(event.target.value)} maxLength={64} placeholder={t("notConfigured")} /><small>{t("sameWorkCellHelp")}</small></label>
      </div>{effectivePolicy && <p>{t("effectivePolicy")}: {exitPolicyLabel(effectivePolicy, language)}</p>}{effectivePolicy === "SAME_WORK_CELL" && !workCell.trim() && <p className="form-notice">{t("missingWorkCellHelp")}</p>}</fieldset></section>
      <section className="form-section"><fieldset disabled={perimeterOnly}><h3>{t("operationalStructure")}</h3><div className="field-grid">
        <label>{t("workshop")}<select value={workshopId} onChange={event=>{setWorkshopId(event.target.value);setSubworkshopId("");setProjectLineId("");}}><option value="">{t("selectWorkshop")}</option>{structure.workshops.filter(x=>x.active||String(x.id)===workshopId).map(x=><option key={x.id} value={x.id}>{x.code} · {x.description}</option>)}</select></label>
        <label>{t("subworkshop")}<select value={subworkshopId} disabled={!workshopId} onChange={event=>{setSubworkshopId(event.target.value);setProjectLineId("");}}><option value="">{t("selectSubworkshop")}</option>{availableSubs.map(x=><option key={x.id} value={x.id}>{x.code} · {x.description}</option>)}</select></label>
        <label>{t("projectLine")}<select value={projectLineId} disabled={!subworkshopId} onChange={event=>setProjectLineId(event.target.value)}><option value="">{t("projectLine")}</option>{availableProjects.map(x=><option key={x.id} value={x.id}>{x.code} · {x.description}</option>)}</select></label>
      </div><details><summary>{t("otherOracleAttributes")}</summary><label>{t("integrationAttributesJson")}<textarea rows={6} value={customAttributes} onChange={event=>setCustomAttributes(event.target.value)} spellCheck={false}/></label></details></fieldset></section>
      <section className="form-section"><div className="section-heading"><div><h3>{t("availability")}</h3><p>{t("inactiveTerminalsHelp")}</p></div><label className="switch-control"><input type="checkbox" role="switch" checked={enabled} onChange={event => setEnabled(event.target.checked)} /><span className="switch-track" /><span>{t("activeTerminal")}</span></label></div></section>
      <section className="form-section"><fieldset disabled={perimeterOnly}><h3>{t("workerActions")}</h3><p>{t("exitMenuHelp")}</p><div className="assignment-group"><label className="field-label" htmlFor="entry-action">{t("automaticEntry")}</label><select id="entry-action" value={entry?.code ?? ""} onChange={event => event.target.value ? setEntry(event.target.value) : setSelected(selected.filter(code => actions.find(action => action.code === code)?.state_effect !== "ENTER"))}><option value="">{t("selectEntryAction")}</option>{available.filter(action => action.active && action.state_effect === "ENTER").map(action => <option key={action.code} value={action.code}>{action.label} · {action.code}</option>)}</select></div>
        <div className="field-label">{t("exitReasons")} <span className="subtle">{topLevelExitCount} {t("topLevelSelected")}</span></div><div className="assignment-list">{available.filter(action => action.state_effect === "EXIT").map(action => <label className={`assignment-option ${selected.includes(action.code) ? "selected" : ""}`} key={action.code} style={action.parent_action_code ? {marginLeft:"24px"} : undefined}><input type="checkbox" checked={selected.includes(action.code)} onChange={() => toggleExit(action.code)} /><span><strong>{action.parent_action_code ? "↳ " : ""}{action.label}</strong><small>{action.code}{action.requires_subaction ? ` · ${action.subaction_codes.length} ${t("subActions")}` : action.parent_action_code ? ` · ${t("childOf")} ${action.parent_action_code}` : ""}</small></span><span className="subtle">EXIT</span></label>)}</div>
      </fieldset></section>
    </fieldset>{error && <div className="inline-error" role="alert">{error}</div>}</div><div className="editor-footer"><button className="secondary" type="button" onClick={onClose} disabled={busy}>{t("cancel")}</button><button className="primary" type="submit" disabled={busy}>{busy ? t("saving") : terminal ? t("saveChanges") : t("createTerminal")} </button></div>
  </form></EditorDialog>;
}
