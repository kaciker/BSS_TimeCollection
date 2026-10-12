import { useEffect, useState } from "react";
import { api } from "../api";
import { NumericKeypad } from "../components/NumericKeypad";
import type { IdentificationMethod, ScanResponse, TerminalAction, TerminalConfig, TerminalPairingStart, TerminalPairingStatus } from "../types";

function activationTokenFromLocation(): string {
  if (window.location.pathname !== "/terminal/activate") return "";
  return window.location.hash.replace(/^#/, "").trim();
}

export function TerminalPage() {
  const [config, setConfig] = useState<TerminalConfig | null>(null);
  const [pairing, setPairing] = useState<TerminalPairingStart | null>(null);
  const [badge, setBadge] = useState("");
  const [method, setMethod] = useState<IdentificationMethod>("KEYPAD");
  const [exitActions, setExitActions] = useState<TerminalAction[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const requestPairing = async () => {
    setError("");
    try {
      setPairing(await api.post<TerminalPairingStart>("/api/v1/terminal/pairing", {}));
    } catch (err) {
      setError((err as Error).message);
    }
  };

  useEffect(() => {
    const load = async () => {
      try {
        const token = activationTokenFromLocation();
        const value = token
          ? await api.post<TerminalConfig>("/api/v1/terminal/activate", { token })
          : await api.get<TerminalConfig>("/api/v1/terminal/config");
        if (token) window.history.replaceState({}, "", "/terminal");
        setConfig(value);
        if (value.identification_mode === "RFID") setMethod("RFID");
      } catch {
        await requestPairing();
      }
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
          setConfig(result.config);
          setPairing(null);
          setError("");
          if (result.config.identification_mode === "RFID") setMethod("RFID");
          return;
        }
        timer = window.setTimeout(() => void poll(), pairing.poll_after_seconds * 1000);
      } catch (err) {
        if (!cancelled) {
          setPairing(null);
          setError((err as Error).message);
        }
      }
    };
    timer = window.setTimeout(() => void poll(), pairing.poll_after_seconds * 1000);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [pairing, config]);

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
      handleResponse(await api.post<ScanResponse>("/api/v1/terminal/scan", {
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
      handleResponse(await api.post<ScanResponse>("/api/v1/terminal/exit", {
        reporter_id: badge,
        identification_method: method,
        action_code: actionCode,
      }));
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  if (!config && pairing) return <main className="terminal-shell"><div className="panel"><div className="eyebrow">TERMINAL ACTIVATION</div><h2>Pair this browser</h2><p>Enter this temporary code in Administration and assign it to the terminal you want to use.</p><div className="terminal-code">{pairing.pairing_code}</div><p>Waiting for activation…</p><p className="subtle">This code expires at {new Date(pairing.expires_at).toLocaleTimeString()}.</p></div></main>;
  if (!config && error) return <main className="terminal-shell"><div className="panel error-panel"><h2>Terminal not provisioned</h2><p>{error}</p><p>You can still use the existing one-time activation link, or generate a new pairing code from this browser.</p><button className="primary" onClick={() => void requestPairing()}>Generate pairing code</button></div></main>;
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
            {config.identification_mode === "BOTH" && <div className="method-note">Manual keypad enabled. RFID adapter can use the same terminal session.</div>}
            {config.identification_mode === "RFID" && <div className="rfid-placeholder">RFID identification is configured for this terminal. Hardware adapter integration is pending.</div>}
          </>
        )}
        {error && config && <div className="inline-error">{error}</div>}
      </section>
    </main>
  );
}
