import { useRef, useState } from "react";
import { api } from "../../api";
import type { AdminAction, AdminTerminal, TerminalProvisioning } from "../../types";
import { TerminalEditor } from "./TerminalEditor";
import { useLanguage } from "../../i18n";

export function TerminalList({ terminals, actions, onChanged }: {
  terminals: AdminTerminal[]; actions: AdminAction[]; onChanged: (message: string) => void;
}) {
  const { t } = useLanguage();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [editor, setEditor] = useState<{ terminal: AdminTerminal | null } | null>(null);
  const [provisioning, setProvisioning] = useState<TerminalProvisioning | null>(null);
  const [provisionError, setProvisionError] = useState("");
  const [copied, setCopied] = useState(false);
  const [cloning, setCloning] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [pairingOpen, setPairingOpen] = useState(false);
  const [pairingCode, setPairingCode] = useState("");
  const [pairingTerminal, setPairingTerminal] = useState("");
  const [pairingBusy, setPairingBusy] = useState(false);
  const activationInput = useRef<HTMLInputElement>(null);
  const copyActivationUrl = async () => {
    setProvisionError("");
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(activationUrl);
      } else {
        activationInput.current?.focus();
        activationInput.current?.select();
        if (!document.execCommand("copy")) throw new Error(t("copyManually"));
      }
      setCopied(true);
    } catch { setProvisionError(t("copyFailed")); }
  };
  const filtered = terminals.filter(terminal => `${terminal.code} ${terminal.name} ${terminal.external_device_id}`.toLowerCase().includes(search.toLowerCase()) && (!status || terminal.active === (status === "active")));
  const activationUrl = provisioning ? `${window.location.origin}/terminal/activate#${provisioning.activation_token}` : "";

  const clone = async (terminal: AdminTerminal) => {
    if (cloning) return;
    setCloning(terminal.code);
    setProvisionError("");
    try {
      const value = await api.post<AdminTerminal>(`/api/v1/admin/terminals/${encodeURIComponent(terminal.code)}/clone`, {});
      setProvisioning(null);
      onChanged(`${t("terminal")} ${value.code} ${t("clonedReview")}`);
      setEditor({ terminal: value });
    } catch (err) { setProvisionError((err as Error).message); }
    finally { setCloning(null); }
  };

  const remove = async (terminal: AdminTerminal) => {
    if (deleting || !window.confirm(`${t("confirmRemoveTerminal")} ${terminal.code}? ${t("removeTerminalHelp")}`)) return;
    setDeleting(terminal.code);
    setProvisionError("");
    try {
      await api.delete(`/api/v1/admin/terminals/${encodeURIComponent(terminal.code)}`);
      if (provisioning?.code === terminal.code) setProvisioning(null);
      onChanged(`${t("terminal")} ${terminal.code} ${t("terminalRemoved")}`);
    } catch (err) { setProvisionError((err as Error).message); }
    finally { setDeleting(null); }
  };

  const provision = async (terminal: AdminTerminal) => {
    if (terminal.provisioned && !window.confirm(`${t("confirmReprovision")} ${terminal.code}? ${t("reprovisionHelp")}`)) return;
    setProvisionError("");
    try {
      const value = await api.post<TerminalProvisioning>(`/api/v1/admin/terminals/${encodeURIComponent(terminal.code)}/provision`, {});
      setProvisioning(value);
      setCopied(false);
      onChanged(`${t("activationLinkGenerated")} ${terminal.code}.`);
    } catch (err) {
      setProvisionError((err as Error).message);
    }
  };

  const pairBrowser = async () => {
    const terminal = terminals.find(item => item.code === pairingTerminal);
    if (!terminal || !pairingCode.trim()) return;
    if (terminal.provisioned && !window.confirm(`${t("confirmNewBrowser")} ${terminal.code}? ${t("pairBrowserRevokesHelp")}`)) return;
    setPairingBusy(true);
    setProvisionError("");
    try {
      await api.post<AdminTerminal>(`/api/v1/admin/terminals/${encodeURIComponent(terminal.code)}/pair`, { pairing_code: pairingCode.trim() });
      setPairingCode("");
      setPairingTerminal("");
      setPairingOpen(false);
      onChanged(`${t("pairingApprovedFor")} ${terminal.code}. ${t("browserActivatesAutomatically")}`);
    } catch (err) {
      setProvisionError((err as Error).message);
    } finally {
      setPairingBusy(false);
    }
  };

  return <>
    <div className="page-actions"><div className="list-stats"><strong>{terminals.length}</strong> {t("terminalsCount")} <span className="stat-separator" /><span className="status-dot" />{terminals.filter(terminal => terminal.active).length} {t("active")}</div><div className="table-controls"><button className="secondary" onClick={() => setPairingOpen(value => !value)}>{t("pairBrowser")}</button><button className="primary" onClick={() => setEditor({terminal:null})}><span aria-hidden="true">＋</span> {t("newTerminal")}</button></div></div>
    {pairingOpen && <section className="admin-card admin-form-card">
      <div className="section-heading"><div><h3>{t("pairByCode")}</h3><p>{t("pairHelp")}</p></div><button className="icon-button" aria-label={t("closePairing")} onClick={() => setPairingOpen(false)}>×</button></div>
      <div className="form-grid"><label>{t("pairingCode")}<input className="pairing-input" value={pairingCode} placeholder="ABCD-EFGH" maxLength={16} autoComplete="off" onChange={event => setPairingCode(event.target.value.toUpperCase())} /></label><label>{t("assignTerminal")}<select value={pairingTerminal} onChange={event => setPairingTerminal(event.target.value)}><option value="">{t("selectTerminal")}</option>{terminals.filter(terminal => terminal.active).map(terminal => <option key={terminal.code} value={terminal.code}>{terminal.code} · {terminal.name}</option>)}</select></label></div>
      <div className="form-actions"><button className="primary" disabled={pairingBusy || !pairingCode.trim() || !pairingTerminal} onClick={() => void pairBrowser()}>{pairingBusy ? t("pairing") : t("approvePairing")}</button></div>
    </section>}
    {provisioning && <section className="admin-card admin-form-card">
      <div className="section-heading"><div><h3>{t("activationLink")} · {provisioning.code}</h3><p>{t("activationHelp")}</p></div><button className="icon-button" aria-label={t("closeActivation")} onClick={() => setProvisioning(null)}>×</button></div>
      <label className="field-control">{t("oneTimeUrl")}<input ref={activationInput} readOnly value={activationUrl} onFocus={event => event.currentTarget.select()} /></label>
      <div className="form-actions"><button className="secondary" onClick={() => void copyActivationUrl()}>{copied ? t("copied") : t("copyUrl")}</button></div>
    </section>}
    {provisionError && <div className="inline-error" role="alert">{provisionError}</div>}
    <section className="admin-card resource-list" aria-label={t("terminals")}>
      <div className="list-toolbar"><label className="search-field"><span className="sr-only">{t("searchTerminals")}</span><input placeholder={t("searchTerminalPlaceholder")} value={search} onChange={event => setSearch(event.target.value)} /></label><label><span className="sr-only">{t("terminalStatus")}</span><select value={status} onChange={event => setStatus(event.target.value)}><option value="">{t("allStatuses")}</option><option value="active">{t("enabled")}</option><option value="inactive">{t("disabled")}</option></select></label><span className="subtle">{filtered.length} {t("results")}</span></div>
      <div className="table-wrap"><table><thead><tr><th>{t("terminal")}</th><th>{t("oracleDeviceId")}</th><th>{t("inputMethod")}</th><th>{t("structure")}</th><th>{t("browserBinding")}</th><th>{t("status")}</th><th><span className="sr-only">{t("manageTerminal")}</span></th></tr></thead><tbody>{filtered.map(terminal => <tr key={terminal.code}>
        <td><strong>{terminal.name}</strong>{terminal.terminal_role !== "CELL" && <div className="cell-secondary">{t("factoryPerimeter")}</div>}<div className="cell-secondary"><code>{terminal.code}</code></div></td><td><code>{terminal.external_device_id}</code></td><td>{terminal.identification_mode === "BOTH" ? t("readerKeypad") : terminal.identification_mode === "RFID" ? t("badgeReader") : t("keypad")}</td>
        <td>{terminal.structure_path ?? <span className="unconfigured">{t("legacyUnassigned")}</span>}</td>
        <td><span className={`resource-status ${terminal.provisioned ? "is-active" : "is-inactive"}`}><span />{terminal.provisioned ? t("provisioned") : terminal.activation_pending ? t("activationPending") : t("notProvisioned")}</span></td>
        <td><span className={`resource-status ${terminal.active ? "is-active" : "is-inactive"}`}><span />{terminal.active ? t("enabled") : t("disabled")}</span></td><td><div className="table-controls"><button className="text-button" aria-label={`${t("edit")} ${t("terminal")} ${terminal.code}`} onClick={() => setEditor({terminal})}>{t("edit")}</button><button className="text-button" aria-label={`${t("clone")} ${t("terminal")} ${terminal.code}`} disabled={!!cloning} onClick={() => void clone(terminal)}>{cloning === terminal.code ? t("cloning") : t("clone")}</button><button className="text-button" onClick={() => void provision(terminal)}>{terminal.provisioned ? t("reprovision") : t("provision")}</button><button className="text-button delete-button" aria-label={`${t("remove")} ${t("terminal")} ${terminal.code}`} disabled={!!deleting} onClick={() => void remove(terminal)}>{deleting === terminal.code ? t("removing") : t("remove")}</button></div></td>
      </tr>)}</tbody></table></div>
      {!filtered.length && <div className="empty-state"><h3>{t("noTerminalsFound")}</h3><p>{terminals.length ? t("tryDifferentSearch") : t("createTerminalHint")}</p></div>}
    </section>
    {editor && <TerminalEditor terminal={editor.terminal} actions={actions} onClose={() => setEditor(null)} onSaved={terminal => {
      setEditor(null);
      if (terminal.activation_token) { setProvisioning({code: terminal.code, activation_token: terminal.activation_token}); setCopied(false); }
      onChanged(`${t("terminal")} ${terminal.code} ${editor.terminal ? t("terminalUpdated") : t("terminalCreated")}`);
    }} />}
  </>;
}
