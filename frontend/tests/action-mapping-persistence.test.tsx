// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ActionEditor } from "../src/components/admin/ActionEditor";
import { api } from "../src/api";
import type { AdminAction, OracleCatalogue } from "../src/types";

vi.mock("../src/api", () => ({ api: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }));
vi.mock("../src/components/admin/EditorDialog", () => ({ EditorDialog: ({ children }: { children: import("react").ReactNode }) => <div>{children}</div> }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

const action: AdminAction = {
  code: "ARGANDA_DIRECT_EXIT", label: "Salida Fábrica", supplier_device_event: "direct_exit",
  oracle_supplier_event: "HUT_TCD_SUPP1_OUT_2", state_effect: "EXIT", oracle_payroll_time_type: null,
  oracle_attributes: {}, display_order: 1, requires_subaction: false, subaction_codes: [],
  show_on_terminal: false, active: true,
};
const catalogue: OracleCatalogue = { payroll_time_types: ["Workshop Entry ES", "Project Entry ES"], work_areas: [], machines: [], cells: [] };
const saved = (payroll: string | null) => ({ ...action, oracle_payroll_time_type: payroll });

it("waits for the catalogue, submits the selected value, and confirms the persisted response", async () => {
  let resolveCatalogue!: (value: OracleCatalogue) => void;
  vi.mocked(api.get).mockReturnValue(new Promise(resolve => { resolveCatalogue = resolve }) as never);
  vi.mocked(api.put).mockResolvedValue(saved("Workshop Entry ES") as never);
  const onSaved = vi.fn();
  render(<ActionEditor action={action} actions={[]} terminals={[]} onClose={vi.fn()} onSaved={onSaved} />);
  expect(screen.getByRole("button", { name: "Save changes" }).hasAttribute("disabled")).toBe(true);
  resolveCatalogue(catalogue);
  await screen.findByRole("option", { name: "Workshop Entry ES" });
  fireEvent.change(document.querySelector("select[name=payrollTimeType]")!, { target: { value: "Workshop Entry ES" } });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() => expect(onSaved).toHaveBeenCalledWith(saved("Workshop Entry ES")));
  const payload = vi.mocked(api.put).mock.calls[0][1] as Record<string, unknown>;
  expect(payload.oracle_payroll_time_type).toBe("Workshop Entry ES");
  expect(payload.oracle_supplier_event).toBe("HUT_TCD_SUPP1_OUT_2");
  expect(payload.state_effect).toBe("EXIT");
});

it("keeps the editor open and reports mismatch when the API response does not persist the selection", async () => {
  vi.mocked(api.get).mockResolvedValue(catalogue as never);
  vi.mocked(api.put).mockResolvedValue(saved(null) as never);
  const onSaved = vi.fn();
  render(<ActionEditor action={action} actions={[]} terminals={[]} onClose={vi.fn()} onSaved={onSaved} />);
  await screen.findByRole("option", { name: "Workshop Entry ES" });
  fireEvent.change(document.querySelector("select[name=payrollTimeType]")!, { target: { value: "Workshop Entry ES" } });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  expect((await screen.findByRole("alert")).textContent).toContain("did not match the selected value");
  expect(onSaved).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Save changes" })).toBeTruthy();
});

it("keeps the editor open and gives an explicit error when catalogue loading fails", async () => {
  vi.mocked(api.get).mockRejectedValue(new Error("unavailable"));
  render(<ActionEditor action={action} actions={[]} terminals={[]} onClose={vi.fn()} onSaved={vi.fn()} />);
  await screen.findByText(/catalogue failed to load/);
  expect(screen.getByRole("button", { name: "Save changes" }).hasAttribute("disabled")).toBe(true);
  expect(api.put).not.toHaveBeenCalled();
});
