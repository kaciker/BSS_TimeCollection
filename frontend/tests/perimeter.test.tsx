// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { PerimeterPanel } from "../src/components/admin/PerimeterPanel";
import { api } from "../src/api";
vi.mock("../src/api", () => ({ api: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }));
afterEach(() => { cleanup(); vi.clearAllMocks(); window.history.replaceState({}, "", "/admin/perimeter"); localStorage.removeItem("bss-perimeter-factory"); localStorage.removeItem("bss-timecollection-language"); });
it("loads disabled settings and does not write terminal assignments", async () => {
  vi.mocked(api.get).mockImplementation(async path => path.endsWith("/presence") ? {inside: [], recent_events: []} : {factory_code: "DEFAULT", enabled: false, badge_source: "OPEN", dedup_enabled: false, dedup_seconds: 5, auto_exit_action_code: null});
  render(<PerimeterPanel terminals={[]} actions={[]} />);
  const enabled = await screen.findByLabelText("Require factory entry before cell entry") as HTMLInputElement;
  expect(enabled.checked).toBe(false);
  expect(api.put).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText("Save factory settings"));
  await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1));
  expect(api.put).toHaveBeenCalledWith("/api/v1/admin/perimeter/DEFAULT", expect.objectContaining({enabled: false}));
});
it("displays activation errors without implying success", async () => {
  vi.mocked(api.get).mockImplementation(async path => path.endsWith("/presence") ? {inside: [], recent_events: []} : {factory_code: "DEFAULT", enabled: false, badge_source: "OPEN", dedup_enabled: false, dedup_seconds: 5, auto_exit_action_code: null});
  vi.mocked(api.put).mockRejectedValue(new Error("Configure automatic cell EXIT action"));
  render(<PerimeterPanel terminals={[]} actions={[]} />);
  await screen.findByLabelText("Require factory entry before cell entry");
  fireEvent.click(screen.getByText("Save factory settings"));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Configure automatic cell EXIT action");
  expect(screen.queryByText("Factory perimeter configuration saved.")).toBeNull();
});

it("offers active leaf EXIT actions including hidden actions", async () => {
  vi.mocked(api.get).mockImplementation(async path => path.endsWith("/presence") ? {inside: [], recent_events: []} : {factory_code: "DEFAULT", enabled: false, badge_source: "OPEN", dedup_enabled: false, dedup_seconds: 5, auto_exit_action_code: null});
  const actions = [
    {code:"AUTO",label:"Automatic exit",state_effect:"EXIT",active:true,show_on_terminal:false,requires_subaction:false},
    {code:"ENTRY",label:"Entry",state_effect:"ENTER",active:true,show_on_terminal:true,requires_subaction:false},
    {code:"PARENT",label:"Parent",state_effect:"EXIT",active:true,show_on_terminal:true,requires_subaction:true},
    {code:"OFF",label:"Inactive",state_effect:"EXIT",active:false,show_on_terminal:true,requires_subaction:false},
  ] as import("../src/types").AdminAction[];
  render(<PerimeterPanel terminals={[]} actions={actions} />);
  const selector = await screen.findByLabelText("Automatic cell EXIT action");
  expect(screen.getByRole("option", {name:"Automatic exit · AUTO (hidden)"})).toBeTruthy();
  expect(screen.queryByRole("option", {name:/Parent|Inactive|Entry ·/})).toBeNull();
  fireEvent.change(selector,{target:{value:"AUTO"}});
  fireEvent.click(screen.getByText("Save factory settings"));
  await waitFor(() => expect(api.put).toHaveBeenCalledWith("/api/v1/admin/perimeter/DEFAULT",expect.objectContaining({auto_exit_action_code:"AUTO"})));
});

it("clears a previous success notice when a later save fails", async () => {
  vi.mocked(api.get).mockImplementation(async path => path.endsWith("/presence") ? {inside: [], recent_events: []} : {factory_code: "DEFAULT", enabled: false, badge_source: "OPEN", dedup_enabled: false, dedup_seconds: 5, auto_exit_action_code: null});
  vi.mocked(api.put).mockResolvedValueOnce({}).mockRejectedValueOnce(new Error("Save failed"));
  render(<PerimeterPanel terminals={[]} actions={[]} />);
  await screen.findByLabelText("Automatic cell EXIT action");
  fireEvent.click(screen.getByText("Save factory settings"));
  await screen.findByText("Factory perimeter configuration saved.");
  fireEvent.click(screen.getByText("Save factory settings"));
  await screen.findByRole("alert");
  expect(screen.queryByText("Factory perimeter configuration saved.")).toBeNull();
});

