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
  code: "EXIT_TEST", label: "Existing exit label", supplier_device_event: "local_exit", oracle_supplier_event: "HUT_TCD_SUPP1_OUT_2",
  state_effect: "EXIT", oracle_payroll_time_type: "Payroll A", oracle_attributes: { source: "kept" }, display_order: 12,
  requires_subaction: true, parent_action_code: null, subaction_codes: ["EXIT_CHILD"], visual_key: "scene-a", show_on_terminal: false, active: true,
};
const catalogue: OracleCatalogue = { payroll_time_types: ["Payroll A", "Payroll B"], work_areas: [], machines: [], cells: [] };

it("keeps action workflow fields standard and preserves advanced values through collapse and save", async () => {
  vi.mocked(api.get).mockResolvedValue(catalogue as never);
  vi.mocked(api.put).mockImplementation(async (_url, payload) => ({ ...action, ...(payload as object) }) as never);
  render(<ActionEditor action={action} actions={[action]} terminals={[]} onClose={vi.fn()} onSaved={vi.fn()} />);

  expect(screen.getByLabelText("Label (English)")).toBeTruthy();
  expect(screen.getByLabelText("Direction")).toBeTruthy();
  expect(screen.getByLabelText("Display order")).toBeTruthy();
  const advanced = screen.getByText("Advanced Configuration");
  fireEvent.click(advanced);
  fireEvent.change(screen.getByLabelText("Local action supplier event"), { target: { value: "local_exit_updated" } });
  fireEvent.change(screen.getByLabelText(/Oracle Supplier Event/), { target: { value: "HUT_TCD_SUPP1_OUT_2" } });
  await screen.findByRole("option", { name: "Payroll B" });
  fireEvent.change(screen.getByLabelText(/Oracle Payroll Time Type/), { target: { value: "Payroll B" } });
  fireEvent.change(screen.getByLabelText("Attributes (JSON object)"), { target: { value: '{"source":"updated","flag":true}' } });
  fireEvent.click(advanced);
  fireEvent.click(advanced);
  expect((screen.getByLabelText(/Oracle Payroll Time Type/) as HTMLSelectElement).value).toBe("Payroll B");
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() => expect(api.put).toHaveBeenCalled());
  const payload = vi.mocked(api.put).mock.calls[0][1] as Record<string, unknown>;
  expect(payload).toMatchObject({
    code: "EXIT_TEST", label: "Existing exit label", supplier_device_event: "local_exit_updated", oracle_supplier_event: "HUT_TCD_SUPP1_OUT_2",
    state_effect: "EXIT", oracle_payroll_time_type: "Payroll B", oracle_attributes: { source: "updated", flag: true },
    display_order: 12, requires_subaction: true, parent_action_code: null, visual_key: "scene-a", show_on_terminal: false, active: true,
  });
});

it("reveals Advanced Configuration when a required supplier event is invalid", async () => {
  vi.mocked(api.get).mockResolvedValue(catalogue as never);
  render(<ActionEditor action={action} actions={[action]} terminals={[]} onClose={vi.fn()} onSaved={vi.fn()} />);
  await screen.findByRole("option", { name: "Payroll B" });
  const summary = screen.getByText("Advanced Configuration");
  fireEvent.click(summary);
  fireEvent.change(screen.getByLabelText("Local action supplier event"), { target: { value: "" } });
  fireEvent.click(summary);
  const section = summary.closest("details")!;
  expect(section.open).toBe(false);
  expect(document.querySelector("form")!.reportValidity()).toBe(false);
  expect(section.open).toBe(true);
});
