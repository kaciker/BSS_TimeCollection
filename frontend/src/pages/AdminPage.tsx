import { useEffect, useState } from "react";
import type { MouseEvent } from "react";
import { api } from "../api";
import type { AdminAction, AdminTerminal } from "../types";
import { MonitoringPanel } from "../components/MonitoringPanel";
import { TerminalList } from "../components/admin/TerminalList";
import { ActionList } from "../components/admin/ActionList";

const pages = {
  cards: { title: "Badge status", description: "Current local state of each badge, derived from its latest captured event.", group: "OPERATIONS", icon: "badge" },
  events: { title: "Event logs", description: "Inspect captured events, stored facts and Oracle delivery status.", group: "OPERATIONS", icon: "events" },
  attempts: { title: "Transmission logs", description: "Review every Oracle transmission attempt and its recorded response.", group: "OPERATIONS", icon: "transmission" },
  terminals: { title: "Terminals", description: "Manage factory clocks, identification methods and assigned worker actions.", group: "CONFIGURATION", icon: "terminal" },
  actions: { title: "Actions", description: "Configure worker actions, English labels and Oracle supplier event mappings.", group: "CONFIGURATION", icon: "actions" },
} as const;
type Section = keyof typeof pages;
function sectionFromPath(): Section {
  const section = window.location.pathname.split("/")[2];
  return section in pages ? section as Section : "cards";
}
function NavIcon({name}: {name: string}) {
  const paths: Record<string, string> = {
    badge: "M4 5h16v14H4z M8 9h3v3H8z M14 9h3 M14 12h3 M8 16h9",
    events: "M7 3h10v18H7z M10 7h4 M10 11h4 M10 15h4",
    transmission: "M3 7h14 M13 3l4 4-4 4 M21 17H7 M11 13l-4 4 4 4",
    terminal: "M3 4h18v13H3z M8 21h8 M12 17v4",
    actions: "M4 6h16 M4 12h16 M4 18h16 M8 3v6 M16 9v6 M10 15v6",
  };
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}

export function AdminPage() {
  const [section, setSection] = useState<Section>(sectionFromPath);
  const [terminals, setTerminals] = useState<AdminTerminal[]>([]);
  const [actions, setActions] = useState<AdminAction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const refresh = async () => {
    try {
      const [terminalData, actionData] = await Promise.all([
        api.get<AdminTerminal[]>("/api/v1/admin/terminals"), api.get<AdminAction[]>("/api/v1/admin/actions"),
      ]);
      setTerminals(terminalData); setActions(actionData); setError("");
    } catch (err) { setError((err as Error).message); }
    finally { setLoading(false); }
  };
  useEffect(() => { void refresh(); const back = () => { setSection(sectionFromPath()); setNotice(""); }; window.addEventListener("popstate", back); return () => window.removeEventListener("popstate", back); }, []);
  const navigate = (event: MouseEvent<HTMLAnchorElement>, next: Section) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault(); window.history.pushState({}, "", `/admin/${next}`); setSection(next); setNotice(""); window.scrollTo(0,0);
  };
  const changed = (message: string) => { setNotice(message); void refresh(); };
  return <div className="admin-layout">
    <aside className="admin-sidebar">
      <a href="/admin/cards" className="admin-brand" onClick={event => navigate(event,"cards")}><span className="brand-mark">B</span><span><strong>BSS</strong><small>TIME COLLECTION</small></span></a>
      <div className="workspace-label"><span className="status-dot" /> Administration</div>
      <nav aria-label="Administration navigation">{["OPERATIONS","CONFIGURATION"].map(group => <div className="nav-group" key={group}><div className="nav-label">{group}</div>{(Object.keys(pages) as Section[]).filter(key => pages[key].group === group).map(key => <a key={key} href={`/admin/${key}`} className={section === key ? "active" : ""} aria-current={section === key ? "page" : undefined} onClick={event => navigate(event,key)}><NavIcon name={pages[key].icon} />{pages[key].title}</a>)}</div>)}</nav>
      <div className="sidebar-footer"><span className="brand-mark small">B</span><div>BSS Time Collection<small>Factory capture platform</small></div></div>
    </aside>
    <div className="admin-main"><header className="admin-topbar"><span>Administration <span className="breadcrumb-separator">/</span> <strong>{pages[section].title}</strong></span><span className="topbar-label">BSS · Time Collection</span></header>
      <main className="admin-content"><div className="page-heading"><div className="eyebrow">{pages[section].group}</div><h1>{pages[section].title}</h1><p>{pages[section].description}</p></div>
        {notice && <div className="success-notice" role="status"><span aria-hidden="true">✓</span>{notice}<button className="icon-button" aria-label="Dismiss notification" onClick={() => setNotice("")}>×</button></div>}
        {error && <div className="inline-error" role="alert">{error} <button className="text-button" onClick={() => void refresh()}>Retry</button></div>}
        {loading ? <div className="admin-card loading-state" role="status">Loading configuration…</div> : section === "terminals" ? <TerminalList key="terminals" terminals={terminals} actions={actions} onChanged={changed} /> : section === "actions" ? <ActionList key="actions" terminals={terminals} actions={actions} onChanged={changed} /> : <MonitoringPanel key={section} terminals={terminals} initialView={section} onNavigate={(next, query = "") => { window.history.pushState({}, "", `/admin/${next}${query}`); setSection(next); }} />}
      </main>
    </div>
  </div>;
}