it("retains the selected factory and its saved settings after a page reload", async () => {
  const saved = {factory_code:"ARGANDA",enabled:true,badge_source:"OPEN",dedup_enabled:false,dedup_seconds:5,auto_exit_action_code:"END_WORK"};
  vi.mocked(api.get).mockImplementation(async path => path.endsWith("/presence") ? {inside:[],recent_events:[]} : path.includes("/ARGANDA") ? saved : {...saved,factory_code:"DEFAULT",enabled:false,auto_exit_action_code:null});
  const actions = [{code:"END_WORK",label:"End work",state_effect:"EXIT",active:true,requires_subaction:false,show_on_terminal:true}] as import("../src/types").AdminAction[];
  const mounted = render(<PerimeterPanel terminals={[]} actions={actions} />);
  await screen.findByLabelText("Automatic cell EXIT action");
  fireEvent.change(screen.getByLabelText("Factory code"),{target:{value:"ARGANDA"}});
  await waitFor(() => expect((screen.getByLabelText("Automatic cell EXIT action") as HTMLSelectElement).value).toBe("END_WORK"));
  expect(new URLSearchParams(window.location.search).get("factory")).toBe("ARGANDA");
  mounted.unmount();
  render(<PerimeterPanel terminals={[]} actions={actions} />);
  await screen.findByLabelText("Automatic cell EXIT action");
  expect((screen.getByLabelText("Factory code") as HTMLInputElement).value).toBe("ARGANDA");
  expect((screen.getByLabelText("Require factory entry before cell entry") as HTMLInputElement).checked).toBe(true);
  expect((screen.getByLabelText("Automatic cell EXIT action") as HTMLSelectElement).value).toBe("END_WORK");
  expect(api.put).not.toHaveBeenCalled();
});

it("ignores a late response from the previous factory", async () => {
  let resolveOld: (value: unknown) => void = () => {};
  vi.mocked(api.get).mockImplementation(path => path.endsWith("/presence") ? Promise.resolve({inside:[],recent_events:[]}) : path.includes("/DEFAULT") ? new Promise(resolve => {resolveOld=resolve;}) : Promise.resolve({factory_code:"ARGANDA",enabled:false,badge_source:"OPEN",dedup_enabled:false,dedup_seconds:12,auto_exit_action_code:null}));
  render(<PerimeterPanel terminals={[]} actions={[]} />);
  fireEvent.change(screen.getByLabelText("Factory code"),{target:{value:"ARGANDA"}});
  await screen.findByLabelText("Scan cooldown (seconds)");
  resolveOld({factory_code:"DEFAULT",enabled:false,badge_source:"OPEN",dedup_enabled:false,dedup_seconds:99,auto_exit_action_code:null});
  await waitFor(() => expect((screen.getByLabelText("Scan cooldown (seconds)") as HTMLInputElement).value).toBe("12"));
});

it("restores the last factory when reopening the menu URL without a query", async () => {
  localStorage.setItem("bss-perimeter-factory","ARGANDA");
  vi.mocked(api.get).mockImplementation(async path => path.endsWith("/presence") ? {inside:[],recent_events:[]} : {factory_code:"ARGANDA",enabled:true,badge_source:"OPEN",dedup_enabled:false,dedup_seconds:5,auto_exit_action_code:null});
  render(<PerimeterPanel terminals={[]} actions={[]} />);
  await screen.findByLabelText("Automatic cell EXIT action");
  expect((screen.getByLabelText("Factory code") as HTMLInputElement).value).toBe("ARGANDA");
  expect(api.get).toHaveBeenCalledWith("/api/v1/admin/perimeter/ARGANDA");
  expect(api.put).not.toHaveBeenCalled();
});

