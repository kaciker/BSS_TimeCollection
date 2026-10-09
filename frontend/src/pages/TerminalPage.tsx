import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { NumericKeypad } from "../components/NumericKeypad";
import type { IdentificationMethod, ScanResponse, TerminalAction, TerminalConfig } from "../types";

function terminalCodeFromPath(): string {
  const parts = window.location.pathname.split("/").filter(Boolean);
  return parts[0] === "terminal" && parts[1] ? decodeURIComponent(parts[1]) : "DEMO-01";
}

export function TerminalPage() {
  const terminalCode = useMemo(terminalCodeFromPath, []);
  const [config, setConfig] = useState<TerminalConfig | null>(null);
  const [badge, setBadge] = useState("");
  const [method, setMethod] = useState<IdentificationMethod>("KEYPAD");
  const [exitActions, setExitActions] = useState<TerminalAction[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get<TerminalConfig>(`/api/v1/terminal/${encodeURIComponent(terminalCode)}/config`)
      .then((value) => {
        setConfig(value);
        if (value.identification_mode === "RFID") setMethod("RFID");
      })
      .catch((err: Error) => setError(err.message));
  }, [terminalCode]);

  const reset = () => {
    setBadge("");
    setExitActions([]);
    setBusy(false);
  };

  const handleResponse = (response: ScanResponse) => {
    if (response.flow === "EXIT_REQUIRED") {
      setExitActions(response.actions);
      setBusy(false);
      return;
    }
    setMessage(response.flow === "ENTRY_RECORDED" ? "Entry registered" : "Exit registered");
    setTimeout(() => {
      setMessage("");
      reset();
    }, 2200);
  };

  const scan = async () => {
    setBusy(true);
    setError("");
    try {
      handleResponse(await api.post<ScanResponse>(`/api/v1/terminal/${encodeURIComponent(terminalCode)}/scan`, {
        reporter_id: badge,
        identification_method: method,
      }));
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  const exit = async (actionCode: string) => {
    setBusy(true);
    setError("");
    try {
      handleResponse(await api.post<ScanResponse>(`/api/v1/terminal/${encodeURIComponent(terminalCode)}/exit`, {
        reporter_id: badge,
        identification_method: method,
        action_code: actionCode,
      }));
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  if (error && !config) return <main className="terminal-shell"><div className="panel error-panel">{error}</div></main>;
  if (!config) return <main className="terminal-shell"><div className="panel">Loading terminal...</div></main>;

  return (
    <main className="terminal-shell">
      <header className="terminal-header">
        <div>
          <div className="eyebrow">BSS TIME COLLECTION</div>
          <h1>{config.name}</h1>
        </div>
        <div className="terminal-code">{config.code}</div>
      </header>

      <section className="panel terminal-panel">
        {message ? (
          <div className="success-state"><div className="check">✓</div><h2>{message}</h2><p>Your event has been stored.</p></div>
        ) : exitActions.length ? (
          <div>
            <div className="eyebrow">EXIT</div>
            <h2>Select the reason for leaving</h2>
            <div className="action-grid">
              {exitActions.map((action) => <button className="action-card" key={action.code} disabled={busy} onClick={() => exit(action.code)}>{action.label}</button>)}
            </div>
            <button className="secondary" onClick={reset} disabled={busy}>Cancel</button>
          </div>
        ) : (
          <>
            <div className="eyebrow">IDENTIFICATION</div>
            <h2>Present your badge</h2>
            {(config.identification_mode === "KEYPAD" || config.identification_mode === "BOTH") && (
              <NumericKeypad value={badge} onChange={setBadge} onSubmit={scan} disabled={busy} />
            )}
            {config.identification_mode === "BOTH" && <div className="method-note">Manual keypad enabled. RFID adapter can use the same terminal API.</div>}
            {config.identification_mode === "RFID" && <div className="rfid-placeholder">RFID identification is configured for this terminal. Hardware adapter integration is pending.</div>}
          </>
        )}
        {error && config && <div className="inline-error">{error}</div>}
      </section>
    </main>
  );
}
