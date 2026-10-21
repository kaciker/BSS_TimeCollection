import { useState } from "react";
import type { AdminAction, AdminTerminal } from "../../types";
import { ActionEditor } from "./ActionEditor";
import { useLanguage } from "../../i18n";

export function ActionList({ actions, terminals, onChanged }: { actions: AdminAction[]; terminals: AdminTerminal[]; onChanged: (message: string) => void; }) {
  const { t } = useLanguage();
  const [search, setSearch] = useState(""); const [effect, setEffect] = useState(""); const [editor, setEditor] = useState<{action: AdminAction | null} | null>(null);
  const filtered = actions.filter(action => `${action.code} ${action.label} ${action.supplier_device_event} ${action.parent_action_code ?? ""}`.toLowerCase().includes(search.toLowerCase()) && (!effect || action.state_effect === effect));
  return <>
    <div className="page-actions"><div className="list-stats"><strong>{actions.length}</strong> {t("actionCount")} <span className="stat-separator" />{actions.filter(action => action.active).length} {t("active")}</div><button className="primary" onClick={() => setEditor({action:null})}><span aria-hidden="true">＋</span> {t("newAction")}</button></div>
    <section className="admin-card resource-list" aria-label={t("actionList")}><div className="list-toolbar"><label className="search-field"><span className="sr-only">{t("searchActions")}</span><input placeholder={t("searchActionPlaceholder")} value={search} onChange={event => setSearch(event.target.value)} /></label><label><span className="sr-only">{t("filterEffect")}</span><select value={effect} onChange={event => setEffect(event.target.value)}><option value="">{t("allEffects")}</option><option value="ENTER">{t("entry")} · ENTER</option><option value="EXIT">{t("exit")} · EXIT</option></select></label><span className="subtle">{filtered.length} {t("results")}</span></div>
      <div className="table-wrap"><table><thead><tr><th>{t("action")}</th><th>{t("hierarchy")}</th><th>{t("oracleSupplierEvent")}</th><th>{t("usedBy")}</th><th>{t("order")}</th><th>{t("status")}</th><th /></tr></thead><tbody>{filtered.map(action => <tr key={action.code}>
        <td><strong>{action.parent_action_code ? "↳ " : ""}{action.label}</strong><div className="cell-secondary"><code>{action.code}</code></div></td>
        <td><span className={`effect-tag effect-${action.state_effect.toLowerCase()}`}>{action.state_effect === "ENTER" ? `↗ ${t("entry")}` : `↙ ${t("exit")}`}</span><div className="cell-secondary">{action.parent_action_code ? `${t("subActionOf")} ${action.parent_action_code}` : action.requires_subaction ? `${action.subaction_codes.length} ${t("subActions")}` : t("topLevel")}</div></td>
        <td><code>{action.supplier_device_event}</code></td><td>{terminals.filter(terminal => terminal.action_codes.includes(action.code)).length} {t("terminalsCount")}</td><td>{action.display_order}</td><td><span className={`resource-status ${action.active ? "is-active" : "is-inactive"}`}><span />{action.active ? t("enabled") : t("disabled")}</span>{action.active && !action.show_on_terminal && <div className="cell-secondary">{t("hiddenFromTerminal")}</div>}</td><td><button className="text-button" onClick={() => setEditor({action})}>{t("edit")}</button></td>
      </tr>)}</tbody></table></div>
    </section>
    {editor && <ActionEditor action={editor.action} actions={actions} terminals={terminals} onClose={() => setEditor(null)} onSaved={action => { setEditor(null); onChanged(`${t("action")} ${action.code} ${editor.action ? t("actionUpdated") : t("actionCreated")}`); }} />}
  </>;
}