it("explicit factory URL takes priority over the last browser selection", async () => {
  localStorage.setItem("bss-perimeter-factory","ARGANDA");
  window.history.replaceState({},"","/admin/perimeter?factory=OTHER");
  vi.mocked(api.get).mockImplementation(async path => path.endsWith("/presence") ? {inside:[],recent_events:[]} : {factory_code:"OTHER",enabled:false,badge_source:"OPEN",dedup_enabled:false,dedup_seconds:5,auto_exit_action_code:null});
  render(<PerimeterPanel terminals={[]} actions={[]} />);
  await screen.findByLabelText("Automatic cell EXIT action");
  expect((screen.getByLabelText("Factory code") as HTMLInputElement).value).toBe("OTHER");
  expect(localStorage.getItem("bss-perimeter-factory")).toBe("OTHER");
});

it("distinguishes saved assignment from destination and updates it after saving", async () => {
  window.history.replaceState({},"","/admin/perimeter?factory=ARGANDA");
  const terminal = {code:"T0004",name:"Cell clock",factory_code:"DEFAULT",terminal_role:"CELL"} as import("../src/types").AdminTerminal;
  vi.mocked(api.get).mockImplementation(async path => path.endsWith("/terminals") ? [terminal] : path.endsWith("/presence") ? {inside:[],recent_events:[]} : {factory_code:"ARGANDA",enabled:true,badge_source:"OPEN",dedup_enabled:false,dedup_seconds:5,auto_exit_action_code:null});
  vi.mocked(api.put).mockResolvedValue({code:"T0004",factory_code:"ARGANDA",role:"CELL"});
  render(<PerimeterPanel terminals={[terminal]} actions={[]} />);
  await screen.findByLabelText("Automatic cell EXIT action");
  expect(screen.getByText("DEFAULT")).toBeTruthy();
  expect(screen.getByRole("button",{name:"Assign to ARGANDA"})).toBeTruthy();
  fireEvent.click(screen.getByRole("button",{name:"Assign to ARGANDA"}));
  await screen.findByRole("button",{name:"Assignment saved"});
  expect(screen.queryByText("DEFAULT")).toBeNull();
  expect((screen.getByRole("button",{name:"Assignment saved"}) as HTMLButtonElement).disabled).toBe(true);
});


it("shows external diagnostics and tests a badge without requesting local events", async () => {
  localStorage.setItem("bss-timecollection-language", "es");
  window.history.replaceState({}, "", "/admin/perimeter?factory=ARGANDA");
  vi.mocked(api.get).mockImplementation(async path => path.endsWith("/presence") ? {inside: [], recent_events: []} : path.endsWith("/external/status") ? {provider:"SQLSERVER_SECURITY_DB",configured:true,reachable:false,database:"SECURITY_DB",server:"10.33.157.67:1433",driver:"ODBC Driver 18 for SQL Server",last_check_at:"2026-10-22T10:00:00Z",status:"ERROR",error_category:"AUTH_FAILED"} : {factory_code:"ARGANDA",enabled:false,badge_source:"EXTERNAL",dedup_enabled:true,dedup_seconds:5,auto_exit_action_code:null});
  vi.mocked(api.post).mockResolvedValue({status:"INSIDE",external_event_time:"2026-10-22T10:00:00Z",zone_code:2,error_category:null});
  render(<PerimeterPanel terminals={[]} actions={[]} />);
  expect(await screen.findByText("Control externo Arganda")).toBeTruthy();
  expect(screen.getByText("Datos locales BSS")).toBeTruthy();
  expect(screen.getByText("AUTH_FAILED")).toBeTruthy();
  expect(screen.queryByText("Presencia en fábrica")).toBeNull();
  expect(screen.queryByText("Movimientos perimetrales recientes")).toBeNull();
  fireEvent.click(screen.getByText("Probar conexión"));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/v1/admin/perimeter/ARGANDA/external/check", {}));
  fireEvent.change(screen.getByLabelText("Tarjeta para probar"), {target:{value:"0582609699"}});
  fireEvent.click(screen.getByText("Probar tarjeta"));
  expect(await screen.findByText("Resultado externo: INSIDE")).toBeTruthy();
  expect(api.post).toHaveBeenCalledWith("/api/v1/admin/perimeter/ARGANDA/external/test-badge", {badge:"0582609699"});
  expect(api.put).not.toHaveBeenCalled();
});
