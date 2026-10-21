import type { AdminEvent } from "../types";

export interface EventSnapshot extends AdminEvent {
  event_kind?: "CELL" | "PERIMETER";
  factory_code?: string | null;
  correlation_id?: string | null;
  auto_cell_exit_event_id?: string | null;
  request_number: string | null;
  terminal_id: number;
  action_id: number | null;
  device_id: string | null;
  action_code: string;
  supplier_device_event: string | null;
  state_effect: string;
  reporter_id_type: string | null;
  identification_method: string | null;
  event_timezone: string;
  oracle_attributes: Record<string, unknown>;
  created_at: string;
  next_attempt_at: string | null;
  last_attempt_at: string | null;
  sent_at: string | null;
  oracle_request_id: string | null;
  oracle_event_id: string | null;
}
export interface Attempt {
  id: number;
  event_id: string;
  attempt_number: number;
  started_at: string;
  finished_at: string;
  endpoint: string;
  http_status: number | null;
  result: string;
  duration_ms: number;
  request_payload: Record<string, unknown>;
  response_payload: unknown;
  error_message: string | null;
}
export interface AttemptSummary extends Attempt { reporter_id: string; terminal_code: string }
export interface CardState { reporter_id: string; worker_state: "INSIDE" | "OUTSIDE"; factory_code?: string | null; factory_state?: "INSIDE" | "OUTSIDE" | null; event: EventSnapshot }
export interface Page<T> { items: T[]; total: number; factory_perimeter_enabled?: boolean; external_factory_presence?: boolean }
export interface EventDetail { event: EventSnapshot; attempts: Attempt[]; oracle_enabled: boolean; oracle_payload_preview: Record<string, unknown> | null }
export const dateLabel = (value: string | null) => value ? new Date(value).toLocaleString("en-GB") : "—";
export function Status({ value }: { value: string }) {
  return <span className={`status status-${value.toLowerCase()}`}>{value === "LOCAL_ONLY" ? "Solo local" : value}</span>;
}
