import { dateLabel, Status } from "./monitoringTypes";
import type { EventDetail } from "./monitoringTypes";

function Json({ value }: { value: unknown }) {
  return <pre className="json-view">{JSON.stringify(value, null, 2)}</pre>;
}

export function EventInspector({ detail, onClose }: { detail: EventDetail; onClose: () => void }) {
  const event = detail.event;
  const fields: [string, string | number | null][] = [
    ["Event ID", event.id], ["Request / requestNumber", event.request_number],
    ["Clock", event.terminal_code], ["deviceId", event.device_id],
    ["Badge / reporterId", event.reporter_id], ["reporterIdType", event.reporter_id_type],
    ["Identification", event.identification_method], ["Action", `${event.action_code} · ${event.action_label}`],
    ["supplierDeviceEvent", event.supplier_device_event], ["Local effect", event.state_effect],
    ["Event time", dateLabel(event.event_datetime)], ["Time zone", event.event_timezone],
    ["Stored in BSS", dateLabel(event.created_at)], ["Attempts", event.attempt_count],
    ["Last attempt", dateLabel(event.last_attempt_at)], ["Next attempt", dateLabel(event.next_attempt_at)],
    ["Accepted by Oracle", dateLabel(event.sent_at)], ["timeEventRequestId", event.oracle_request_id],
    ["timeEventId", event.oracle_event_id],
  ];
  return <section className="admin-card event-inspector" aria-label="Event details">
    <div className="monitor-heading"><div><div className="eyebrow">EVENT DETAILS</div><h2>Badge {event.reporter_id}</h2></div><button className="secondary" onClick={onClose}>Close details</button></div>
    <p><Status value={event.delivery_status} /> · Oracle {detail.oracle_enabled ? "enabled" : "disabled"}</p>
    <dl className="event-fields">{fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value ?? "—"}</dd></div>)}</dl>
    <details><summary>Complete record stored in BSS</summary><Json value={event} /></details>
    <h3>Oracle payload preview</h3>
    <p className="muted">Preview using the current configuration; this is not evidence of transmission. requestTimestamp is generated when sending. The actual JSON for each attempt appears below.</p>
    <Json value={detail.oracle_payload_preview} />
    <h3>Transmission history ({detail.attempts.length})</h3>
    <p className="muted">SENT indicates HTTP acceptance; subsequent business validation is handled by Oracle.</p>
    {!detail.attempts.length && <p className="empty-state">No transmission attempts recorded. This event has not been sent to Oracle yet.</p>}
    {detail.attempts.map(attempt => <details className="attempt-detail" key={attempt.id}>
      <summary>Attempt {attempt.attempt_number} · {dateLabel(attempt.started_at)} · {attempt.result} · HTTP {attempt.http_status ?? "—"}</summary>
      <p>Endpoint: <code>{attempt.endpoint}</code></p>
      <p>Finished: {dateLabel(attempt.finished_at)} · Duration: {attempt.duration_ms} ms</p>
      {attempt.error_message && <p className="inline-error">{attempt.error_message}</p>}
      <h4>Recorded request</h4><Json value={attempt.request_payload} />
      <h4>Recorded response</h4><Json value={attempt.response_payload} />
    </details>)}
  </section>;
}
