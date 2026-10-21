export type ExitPolicyMode = "DISABLED" | "SAME_TERMINAL" | "SAME_WORK_CELL" | "INHERIT";
import type { Language } from "../../i18n";
import { translate } from "../../i18n";

const keys: Record<Exclude<ExitPolicyMode, "INHERIT">, string> = {
  DISABLED: "exitPolicyDisabled", SAME_TERMINAL: "exitPolicySameTerminal", SAME_WORK_CELL: "exitPolicySameWorkCell",
};
export const exitPolicyModes = (language: Language = "en") => ([
  { value: "DISABLED" as const, label: translate(language, keys.DISABLED) },
  { value: "SAME_TERMINAL" as const, label: translate(language, keys.SAME_TERMINAL) },
  { value: "SAME_WORK_CELL" as const, label: translate(language, keys.SAME_WORK_CELL) },
]);
export const exitPolicyLabel = (mode: ExitPolicyMode, language: Language = "en") => mode === "INHERIT" ? mode : translate(language, keys[mode]);
