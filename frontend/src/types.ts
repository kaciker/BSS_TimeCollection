export type IdentificationMode = "RFID" | "KEYPAD" | "BOTH";
export type IdentificationMethod = "RFID" | "KEYPAD";

export interface TerminalAction {
  code: string;
  label: string;
  has_subactions: boolean;
  visual_key?: string | null;
}

export interface TerminalConfig {
  code: string;
  name: string;
  identification_mode: IdentificationMode;
  actions: TerminalAction[];
}

export interface TerminalPairingStart {
  pairing_code: string;
  request_token: string;
  expires_at: string;
  poll_after_seconds: number;
}

export interface TerminalPairingStatus {
  status: "WAITING" | "APPROVED";
  config?: TerminalConfig | null;
}

export interface CapturedEvent {
  id: string;
  action_code: string;
  action_label: string;
  event_datetime: string;
  delivery_status: string;
}

export interface ScanResponse {
  flow: "ENTRY_RECORDED" | "EXIT_REQUIRED" | "SUBACTION_REQUIRED" | "EXIT_RECORDED";
  worker_state: "INSIDE" | "OUTSIDE";
  event?: CapturedEvent;
  actions: TerminalAction[];
}

export interface AdminTerminal {
  code: string;
  name: string;
  external_device_id: string;
  identification_mode: IdentificationMode;
  reporter_id_type: string;
  oracle_attributes: Record<string, unknown>;
  active: boolean;
  action_codes: string[];
  provisioned: boolean;
  activation_pending: boolean;
  exit_policy_mode: "DISABLED" | "SAME_TERMINAL" | "SAME_WORK_CELL" | "INHERIT";
  effective_exit_policy_mode: "DISABLED" | "SAME_TERMINAL" | "SAME_WORK_CELL";
  global_exit_policy_mode: "DISABLED" | "SAME_TERMINAL" | "SAME_WORK_CELL";
  activation_token?: string | null;
}

export interface TerminalProvisioning {
  code: string;
  activation_token: string;
}

export interface AdminAction {
  code: string;
  label: string;
  supplier_device_event: string;
  state_effect: "ENTER" | "EXIT";
  oracle_attributes: Record<string, unknown>;
  display_order: number;
  requires_subaction: boolean;
  parent_action_code?: string | null;
  subaction_codes: string[];
  visual_key?: string | null;
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
