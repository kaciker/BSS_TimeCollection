export type ExitPolicyMode = "DISABLED" | "SAME_TERMINAL" | "SAME_WORK_CELL" | "INHERIT";
export const exitPolicyModes: {value:ExitPolicyMode; label:string}[] = [
  {value:"DISABLED",label:"Disabled — any terminal"},
  {value:"SAME_TERMINAL",label:"Same Terminal — original entry terminal"},
  {value:"SAME_WORK_CELL",label:"Same Work Cell — matching configured cell"},
];
export const exitPolicyLabel = (mode:ExitPolicyMode) => exitPolicyModes.find(item=>item.value===mode)?.label ?? mode;
