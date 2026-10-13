import { useEffect, useState } from "react";

export function TerminalClock({ recordedAt }: { recordedAt: string | null }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    let timer = 0;
    const tick = () => {
      setNow(Date.now());
      timer = window.setTimeout(tick, 1000 - Date.now() % 1000);
    };
    tick();
    const resume = () => {
      if (!document.hidden) { window.clearTimeout(timer); tick(); }
    };
    document.addEventListener("visibilitychange", resume);
    return () => { window.clearTimeout(timer); document.removeEventListener("visibilitychange", resume); };
  }, []);

  // Confirmation shows the actual timestamp returned by the capture API.
  const date = new Date(recordedAt ?? now);
  const digits = [date.getHours(), date.getMinutes(), date.getSeconds()]
    .map(value => String(value).padStart(2, "0")).join(":");
  return <div className="terminal-clock"><time dateTime={date.toISOString()} aria-label={recordedAt ? "Recorded event time" : "Current time"} aria-live="off">{digits}</time></div>;
}
