import { useEffect, useState } from "react";
import type { MouseEvent } from "react";
import { api } from "../api";
import { useLanguage } from "../i18n";
import type { AdminAction, AdminTerminal } from "../types";
import { MonitoringPanel } from "../components/MonitoringPanel";
import { ActionList } from "../components/admin/ActionList";
import { DatabasePanel } from "../components/admin/DatabasePanel";
import { PoliciesPanel } from "../components/admin/PoliciesPanel";
import { PerimeterPanel } from "../components/admin/PerimeterPanel";
import { SettingsPanel } from "../components/admin/SettingsPanel";
import { TerminalList } from "../components/admin/TerminalList";
import { StructurePanel } from "../components/admin/StructurePanel";

type Section = "cards" | "events" | "attempts" | "terminals" | "structure" | "actions" | "database" | "settings" | "policies" | "perimeter";

function sectionFromPath(): Section {
  const section = window.location.pathname.split("/")[2] as Section;
  return ["cards","events","attempts","terminals","structure","actions","database","settings","policies","perimeter"].includes(section) ? section : "cards";
}

function NavIcon({name}: {name: string}) {
  const paths: Record<string, string> = {
    badge: "M4 5h16v14H4z M8 9h3v3H8z M14 9h3 M14 12h3 M8 16h9", events: "M7 3h10v18H7z M10 7h4 M10 11h4 M10 15h4", transmission: "M3 7h14 M13 3l4 4-4 4 M21 17H7 M11 13l-4 4 4 4", terminal: "M3 4h18v13H3z M8 21h8 M12 17v4", structure: "M3 3h7v7H3z M14 3h7v7h-7z M8 14h8v7H8z", actions: "M4 6h16 M4 12h16 M4 18h16 M8 3v6 M16 9v6 M10 15v6", perimeter: "M4 4h16v16H4z M8 4v16 M16 4v16", policies: "M5 12h14 M12 5v14 M5 5h14v14H5z", database: "M5 5c0-2 14-2 14 0s-14 2-14 0v14c0 2 14 2 14 0V5 M5 12c0 2 14 2 14 0", settings: "M12 3v3 M12 18v3 M3 12h3 M18 12h3 M5.6 5.6l2.1 2.1 M16.3 16.3l2.1 2.1 M18.4 5.6l-2.1 2.1 M7.7 16.3l-2.1 2.1 M9 12a3 3 0 1 0 6 0 3 3 0 0 0-6 0",
  };
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}

export function AdminPage() {
  const { t } = useLanguage();
  const pages: Record<Section, {title:string; description:string; group:string; icon:string}> = {
    cards: { title:t("badgeStatus"), description:t("badgeStatusDesc"), group:t("operations"), icon:"badge" }, events:{ title:t("eventLogs"), description:t("eventLogsDesc"), group:t("operations"), icon:"events" }, attempts:{ title:t("transmissionLogs"), description:t("transmissionLogsDesc"), group:t("operations"), icon:"transmission" }, terminals:{ title:t("terminals"), description:t("terminalsDesc"), group:t("configuration"), icon:"terminal" }, structure:{ title:"Structure", description:"", group:t("configuration"), icon:"structure" }, actions:{ title:t("actions"), description:t("actionsDesc"), group:t("configuration"), icon:"actions" }, perimeter:{ title:"Factory Perimeter", description:"Badge presence and duplicate scan policy.", group:t("configuration"), icon:"perimeter" }, policies:{ title:"Policies", description:"Configure global and per-terminal operational restrictions.", group:t("configuration"), icon:"policies" }, database:{ title:t("database"), description:t("databaseDesc"), group:t("configuration"), icon:"database" }, settings:{ title:t("settings"), description:t("settingsDesc"), group:t("configuration"), icon:"settings" },
  };
  const [section, setSection] = useState<Section>(sectionFromPath);
  const [terminals, setTerminals] = useState<AdminTerminal[]>([]); const [actions, setActions] = useState<AdminAction[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState(""); const [notice, setNotice] = useState("");
  const refresh = async () => { try { const [terminalData, actionData] = await Promise.all([api.get<AdminTerminal[]>("/api/v1/admin/terminals"), api.get<AdminAction[]>("/api/v1/admin/actions")]); setTerminals(terminalData); setActions(actionData); setError(""); } catch (err) { setError((err as Error).message); } finally { setLoading(false); } };
  useEffect(() => { void refresh(); const back = () => { setSection(sectionFromPath()); setNotice(""); }; window.addEventListener("popstate", back); return () => window.removeEventListener("popstate", back); }, []);
  const navigate = (event: MouseEvent<HTMLAnchorElement>, next: Section) => { if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return; event.preventDefault(); window.history.pushState({}, "", `/admin/${next}`); setSection(next); setNotice(""); window.scrollTo(0,0); };
  const changed = (message: string) => { setNotice(message); void refresh(); };
  const groups = [t("operations"), t("configuration")];
  return <div className="admin-layout"><aside className="admin-sidebar">
    <a href="/admin/cards" className="admin-brand" aria-label="Hutchinson BSS Time Collection" onClick={event => navigate(event,"cards")}><img src="/img/logobig.png" alt="Hutchinson BSS" /><span className="admin-brand-caption">TIME COLLECTION</span></a>
    <div className="workspace-label"><span className="status-dot" /> {t("administration")}</div>
    <nav aria-label="Administration navigation">{groups.map(group => <div className="nav-group" key={group}><div className="nav-label">{group}</div>{(Object.keys(pages) as Section[]).filter(key => pages[key].group === group).map(key => <a key={key} href={`/admin/${key}`} className={section === key ? "active" : ""} aria-current={section === key ? "page" : undefined} onClick={event => navigate(event,key)}><NavIcon name={pages[key].icon} />{pages[key].title}</a>)}</div>)}</nav>
    <div className="sidebar-footer"><span className="brand-mark small">B</span><div>BSS Time Collection<small>Factory capture platform</small></div></div>
  </aside><div className="admin-main"><header className="admin-topbar"><span>{t("administration")} <span className="breadcrumb-separator">/</span> <strong>{pages[section].title}</strong></span><span className="topbar-label">BSS · Time Collection</span></header>
    <main className="admin-content"><div className="page-heading"><div className="eyebrow">{pages[section].group}</div><h1>{pages[section].title}</h1>{pages[section].description&&<p>{pages[section].description}</p>}</div>
      {notice && <div className="success-notice" role="status"><span aria-hidden="true">✓</span>{notice}<button className="icon-button" aria-label="Dismiss notification" onClick={() => setNotice("")}>×</button></div>}
      {error && <div className="inline-error" role="alert">{error} <button className="text-button" onClick={() => void refresh()}>{t("retry")}</button></div>}
      {loading ? <div className="admin-card loading-state" role="status">{t("loadingConfiguration")}</div> : section === "terminals" ? <TerminalList key="terminals" terminals={terminals} actions={actions} onChanged={changed} /> : section === "structure" ? <StructurePanel key="structure" /> : section === "actions" ? <ActionList key="actions" terminals={terminals} actions={actions} onChanged={changed} /> : section === "policies" ? <PoliciesPanel key="policies" /> : section === "perimeter" ? <PerimeterPanel key="perimeter" terminals={terminals} /> : section === "database" ? <DatabasePanel key="database" /> : section === "settings" ? <SettingsPanel key="settings" /> : <MonitoringPanel key={section} terminals={terminals} initialView={section} onNavigate={(next, query = "") => { window.history.pushState({}, "", `/admin/${next}${query}`); setSection(next); }} />}
    </main></div></div>;
}
