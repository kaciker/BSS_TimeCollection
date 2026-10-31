import { Fragment, useEffect, useRef, useState } from "react";
import type { CSSProperties, FormEvent, ReactNode } from "react";
import { api } from "../api";
import type { AdminTerminal } from "../types";
import { EventInspector } from "./EventInspector";
import { dateLabel, Status } from "./monitoringTypes";
import type { AttemptSummary, CardState, EventDetail, EventSnapshot, Page } from "./monitoringTypes";
import { useLanguage } from "../i18n";

type View = "cards" | "events" | "attempts";
const statuses = ["PENDING", "SENDING", "RETRY", "SENT", "REJECTED", "UNKNOWN"];
const initialFilters = { clock: "", badge: "", state: "", factoryState: "", status: "", start: "", end: "" };
const pageSize = 50;

export function MonitoringPanel({ terminals, initialView = "cards", onNavigate }: { terminals: AdminTerminal[]; initialView?: View; onNavigate?: (view: View, query?: string) => void }) {
  const { t, language } = useLanguage();
  const employeeIdLabel = language === "es" ? "N.º empleado" : "Employee ID";
  const readerIdLabel = language === "es" ? "ID lector" : "Reader ID";
  const cardLabel = language === "es" ? "Tarjeta" : "Card";
  const identitySearchLabel = language === "es" ? "Empleado / lector / tarjeta" : "Employee / reader / card";
  const identitySearchPlaceholder = language === "es" ? "Buscar empleado, RFID o tarjeta" : "Search employee, RFID or card";
  const [view, setView] = useState<View>(initialView);
  const [hiddenColumns, setHiddenColumns] = useState<Record<string, string[]>>(() => {
    try { const stored = JSON.parse(localStorage.getItem("bss-admin-hidden-columns") ?? "{}"); return stored && typeof stored === "object" && !Array.isArray(stored) ? stored : {}; } catch { return {}; }
  });
  const columnText = ({en: ["Columns", "Show all", "Always visible", "Show column"], es: ["Columnas", "Mostrar todas", "Siempre visible", "Mostrar columna"], fr: ["Colonnes", "Tout afficher", "Toujours visible", "Afficher la colonne"], pl: ["Kolumny", "Pokaż wszystkie", "Zawsze widoczne", "Pokaż kolumnę"]})[language];
  const saveColumns = (next: Record<string, string[]>) => { setHiddenColumns(next); try { localStorage.setItem("bss-admin-hidden-columns", JSON.stringify(next)); } catch {} };
  const toggleColumn = (id: string) => {
    if (id === "employee" || (view === "attempts" && id === "reader")) return;
    const hidden = Array.isArray(hiddenColumns[view]) ? hiddenColumns[view] : [];
    saveColumns({...hiddenColumns, [view]: hidden.includes(id) ? hidden.filter(value => value !== id) : [...hidden, id]});
  };
  const [draft, setDraft] = useState(() => {
    const query = new URLSearchParams(window.location.search);
    return { ...initialFilters, badge: query.get("badge") ?? "", clock: query.get("clock") ?? "" };
  });
  const [filters, setFilters] = useState(draft);
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [data, setData] = useState<Page<EventSnapshot | CardState | AttemptSummary>>({ items: [], total: 0 });
  const [factoryEnabled, setFactoryEnabled] = useState(false);
  const [dataView, setDataView] = useState<View>(initialView);
  const items = dataView === view ? data.items : [];
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [updated, setUpdated] = useState<string | null>(null);
  const [historicalClocks, setHistoricalClocks] = useState<string[]>([]);
  const [detail, setDetail] = useState<EventDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const detailRequest = useRef(0);
  const detailDialog = useRef<HTMLDialogElement>(null);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const detailOpen = view !== "events" && (detailLoading || !!detail);
  const inlineDetail = <div id="event-inline-details" className="inline-event-detail">{detailLoading && <div role="status">{t("loadingDetails")}</div>}{detail && <EventInspector detail={detail} onClose={closeDetail} />}</div>;

  useEffect(() => {
    const dialog = detailDialog.current;
    if (!dialog) return;
    const previousOverflow = document.body.style.overflow;
    if (detailOpen) {
      if (!dialog.open) {
        if (typeof dialog.showModal === "function") dialog.showModal();
        else dialog.setAttribute("open", "");
      }
      document.body.style.overflow = "hidden";
    } else {
      if (dialog.open) {
        if (typeof dialog.close === "function") dialog.close();
        else dialog.removeAttribute("open");
      }
      document.body.style.overflow = previousOverflow;
    }
    return () => { if (detailOpen) document.body.style.overflow = previousOverflow; };
  }, [detailOpen]);

  useEffect(() => {
    void api.get<string[]>("/api/v1/admin/monitoring/clocks").then(setHistoricalClocks).catch(() => {});
  }, []);
  const activeCodes = new Set(terminals.map(terminal => terminal.code));
  const removedCodes = historicalClocks.filter(code => !activeCodes.has(code));

  useEffect(() => {
    let active = true;
    let pending = false;
    const query = new URLSearchParams({ offset: String(offset), limit: String(pageSize) });
    if (filters.clock) query.set("terminal_code", filters.clock);
    if (filters.badge) query.set("reporter_id", filters.badge);
    if (view === "cards" && filters.state) query.set("worker_state", filters.state);
    if (view === "cards" && filters.factoryState) query.set("factory_state", filters.factoryState);
    if (view !== "cards" && filters.status) query.set(view === "events" ? "delivery_status" : "result", filters.status);
    if (view === "events") {
      if (filters.start) query.set("start", new Date(filters.start).toISOString());
      if (filters.end) query.set("end", new Date(filters.end).toISOString());
    }
    setData({ items: [], total: 0 });
    setLoading(true);
    const refresh = async () => {
      if (pending) return;
      pending = true;
      try {
        const result = await api.get<Page<EventSnapshot | CardState | AttemptSummary>>(`/api/v1/admin/monitoring/${view}?${query}`);
        if (active) { setData(result); if (view === "cards") setFactoryEnabled(!!result.factory_perimeter_enabled); setDataView(view); setError(""); setUpdated(new Date().toISOString()); }
      } catch (err) { if (active) setError((err as Error).message); }
      finally { pending = false; if (active) setLoading(false); }
    };
    void refresh();
    const interval = window.setInterval(() => void refresh(), 15000);
    return () => { active = false; window.clearInterval(interval); };
  }, [view, filters, offset, revision]);

  const selectView = (next: View) => { setView(next); setOffset(0); closeDetail(); };
  const apply = (event: FormEvent) => { event.preventDefault(); closeDetail(); setFilters({ ...draft }); setOffset(0); };
  function closeDetail() { detailRequest.current++; setSelectedEventId(null); setDetail(null); setDetailLoading(false); }
  const inspect = async (id: string) => {
    if (view === "events" && selectedEventId === id) { closeDetail(); return; }
    setSelectedEventId(id);
    const request = ++detailRequest.current;
    setDetail(null); setDetailLoading(true);
    try {
      const result = await api.get<EventDetail>(`/api/v1/admin/monitoring/events/${encodeURIComponent(id)}`);
      if (request === detailRequest.current) setDetail(result);
    } catch (err) { if (request === detailRequest.current) { setError((err as Error).message); setSelectedEventId(null); } }
    finally { if (request === detailRequest.current) setDetailLoading(false); }
  };
  const history = (badge: string) => {
    const next = { ...filters, badge, start: "", end: "", status: "" };
    if (onNavigate) {
      onNavigate("events", `?badge=${encodeURIComponent(badge)}&clock=${encodeURIComponent(filters.clock)}`);
    } else { setDraft(next); setFilters(next); selectView("events"); }
  };
  const badgeStatus = (value: string) => <span className={`status ${value === "INSIDE" ? "status-sent" : ""}`}>{value === "INSIDE" ? t("inside") : t("outside")}</span>;

  type Column = { id: string; label: string; width: number; locked?: boolean; render: (item: any) => ReactNode };
  const detailButton = (id: string) => <button aria-expanded={view === "events" ? selectedEventId === id : undefined} aria-controls={selectedEventId === id ? "event-inline-details" : undefined} onClick={() => void inspect(id)}>{view === "events" && selectedEventId === id ? t("closeDetails") : t("details")}</button>;
  const columns: Column[] = view === "events" ? [
    {id:"time",label:t("eventTime"),width:190,render:e=>dateLabel(e.event_datetime)},
    {id:"employee",label:employeeIdLabel,width:130,locked:true,render:e=><strong>{e.person_id ?? "—"}</strong>},
    {id:"clock",label:t("clock"),width:110,render:e=>e.terminal_code},
    {id:"reader",label:readerIdLabel,width:160,render:e=>e.reporter_id},
    {id:"card",label:cardLabel,width:330,render:e=>e.credential_id ?? "—"},
    {id:"action",label:t("action"),width:310,render:e=><>{e.action_label}<span className="event-context"> · {e.event_kind === "PERIMETER" ? `${t("factoryPerimeter")} · ${e.factory_code}` : t("cell")}</span></>},
    {id:"effect",label:t("effect"),width:100,render:e=>e.state_effect},
    {id:"delivery",label:t("delivery"),width:130,render:e=><Status value={e.delivery_status} />},
    {id:"attempts",label:t("attemptsLabel"),width:100,render:e=>e.attempt_count},
    {id:"inspect",label:t("inspect"),width:130,render:e=>detailButton(e.id)},
  ] : view === "cards" ? [
    {id:"employee",label:employeeIdLabel,width:130,locked:true,render:c=><strong>{c.person_id ?? c.event.person_id ?? "—"}</strong>},
    {id:"reader",label:readerIdLabel,width:160,render:c=>c.reporter_id},
    {id:"card",label:cardLabel,width:330,render:c=>c.credential_id ?? c.event.credential_id ?? "—"},
    {id:"cellState",label:t("cellState"),width:110,render:c=>badgeStatus(c.worker_state)},
    ...(factoryEnabled ? [{id:"factoryState",label:t("factoryState"),width:140,render:(c: CardState)=>c.factory_state ? <>{badgeStatus(c.factory_state)}<div className="cell-secondary">{c.factory_code}</div></> : <span className="muted">{t("notActivated")}</span>}] : []),
    {id:"clock",label:t("latestClock"),width:140,render:c=>c.event.terminal_code},
    {id:"time",label:t("latestEvent"),width:190,render:c=>dateLabel(c.event.event_datetime)},
    {id:"action",label:t("action"),width:240,render:c=>c.event.action_label},
    {id:"delivery",label:t("delivery"),width:130,render:c=><Status value={c.event.delivery_status} />},
    {id:"inspect",label:t("inspect"),width:170,render:c=><>{detailButton(c.event.id)}<button onClick={()=>history(c.reporter_id)}>{t("history")}</button></>},
  ] : [
    {id:"time",label:t("attemptTime"),width:190,render:a=>dateLabel(a.started_at)},
    {id:"clock",label:t("clock"),width:110,render:a=>a.terminal_code},
    {id:"reader",label:t("badge"),width:160,locked:true,render:a=>a.reporter_id},
    {id:"attempts",label:t("attempt"),width:100,render:a=>a.attempt_number},
    {id:"delivery",label:t("result"),width:130,render:a=><Status value={a.result} />},
    {id:"http",label:t("http"),width:100,render:a=>a.http_status ?? "—"},
    {id:"duration",label:t("duration"),width:110,render:a=>`${a.duration_ms} ms`},
    {id:"inspect",label:t("inspect"),width:130,render:a=>detailButton(a.event_id)},
  ];
  const hidden = Array.isArray(hiddenColumns[view]) ? hiddenColumns[view] : [];
  const visibleColumns = columns.filter(column => column.locked || !hidden.includes(column.id));

  return <>
    <section className="admin-card monitoring">
      <div className="monitor-heading"><div><h2>{view === "cards" ? t("badgeRegister") : view === "events" ? t("capturedEvents") : t("deliveryAttempts")}</h2></div><button className="secondary" onClick={() => setRevision(value => value + 1)}>{t("refresh")}</button></div>
      <form className="monitor-filters" onSubmit={apply}>
        <label>{t("clock")}<select value={draft.clock} onChange={e => setDraft({ ...draft, clock: e.target.value })}><option value="">{t("allClocks")}</option>{terminals.map(terminal => <option key={terminal.code} value={terminal.code}>{terminal.code} · {terminal.name}</option>)}{removedCodes.map(code => <option key={code} value={code}>{code} · {t("removed")}</option>)}</select></label>
        <label>{identitySearchLabel}<input value={draft.badge} placeholder={identitySearchPlaceholder} onChange={e => setDraft({ ...draft, badge: e.target.value })} /></label>
        {view === "cards" ? <label>{t("cellState")}<select value={draft.state} onChange={e => setDraft({ ...draft, state: e.target.value })}><option value="">{t("all")}</option><option value="INSIDE">{t("inside")}</option><option value="OUTSIDE">{t("outside")}</option></select></label> : <label>{view === "events" ? t("delivery") : t("attemptResult")}<select value={draft.status} onChange={e => setDraft({ ...draft, status: e.target.value })}><option value="">{t("all")}</option>{(view === "events" ? [...statuses,"LOCAL_ONLY"] : statuses).map(status => <option key={status} value={status}>{status === "LOCAL_ONLY" ? t("localOnly") : status}</option>)}</select></label>}
        {view === "cards" && factoryEnabled && <label>{t("factoryState")}<select value={draft.factoryState} onChange={e => setDraft({ ...draft, factoryState: e.target.value })}><option value="">{t("all")}</option><option value="INSIDE">{t("inside")}</option><option value="OUTSIDE">{t("outside")}</option></select></label>}
        {view === "events" && <><label>{t("from")}<input type="datetime-local" value={draft.start} onChange={e => setDraft({ ...draft, start: e.target.value })} /></label><label>{t("to")}<input type="datetime-local" value={draft.end} onChange={e => setDraft({ ...draft, end: e.target.value })} /></label></>}
        <button className="primary" type="submit">{t("applyFilters")}</button>
        <button className="secondary" type="button" onClick={() => { closeDetail(); setDraft(initialFilters); setFilters({ ...initialFilters }); setOffset(0); }}>{t("reset")}</button>
      </form>
      <p className="muted">{view === "cards" ? t("monitoringCellHelp") : view === "events" ? t("eventsStoredHelp") : t("attemptsHelp")}</p>
      <p className="monitor-count" aria-live="polite">{loading ? t("loading") : `${data.total} ${view === "cards" ? t("badges") : view === "events" ? t("events") : t("attempts")}`}<span className="muted">{t("autoRefresh")} · {dateLabel(updated)}</span></p>
      {error && <div className="inline-error" role="alert">{error}</div>}
      <details className="column-picker">
        <summary>{columnText[0]} <span className="subtle">{visibleColumns.length}/{columns.length}</span></summary>
        <fieldset><legend className="sr-only">{columnText[0]}</legend>{columns.map(column=><label key={column.id}><input type="checkbox" aria-label={`${columnText[3]}: ${column.label}`} checked={visibleColumns.includes(column)} disabled={column.locked} onChange={()=>toggleColumn(column.id)} />{column.label}{column.locked && <small>{columnText[2]}</small>}</label>)}</fieldset>
        <button className="text-button" onClick={()=>saveColumns({...hiddenColumns,[view]:[]})}>{columnText[1]}</button>
      </details>
      <p className="table-scroll-hint">{({ en: "Scroll horizontally to see all columns.", es: "Desplázate horizontalmente para ver todas las columnas.", fr: "Faites défiler horizontalement pour voir toutes les colonnes.", pl: "Przewiń poziomo, aby zobaczyć wszystkie kolumny." })[language]}</p>
      <div className={`table-wrap monitoring-table-wrap ${view}-table-wrap`} tabIndex={0} role="region" aria-label={t(view === "events" ? "eventLogs" : view === "cards" ? "badgeRegister" : "deliveryAttempts")}>
        <table className={view === "events" ? "events-table configurable-table" : "configurable-table"} style={{minWidth:visibleColumns.reduce((sum,column)=>sum+column.width,0), "--event-employee-left": visibleColumns.some(column=>column.id === "time") ? "190px" : "0px"} as CSSProperties}>
          <colgroup>{visibleColumns.map(column=><col key={column.id} style={{width:column.width}} />)}</colgroup>
          <thead><tr>{visibleColumns.map(column=><th key={column.id} data-column={column.id}>{column.label}</th>)}</tr></thead>
          <tbody>{items.map(item=>{
            const id = view === "cards" ? (item as CardState).reporter_id : String((item as EventSnapshot | AttemptSummary).id);
            return <Fragment key={id}><tr className={view === "events" && selectedEventId === id ? "selected-event" : undefined}>{visibleColumns.map(column=><td key={column.id} data-column={column.id} className={column.id === "inspect" ? "row-actions" : undefined}>{column.render(item)}</td>)}</tr>
              {view === "events" && selectedEventId === id && <tr className="event-detail-row"><td colSpan={visibleColumns.length}>{inlineDetail}</td></tr>}
            </Fragment>;
          })}</tbody>
        </table>
      </div>
      {!loading && !items.length && <p className="empty-state">{view === "attempts" ? t("noAttempts") : t("noResults")}</p>}
      <div className="pagination"><button className="secondary" disabled={loading || offset === 0} onClick={() => { closeDetail(); setOffset(Math.max(0, offset - pageSize)); }}>{t("previous")}</button><span>{data.total ? `${offset + 1}–${Math.min(offset + pageSize, data.total)} ${t("of")} ${data.total}` : `0 ${t("results")}`}</span><button className="secondary" disabled={loading || offset + pageSize >= data.total} onClick={() => { closeDetail(); setOffset(offset + pageSize); }}>{t("next")}</button></div>
    </section>
    <dialog ref={detailDialog} className="event-modal-dialog" aria-label={t("eventDetails")} onCancel={event => { event.preventDefault(); closeDetail(); }} onKeyDown={event => { if (event.key === "Escape") closeDetail(); }} onClick={event => { if (event.target === event.currentTarget) closeDetail(); }}>
      <div className="event-modal">
        {detailLoading && <div className="admin-card" role="status">{t("loadingDetails")}</div>}
        {detail && <EventInspector detail={detail} onClose={closeDetail} />}
      </div>
    </dialog>
  </>;
}
