import { useEffect, useState } from "react";
import { api } from "../api";
import { NumericKeypad } from "../components/NumericKeypad";
import { useLanguage } from "../i18n";
import type { IdentificationMethod, ScanResponse, TerminalAction, TerminalConfig, TerminalPairingStart, TerminalPairingStatus } from "../types";

const actionVisualKeys = new Set(["factory", "break", "medical", "personal", "legal", "end-work", "no-work"]);

function activationTokenFromLocation(): string {
  if (window.location.pathname !== "/terminal/activate") return "";
  return window.location.hash.replace(/^#/, "").trim();
}

export function TerminalPage() {
  const { language, t } = useLanguage();
  const [config, setConfig] = useState<TerminalConfig | null>(null);
  const [pairing, setPairing] = useState<TerminalPairingStart | null>(null);
  const [badge, setBadge] = useState("");
  const [method, setMethod] = useState<IdentificationMethod>("KEYPAD");
  const [exitActions, setExitActions] = useState<TerminalAction[]>([]);
  const [subactionMode, setSubactionMode] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const requestPairing = async () => {
    setError("");
    try { setPairing(await api.post<TerminalPairingStart>("/api/v1/terminal/pairing", {})); }
    catch (err) { setError((err as Error).message); }
  };

  useEffect(() => {
    const load = async () => {
      try {
        const token = activationTokenFromLocation();
        const value = token ? await api.post<TerminalConfig>("/api/v1/terminal/activate", { token }) : await api.get<TerminalConfig>("/api/v1/terminal/config");
        if (token) window.history.replaceState({}, "", "/terminal");
        setConfig(value);
        if (value.identification_mode === "RFID") setMethod("RFID");
      } catch { await requestPairing(); }
    };
    void load();
  }, []);

  useEffect(() => {
    if (!pairing || config) return;
    let cancelled = false;
    let timer = 0;
    const poll = async () => {
      try {
        const result = await api.post<TerminalPairingStatus>("/api/v1/terminal/pairing/status", { request_token: pairing.request_token });
        if (cancelled) return;
        if (result.status === "APPROVED" && result.config) {
          setConfig(result.config); setPairing(null); setError("");
          if (result.config.identification_mode === "RFID") setMethod("RFID");
          return;
        }
        timer = window.setTimeout(() => void poll(), pairing.poll_after_seconds * 1000);
      } catch (err) {
        if (!cancelled) { setPairing(null); setError((err as Error).message); }
      }
    };
    timer = window.setTimeout(() => void poll(), pairing.poll_after_seconds * 1000);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [pairing, config]);

  const reset = () => { setBadge(""); setExitActions([]); setSubactionMode(false); setBusy(false); };

  const handleResponse = (response: ScanResponse) => {
    if (response.flow === "EXIT_REQUIRED" || response.flow === "SUBACTION_REQUIRED") {
      setExitActions(response.actions);
      setSubactionMode(response.flow === "SUBACTION_REQUIRED");
      setBusy(false);
      return;
    }
    setMessage(response.flow === "ENTRY_RECORDED" ? t("entryRegistered") : t("exitRegistered"));
    setTimeout(() => { setMessage(""); reset(); }, 2200);
  };

  const scan = async () => {
    setBusy(true); setError("");
    try { handleResponse(await api.post<ScanResponse>("/api/v1/terminal/scan", { reporter_id: badge, identification_method: method })); }
    catch (err) { setError((err as Error).message); setBusy(false); }
  };

  const exit = async (actionCode: string) => {
    setBusy(true); setError("");
    try { handleResponse(await api.post<ScanResponse>("/api/v1/terminal/exit", { reporter_id: badge, identification_method: method, action_code: actionCode })); }
    catch (err) { setError((err as Error).message); setBusy(false); }
  };

  if (!config && pairing) return <main className="terminal-shell activation-shell"><section className="panel activation-panel"><img className="activation-logo" src="/img/logobig.png" alt="Hutchinson BSS" /><div className="activation-content"><div className="eyebrow">{t("terminalActivation")}</div><h1>{t("pairBrowser")}</h1><p>{t("pairHelp")}</p><div className="pairing-code" aria-label={pairing.pairing_code}>{pairing.pairing_code}</div><div className="pairing-status"><span className="pairing-pulse" />{t("waitingActivation")}</div><p className="activation-expiry">{t("codeExpires")} {new Date(pairing.expires_at).toLocaleTimeString(language)}.</p></div></section></main>;
  if (!config && error) return <main className="terminal-shell activation-shell"><section className="panel activation-panel"><img className="activation-logo" src="/img/logobig.png" alt="Hutchinson BSS" /><div className="activation-content"><div className="eyebrow">{t("terminalActivation")}</div><h1>{t("terminalNotProvisioned")}</h1><div className="inline-error" role="alert">{error}</div><p>{t("pairingAlternative")}</p><button className="primary" onClick={() => void requestPairing()}>{t("generatePairing")}</button></div></section></main>;
  if (!config) return <main className="terminal-shell activation-shell"><section className="panel activation-panel"><img className="activation-logo" src="/img/logobig.png" alt="Hutchinson BSS" /><div className="activation-content">{t("loadingTerminal")}</div></section></main>;

  return <main className="terminal-shell terminal-operational">
    <header className="terminal-header">
      <div className="terminal-heading">
        <img className="terminal-brand" src="/img/logobig.png" alt="Hutchinson BSS" />
        <div className="terminal-heading-copy"><div className="eyebrow">TIME COLLECTION</div><h1>{config.name}</h1></div>
      </div>
      <div className="terminal-code">{config.code}</div>
    </header>
    <section className="panel terminal-panel">
      {message ? <div className="success-state"><div className="check">✓</div><h2>{message}</h2><p>{t("eventStored")}</p></div> : exitActions.length ? <div>
        <div className="eyebrow">{t("exit")}</div><h2>{subactionMode ? t("selectSubaction") : t("selectExit")}</h2>
        <div className="action-grid">{exitActions.map(action => <button className="action-card" key={action.code} disabled={busy} onClick={() => exit(action.code)}>{action.visual_key && actionVisualKeys.has(action.visual_key) && <img className="action-illustration" src={`/action-visuals/${action.visual_key}.png`} alt="" /> }<span>{action.label}{action.has_subactions ? " ›" : ""}</span></button>)}</div>
        <button className="secondary" onClick={reset} disabled={busy}>{t("cancel")}</button>
      </div> : <>
        <div className="eyebrow">{t("identification")}</div><h2>{t("presentBadge")}</h2>
        {(config.identification_mode === "KEYPAD" || config.identification_mode === "BOTH") && <NumericKeypad value={badge} onChange={setBadge} onSubmit={scan} disabled={busy} placeholder={t("enterBadge")} continueLabel={t("continue")} />}
        {config.identification_mode === "BOTH" && <div className="method-note">{t("keypadNote")}</div>}
        {config.identification_mode === "RFID" && <div className="rfid-placeholder"><img src="/img/rfid-card.svg" alt="Contactless card" /><p>{t("rfidPending")}</p></div>}
      </>}
      {error && config && <div className="inline-error">{error}</div>}
    </section>
  </main>;
}
