// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { PerimeterPanel } from "../src/components/admin/PerimeterPanel";
import { api } from "../src/api";
vi.mock("../src/api", () => ({ api: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }));

afterEach(() => { cleanup(); vi.clearAllMocks(); window.history.replaceState({}, "", "/admin/perimeter"); localStorage.removeItem("bss-timecollection-language"); });
const factories = [
  {id:1,code:"ARGANDA",name:"Arganda",location:"Arganda",country:"Spain",timezone:"Europe/Madrid",active:true,created_at:"",updated_at:""},
  {id:2,code:"OTHER",name:"Other site",location:null,country:null,timezone:"UTC",active:true,created_at:"",updated_at:""},
];
const install = {default_factory_code:"ARGANDA",default_factory:factories[0],configuration_error:null};
const arganda = {factory_code:"ARGANDA",enabled:false,badge_source:"OPEN",dedup_enabled:true,dedup_seconds:7,auto_exit_action_code:null};
const other = {factory_code:"OTHER",enabled:false,badge_source:"OPEN",dedup_enabled:false,dedup_seconds:13,auto_exit_action_code:null};
function setup(terminals: unknown[] = [], argandaConfig = arganda) {
  vi.mocked(api.get).mockImplementation(async (path: string) => {
    if (path === "/api/v1/admin/factories") return factories;
    if (path === "/api/v1/admin/installation-settings") return install;
    if (path === "/api/v1/admin/terminals") return terminals;
    if (path.endsWith("/external/status")) return {provider:"SQLSERVER_SECURITY_DB",configured:true,reachable:false,database:"SECURITY_DB",server:null,driver:"ODBC",last_check_at:null,status:"ERROR",error_category:"AUTH_FAILED"};
    if (path.endsWith("/presence")) return {factory_code:path.includes("OTHER") ? "OTHER" : "ARGANDA",inside:[],recent_events:[]};
    return path.includes("/OTHER") ? other : argandaConfig;
  });
}
it("opens Factory Perimeter on the persisted default with a registry dropdown", async () => {
  setup();
  render(<PerimeterPanel terminals={[]} actions={[]} />);
  const selector = (await screen.findAllByRole("combobox"))[0];
  expect(selector.tagName).toBe("SELECT");
  expect((selector as HTMLSelectElement).value).toBe("ARGANDA");
  expect(screen.getByText("Arganda (ARGANDA)")).toBeTruthy();
  expect((await screen.findByLabelText("Scan cooldown (seconds)") as HTMLInputElement).value).toBe("7");
  expect(api.get).toHaveBeenCalledWith("/api/v1/admin/perimeter/ARGANDA");
});
it("loads and saves only the selected factory's perimeter settings", async () => {
  setup();
  render(<PerimeterPanel terminals={[]} actions={[]} />);
  await screen.findByLabelText("Scan cooldown (seconds)");
  fireEvent.change((await screen.findAllByRole("combobox"))[0], {target:{value:"OTHER"}});
  const cooldown = await screen.findByLabelText("Scan cooldown (seconds)") as HTMLInputElement;
  await waitFor(() => expect(cooldown.value).toBe("13"));
  fireEvent.click(screen.getByText("Save factory settings"));
  await waitFor(() => expect(api.put).toHaveBeenCalledWith("/api/v1/admin/perimeter/OTHER", expect.objectContaining({factory_code:"OTHER",dedup_seconds:13})));
});
it("uses the selected registered factory in terminal role assignments", async () => {
  const terminal = {code:"T0005",name:"Main entry",factory_code:"OTHER",terminal_role:"PERIMETER_BOTH"};
  setup([terminal]);
  vi.mocked(api.put).mockResolvedValue({code:"T0005",factory_code:"ARGANDA",role:"PERIMETER_BOTH"});
  render(<PerimeterPanel terminals={[terminal as never]} actions={[]} />);
  const assign = await screen.findByRole("button", {name:"Assign to ARGANDA"});
  expect(screen.queryByRole("button", {name:/Assign to DEFAULT/})).toBeNull();
  fireEvent.click(assign);
  await waitFor(() => expect(api.put).toHaveBeenCalledWith("/api/v1/admin/perimeter/terminals/T0005/role", {role:"PERIMETER_BOTH",factory_code:"ARGANDA"}));
});
it("retains Arganda external perimeter diagnostics", async () => {
  setup([], {...arganda,badge_source:"EXTERNAL"});
  localStorage.setItem("bss-timecollection-language", "es");
  window.history.replaceState({}, "", "/admin/perimeter?factory=ARGANDA");
  render(<PerimeterPanel terminals={[]} actions={[]} />);
  expect(await screen.findByText("Control externo Arganda")).toBeTruthy();
  expect(screen.getByText("AUTH_FAILED")).toBeTruthy();
});
