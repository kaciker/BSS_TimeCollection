import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
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
  const [view, setView] = useState<View>(initialView);
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
  const apply = (event: FormEvent) => { event.preventDefault(); setFilters({ ...draft }); setOffset(0); };
  const closeDetail = () => { detailRequest.current++; setDetail(null); setDetailLoading(false); };
  const inspect = async (id: string) => {
    const request = ++detailRequest.current;
    setDetail(null); setDetailLoading(true);
    try {
      const result = await api.get<EventDetail>(`/api/v1/admin/monitoring/events/${encodeURIComponent(id)}`);
      if (request === detailRequest.current) setDetail(result);
    } catch (err) { if (request === detailRequest.current) setError((err as Error).message); }
    finally { if (request === detailRequest.current) setDetailLoading(false); }
  };
  const history = (badge: string) => {
    const next = { ...filters, badge, start: "", end: "", status: "" };
    if (onNavigate) {
      onNavigate("events", `?badge=${encodeURIComponent(badge)}&clock=${encodeURIComponent(filters.clock)}`);
    } else { setDraft(next); setFilters(next); selectView("events"); }
  };
  const badgeStatus = (value: string) => <span className={`status ${value === "INSIDE" ? "status-sent" : ""}`}>{value === "INSIDE" ? t("inside") : t("outside")}</span>;

  return <>
    <section className="admin-card monitoring">
      <div className="monitor-heading"><div><h2>{view === "cards" ? t("badgeRegister") : view === "events" ? t("capturedEvents") : t("deliveryAttempts")}</h2></div><button className="secondary" onClick={() => setRevision(value => value + 1)}>{t("refresh")}</button></div>
      <form className="monitor-filters" onSubmit={apply}>
        <label>{t("clock")}<select value={draft.clock} onChange={e => setDraft({ ...draft, clock: e.target.value })}><option value="">{t("allClocks")}</option>{terminals.map(terminal => <option key={terminal.code} value={terminal.code}>{terminal.code} · {terminal.name}</option>)}{removedCodes.map(code => <option key={code} value={code}>{code} · {t("removed")}</option>)}</select></label>
        <label>{t("badgeNumber")}<input value={draft.badge} placeholder={t("searchBadge")} onChange={e => setDraft({ ...draft, badge: e.target.value })} /></label>
        {view === "cards" ? <label>{t("cellState")}<select value={draft.state} onChange={e => setDraft({ ...draft, state: e.target.value })}><option value="">{t("all")}</option><option value="INSIDE">{t("inside")}</option><option value="OUTSIDE">{t("outside")}</option></select></label> : <label>{view === "events" ? t("delivery") : t("attemptResult")}<select value={draft.status} onChange={e => setDraft({ ...draft, status: e.target.value })}><option value="">{t("all")}</option>{(view === "events" ? [...statuses,"LOCAL_ONLY"] : statuses).map(status => <option key={status} value={status}>{status === "LOCAL_ONLY" ? t("localOnly") : status}</option>)}</select></label>}
        {view === "cards" && factoryEnabled && <label>{t("factoryState")}<select value={draft.factoryState} onChange={e => setDraft({ ...draft, factoryState: e.target.value })}><option value="">{t("all")}</option><option value="INSIDE">{t("inside")}</option><option value="OUTSIDE">{t("outside")}</option></select></label>}
        {view === "events" && <><label>{t("from")}<input type="datetime-local" value={draft.start} onChange={e => setDraft({ ...draft, start: e.target.value })} /></label><label>{t("to")}<input type="datetime-local" value={draft.end} onChange={e => setDraft({ ...draft, end: e.target.value })} /></label></>}
        <button className="primary" type="submit">{t("applyFilters")}</button>
        <button className="secondary" type="button" onClick={() => { setDraft(initialFilters); setFilters({ ...initialFilters }); setOffset(0); }}>{t("reset")}</button>
      </form>
      <p className="muted">{view === "cards" ? t("monitoringCellHelp") : view === "events" ? t("eventsStoredHelp") : t("attemptsHelp")}</p>
      <p className="monitor-count" aria-live="polite">{loading ? t("loading") : `${data.total} ${view === "cards" ? t("badges") : view === "events" ? t("events") : t("attempts")}`}<span className="muted">{t("autoRefresh")} · {dateLabel(updated)}</span></p>
      {error && <div className="inline-error" role="alert">{error}</div>}
      <div className="table-wrap">
        {view === "cards" && <table><thead><tr><th>{t("badge")}</th><th>{t("cellState")}</th>{factoryEnabled && <th>{t("factoryState")}</th>}<th>{t("latestClock")}</th><th>{t("latestEvent")}</th><th>{t("action")}</th><th>{t("delivery")}</th><th>{t("inspect")}</th></tr></thead><tbody>{(items as CardState[]).map(card => <tr key={card.reporter_id}><td><strong>{card.reporter_id}</strong></td><td>{badgeStatus(card.worker_state)}</td>{factoryEnabled && <td>{card.factory_state ? <>{badgeStatus(card.factory_state)}<div className="cell-secondary">{card.factory_code}</div></> : <span className="muted">{t("notActivated")}</span>}</td>}<td>{card.event.terminal_code}</td><td>{dateLabel(card.event.event_datetime)}</td><td>{card.event.action_label}</td><td><Status value={card.event.delivery_status} /></td><td className="row-actions"><button onClick={() => void inspect(card.event.id)}>{t("details")}</button><button onClick={() => history(card.reporter_id)}>{t("history")}</button></td></tr>)}</tbody></table>}
        {view === "events" && <table><thead><tr><th>{t("eventTime")}</th><th>{t("clock")}</th><th>{t("badge")}</th><th>{t("action")}</th><th>{t("effect")}</th><th>{t("delivery")}</th><th>{t("attemptsLabel")}</th><th>{t("inspect")}</th></tr></thead><tbody>{(items as EventSnapshot[]).map(event => <tr key={event.id}><td>{dateLabel(event.event_datetime)}</td><td>{event.terminal_code}</td><td><strong>{event.reporter_id}</strong></td><td>{event.action_label}<div className="cell-secondary">{event.event_kind === "PERIMETER" ? `${t("factoryPerimeter")} · ${event.factory_code}` : t("cell")}</div></td><td>{event.state_effect}</td><td><Status value={event.delivery_status} /></td><td>{event.attempt_count}</td><td className="row-actions"><button onClick={() => void inspect(event.id)}>{t("details")}</button></td></tr>)}</tbody></table>}
        {view === "attempts" && <table><thead><tr><th>{t("attemptTime")}</th><th>{t("clock")}</th><th>{t("badge")}</th><th>{t("attempt")}</th><th>{t("result")}</th><th>{t("http")}</th><th>{t("duration")}</th><th>{t("inspect")}</th></tr></thead><tbody>{(items as AttemptSummary[]).map(attempt => <tr key={attempt.id}><td>{dateLabel(attempt.started_at)}</td><td>{attempt.terminal_code}</td><td>{attempt.reporter_id}</td><td>{attempt.attempt_number}</td><td><Status value={attempt.result} /></td><td>{attempt.http_status ?? "—"}</td><td>{attempt.duration_ms} ms</td><td className="row-actions"><button onClick={() => void inspect(attempt.event_id)}>{t("details")}</button></td></tr>)}</tbody></table>}
      </div>
      {!loading && !items.length && <p className="empty-state">{view === "attempts" ? t("noAttempts") : t("noResults")}</p>}
      <div className="pagination"><button className="secondary" disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - pageSize))}>{t("previous")}</button><span>{data.total ? `${offset + 1}–${Math.min(offset + pageSize, data.total)} ${t("of")} ${data.total}` : `0 ${t("results")}`}</span><button className="secondary" disabled={loading || offset + pageSize >= data.total} onClick={() => setOffset(offset + pageSize)}>{t("next")}</button></div>
    </section>
    {detailLoading && <div className="admin-card" role="status">{t("loadingDetails")}</div>}
    {detail && <EventInspector detail={detail} onClose={closeDetail} />}
  </>;
}
