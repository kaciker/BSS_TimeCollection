import { useState } from "react";
import { localizedActionVisuals } from "../../actionVisuals";
import type { FormEvent } from "react";
import { api } from "../../api";
import type { AdminAction, AdminTerminal } from "../../types";
import { EditorDialog } from "./EditorDialog";
import { useLanguage } from "../../i18n";



export function ActionEditor({ action, actions, terminals, onClose, onSaved }: {
  action: AdminAction | null; actions: AdminAction[]; terminals: AdminTerminal[]; onClose: () => void; onSaved: (value: AdminAction) => void;
}) {
  const { t, language } = useLanguage();
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
    try { attributes = JSON.parse(String(data.get("attributes") || "{}")); } catch { setError(t("oracleJsonError")); return; }
    if (!attributes || typeof attributes !== "object" || Array.isArray(attributes)) { setError(t("oracleObjectError")); return; }
    const payload = { code: action?.code ?? String(data.get("code")).trim(), label: String(data.get("label")).trim(), supplier_device_event: String(data.get("supplier")).trim(), state_effect: effect, display_order: Number(data.get("order")), oracle_attributes: attributes, requires_subaction: effect === "EXIT" && !parentCode ? requiresSubaction : false, parent_action_code: effect === "EXIT" && parentCode ? parentCode : null, visual_key: visualKey || null, show_on_terminal: showOnTerminal, active };
    setBusy(true);
    try { const saved = action ? await api.put<AdminAction>(`/api/v1/admin/actions/${encodeURIComponent(action.code)}`, payload) : await api.post<AdminAction>("/api/v1/admin/actions", payload); onSaved(saved); }
    catch (err) { setError((err as Error).message); setBusy(false); }
  };
  return <EditorDialog title={action ? t("editAction") : t("newActionTitle")} description={t("actionEditorHelp")} busy={busy} onClose={onClose}>
    <form onSubmit={submit}><div className="editor-body"><fieldset disabled={busy}>
      <section className="form-section"><h3>{t("workerAction")}</h3><div className="field-grid">
        <label>{t("actionCode")}<input name="code" required maxLength={64} defaultValue={action?.code ?? ""} readOnly={!!action} placeholder="e.g. FACTORY_EXIT" autoFocus /></label>
        <label>{t("labelEnglish")}<input name="label" required maxLength={120} defaultValue={action?.label ?? ""} placeholder="e.g. Factory exit" /></label>
        <label>{t("localStateEffect")}<select value={effect} onChange={event => { const value = event.target.value as "ENTER" | "EXIT"; setEffect(value); if (value === "ENTER") { setParentCode(""); setRequiresSubaction(false); } }}><option value="ENTER">{t("entry")} · ENTER</option><option value="EXIT">{t("exit")} · EXIT</option></select></label>
        <label>{t("order")}<input name="order" type="number" required min={0} max={100000} defaultValue={action?.display_order ?? 100} /></label>
      </div></section>
      {effect === "EXIT" && <section className="form-section"><h3>{t("exitHierarchy")}</h3><div className="field-grid">
        <label>{t("parentAction")}<select value={parentCode} onChange={event => { setParentCode(event.target.value); if (event.target.value) setRequiresSubaction(false); }}><option value="">{t("topLevelExit")}</option>{parentCandidates.map(item => <option value={item.code} key={item.code}>{item.label} · {item.code}</option>)}</select><small>{t("parentHelp")}</small></label>
        <label className="switch-control"><input type="checkbox" role="switch" checked={requiresSubaction} disabled={!!parentCode} onChange={event => setRequiresSubaction(event.target.checked)} /><span className="switch-track" aria-hidden="true" /><span>{t("requiresSubaction")}</span></label>
      </div>{requiresSubaction && <p className="form-notice">{t("subactionMenuHelp")}</p>}</section>}
      <section className="form-section"><h3>{t("actionIllustration")}</h3><p>{t("optionalVisual")}</p><div className="action-visual-picker">{localizedActionVisuals(language).map(option => <label className={`action-visual-option ${visualKey === option.key ? "selected" : ""}`} key={option.key}><input type="radio" name="visual_key" checked={visualKey === option.key} onChange={() => setVisualKey(option.key)} />{option.key ? <img src={`/action-visuals/${option.key}.png`} alt="" /> : <span className="no-visual">—</span>}<span>{option.name}</span></label>)}</div></section>
      <section className="form-section"><h3>{t("oracleMapping")}</h3><div className="field-grid"><label>{t("supplierEventCode")}<input name="supplier" required maxLength={128} defaultValue={action?.supplier_device_event ?? ""} placeholder="e.g. BSS_FACTORY_EXIT" /></label></div><details className="advanced-fields"><summary>{t("optionalOracleAttributes")}</summary><label>{t("attributesJson")}<textarea name="attributes" rows={5} defaultValue={JSON.stringify(action?.oracle_attributes ?? {}, null, 2)} spellCheck={false} /></label></details></section>
      <section className="form-section"><div className="section-heading"><div><h3>{t("availability")}</h3><p>{t("inactiveActionsHidden")}</p></div><label className="switch-control"><input type="checkbox" role="switch" checked={active} onChange={event => setActive(event.target.checked)} /><span className="switch-track" aria-hidden="true" /><span>{t("activeAction")}</span></label></div><label className="switch-control"><input type="checkbox" role="switch" checked={showOnTerminal} onChange={event => setShowOnTerminal(event.target.checked)} /><span className="switch-track" aria-hidden="true" /><span>{t("showOnTerminal")}</span></label><p className="form-notice">{t("hiddenActionsHelp")}</p>{assigned.length > 0 && <p className="form-notice">{t("usedByTerminals")} {assigned.map(terminal => terminal.code).join(", ")}.</p>}</section>
    </fieldset>{error && <div className="inline-error" role="alert">{error}</div>}</div>
    <div className="editor-footer"><button className="secondary" type="button" onClick={onClose} disabled={busy}>{t("cancel")}</button><button className="primary" type="submit" disabled={busy}>{busy ? t("saving") : action ? t("saveChanges") : t("createAction")}</button></div></form>
  </EditorDialog>;
}
