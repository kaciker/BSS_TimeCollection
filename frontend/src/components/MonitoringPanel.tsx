import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { api } from "../api";
import type { AdminTerminal } from "../types";
import { EventInspector } from "./EventInspector";
import { dateLabel, Status } from "./monitoringTypes";
import type { AttemptSummary, CardState, EventDetail, EventSnapshot, Page } from "./monitoringTypes";

type View = "cards" | "events" | "attempts";
const statuses = ["PENDING", "SENDING", "RETRY", "SENT", "REJECTED", "UNKNOWN"];
const initialFilters = { clock: "", badge: "", state: "INSIDE", status: "", start: "", end: "" };
const pageSize = 50;

export function MonitoringPanel({ terminals, initialView = "cards", onNavigate }: { terminals: AdminTerminal[]; initialView?: View; onNavigate?: (view: View, query?: string) => void }) {
  const [view, setView] = useState<View>(initialView);
  const [draft, setDraft] = useState(() => {
    const query = new URLSearchParams(window.location.search);
    return { ...initialFilters, badge: query.get("badge") ?? "", clock: query.get("clock") ?? "" };
  });
  const [filters, setFilters] = useState(draft);
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [data, setData] = useState<Page<EventSnapshot | CardState | AttemptSummary>>({ items: [], total: 0 });
  const [dataView, setDataView] = useState<View>(initialView);
  const items = dataView === view ? data.items : [];
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [updated, setUpdated] = useState<string | null>(null);
  const [detail, setDetail] = useState<EventDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const detailRequest = useRef(0);

  useEffect(() => {
    let active = true;
    let pending = false;
    const query = new URLSearchParams({ offset: String(offset), limit: String(pageSize) });
    if (filters.clock) query.set("terminal_code", filters.clock);
    if (filters.badge) query.set("reporter_id", filters.badge);
    if (view === "cards" && filters.state) query.set("worker_state", filters.state);
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
        if (active) { setData(result); setDataView(view); setError(""); setUpdated(new Date().toISOString()); }
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
  const badgeStatus = (value: string) => <span className={`status ${value === "INSIDE" ? "status-sent" : ""}`}>{value === "INSIDE" ? "Inside" : "Outside"}</span>;

  return <>
    <section className="admin-card monitoring">
      <div className="monitor-heading"><div><h2>{view === "cards" ? "Badge register" : view === "events" ? "Captured events" : "Delivery attempts"}</h2></div><button className="secondary" onClick={() => setRevision(value => value + 1)}>Refresh</button></div>
      <form className="monitor-filters" onSubmit={apply}>
        <label>Clock<select value={draft.clock} onChange={e => setDraft({ ...draft, clock: e.target.value })}><option value="">All clocks</option>{terminals.map(terminal => <option key={terminal.code} value={terminal.code}>{terminal.code} · {terminal.name}</option>)}</select></label>
        <label>Badge number<input value={draft.badge} placeholder="Search badge" onChange={e => setDraft({ ...draft, badge: e.target.value })} /></label>
        {view === "cards" ? <label>Local state<select value={draft.state} onChange={e => setDraft({ ...draft, state: e.target.value })}><option value="">All</option><option value="INSIDE">Inside</option><option value="OUTSIDE">Outside</option></select></label> : <label>{view === "events" ? "Delivery" : "Attempt result"}<select value={draft.status} onChange={e => setDraft({ ...draft, status: e.target.value })}><option value="">All</option>{statuses.map(status => <option key={status}>{status}</option>)}</select></label>}
        {view === "events" && <><label>From<input type="datetime-local" value={draft.start} onChange={e => setDraft({ ...draft, start: e.target.value })} /></label><label>To<input type="datetime-local" value={draft.end} onChange={e => setDraft({ ...draft, end: e.target.value })} /></label></>}
        <button className="primary" type="submit">Apply filters</button>
        <button className="secondary" type="button" onClick={() => { setDraft(initialFilters); setFilters({ ...initialFilters }); setOffset(0); }}>Reset</button>
      </form>
      <p className="muted">{view === "cards" ? "State derived from each badge's latest event across all clocks. The clock filter refers to the latest event; this is not Oracle-validated attendance." : view === "events" ? "Events stored in BSS. Open the details to view all recorded data and delivery history." : "Each Oracle transmission attempt, with its request, response and technical result in the details."}</p>
      <p className="monitor-count" aria-live="polite">{loading ? "Loading…" : `${data.total} ${view === "cards" ? "badges" : view === "events" ? "events" : "attempts"}`}<span className="muted">Auto-refresh every 15 s · {dateLabel(updated)}</span></p>
      {error && <div className="inline-error" role="alert">{error}</div>}
      <div className="table-wrap">
        {view === "cards" && <table><thead><tr><th>Badge</th><th>Local state</th><th>Latest clock</th><th>Latest event</th><th>Action</th><th>Delivery</th><th>Inspect</th></tr></thead><tbody>{(items as CardState[]).map(card => <tr key={card.reporter_id}><td><strong>{card.reporter_id}</strong></td><td>{badgeStatus(card.worker_state)}</td><td>{card.event.terminal_code}</td><td>{dateLabel(card.event.event_datetime)}</td><td>{card.event.action_label}</td><td><Status value={card.event.delivery_status} /></td><td className="row-actions"><button onClick={() => void inspect(card.event.id)}>Details</button><button onClick={() => history(card.reporter_id)}>History</button></td></tr>)}</tbody></table>}
        {view === "events" && <table><thead><tr><th>Event time</th><th>Clock</th><th>Badge</th><th>Action</th><th>Effect</th><th>Delivery</th><th>Attempts</th><th>Inspect</th></tr></thead><tbody>{(items as EventSnapshot[]).map(event => <tr key={event.id}><td>{dateLabel(event.event_datetime)}</td><td>{event.terminal_code}</td><td><strong>{event.reporter_id}</strong></td><td>{event.action_label}</td><td>{event.state_effect}</td><td><Status value={event.delivery_status} /></td><td>{event.attempt_count}</td><td className="row-actions"><button onClick={() => void inspect(event.id)}>Details</button></td></tr>)}</tbody></table>}
        {view === "attempts" && <table><thead><tr><th>Attempt time</th><th>Clock</th><th>Badge</th><th>Attempt</th><th>Result</th><th>HTTP</th><th>Duration</th><th>Inspect</th></tr></thead><tbody>{(items as AttemptSummary[]).map(attempt => <tr key={attempt.id}><td>{dateLabel(attempt.started_at)}</td><td>{attempt.terminal_code}</td><td>{attempt.reporter_id}</td><td>{attempt.attempt_number}</td><td><Status value={attempt.result} /></td><td>{attempt.http_status ?? "—"}</td><td>{attempt.duration_ms} ms</td><td className="row-actions"><button onClick={() => void inspect(attempt.event_id)}>Details</button></td></tr>)}</tbody></table>}
      </div>
      {!loading && !items.length && <p className="empty-state">{view === "attempts" ? "No recorded attempts match these filters. Pending events may not have been sent yet." : "No results match these filters."}</p>}
      <div className="pagination"><button className="secondary" disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - pageSize))}>Previous</button><span>{data.total ? `${offset + 1}–${Math.min(offset + pageSize, data.total)} of ${data.total}` : "0 results"}</span><button className="secondary" disabled={loading || offset + pageSize >= data.total} onClick={() => setOffset(offset + pageSize)}>Next</button></div>
    </section>
    {detailLoading && <div className="admin-card" role="status">Loading details…</div>}
    {detail && <EventInspector detail={detail} onClose={closeDetail} />}
  </>;
}
