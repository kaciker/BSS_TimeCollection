import { dateLabel, Status } from "./monitoringTypes";
import type { EventDetail } from "./monitoringTypes";
import { useLanguage } from "../i18n";

function Json({ value }: { value: unknown }) {
  return <pre className="json-view">{JSON.stringify(value, null, 2)}</pre>;
}

export function EventInspector({ detail, onClose }: { detail: EventDetail; onClose: () => void }) {
  const { t, language } = useLanguage();
  const event = detail.event;
  const fields: [string, string | number | null][] = [
    ["Event ID", event.id], [t("requestNumber"), event.request_number],
    [t("clock"), event.terminal_code], ["deviceId", event.device_id],
    ["Badge / reporterId", event.reporter_id], ["reporterIdType", event.reporter_id_type],
    [t("identification"), event.identification_method], [t("action"), `${event.action_code} · ${event.action_label}`],
    ["supplierDeviceEvent", event.supplier_device_event], [t("localEffect"), event.state_effect],
    [t("eventTime"), dateLabel(event.event_datetime, language)], [t("timeZone"), event.event_timezone],
    [t("storedInBss"), dateLabel(event.created_at, language)], [t("attemptsLabel"), event.attempt_count],
    [t("lastAttempt"), dateLabel(event.last_attempt_at, language)], [t("nextAttempt"), dateLabel(event.next_attempt_at, language)],
    [t("acceptedByOracle"), dateLabel(event.sent_at, language)], ["timeEventRequestId", event.oracle_request_id],
    ["timeEventId", event.oracle_event_id],
  ];
  if (event.event_kind === "PERIMETER") return <section className="admin-card event-inspector" aria-label={t("eventDetails")}>
    <div className="monitor-heading"><div><div className="eyebrow">{t("perimeterUpper")}</div><h2>{t("badgePrefix")} {event.reporter_id}</h2></div><button className="secondary" onClick={onClose}>{t("closeDetails")}</button></div>
    <p><Status value="LOCAL_ONLY" t={t} /> · {t("perimeterNotSent")}</p>
    <dl className="event-fields">{[[t("factory"),event.factory_code],[t("clock"),event.terminal_code],[t("direction"),event.state_effect],[t("time"),dateLabel(event.event_datetime, language)],["Correlation ID",event.correlation_id],[t("autoCellExit"),event.auto_cell_exit_event_id]].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value ?? "—"}</dd></div>)}</dl>
    <details><summary>{t("completeRecord")}</summary><Json value={event} /></details>
  </section>;
  return <section className="admin-card event-inspector" aria-label={t("eventDetails")}>
    <div className="monitor-heading"><div><div className="eyebrow">{t("eventUpper")}</div><h2>{t("badgePrefix")} {event.reporter_id}</h2></div><button className="secondary" onClick={onClose}>{t("closeDetails")}</button></div>
    <p><Status value={event.delivery_status} t={t} /> · Oracle {detail.oracle_enabled ? t("oracleEnabled") : t("oracleDisabled")}</p>
    <dl className="event-fields">{fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value ?? "—"}</dd></div>)}</dl>
    <details><summary>{t("completeRecord")}</summary><Json value={event} /></details>
    <h3>{t("payloadPreview")}</h3>
    <p className="muted">{t("previewHelp")}</p>
    <Json value={detail.oracle_payload_preview} />
    <h3>{t("transmissionHistory")} ({detail.attempts.length})</h3>
    <p className="muted">{t("sentHelp")}</p>
    {!detail.attempts.length && <p className="empty-state">{t("noTransmissionAttempts")}</p>}
    {detail.attempts.map(attempt => <details className="attempt-detail" key={attempt.id}>
      <summary>{t("attempt")} {attempt.attempt_number} · {dateLabel(attempt.started_at, language)} · {attempt.result} · HTTP {attempt.http_status ?? "—"}</summary>
      <p>{t("endpoint")}: <code>{attempt.endpoint}</code></p>
      <p>{t("finished")}: {dateLabel(attempt.finished_at, language)} · {t("duration")}: {attempt.duration_ms} ms</p>
      {attempt.error_message && <p className="inline-error">{attempt.error_message}</p>}
      <h4>{t("recordedRequest")}</h4><Json value={attempt.request_payload} />
      <h4>{t("recordedResponse")}</h4><Json value={attempt.response_payload} />
    </details>)}
  </section>;
}
