export type IdentificationMode = "RFID" | "KEYPAD" | "BOTH";
export type IdentificationMethod = "RFID" | "KEYPAD";

export interface TerminalAction {
  code: string;
  label: string;
}

export interface TerminalConfig {
  code: string;
  name: string;
  identification_mode: IdentificationMode;
  actions: TerminalAction[];
}

export interface CapturedEvent {
  id: string;
  action_code: string;
  action_label: string;
  event_datetime: string;
  delivery_status: string;
}

export interface ScanResponse {
  flow: "ENTRY_RECORDED" | "EXIT_REQUIRED" | "EXIT_RECORDED";
  worker_state: "INSIDE" | "OUTSIDE";
  event?: CapturedEvent;
  actions: TerminalAction[];
}

export interface AdminTerminal {
  code: string;
  name: string;
  external_device_id: string;
  identification_mode: IdentificationMode;
  active: boolean;
  action_codes: string[];
}

export interface AdminAction {
  code: string;
  label: string;
  supplier_device_event: string;
  state_effect: "ENTER" | "EXIT";
  reporter_id_type: string;
  oracle_attributes: Record<string, unknown>;
  display_order: number;
  active: boolean;
}

export interface AdminEvent {
  id: string;
  terminal_code: string;
  action_label: string;
  reporter_id: string;
  event_datetime: string;
  delivery_status: string;
  attempt_count: number;
}
