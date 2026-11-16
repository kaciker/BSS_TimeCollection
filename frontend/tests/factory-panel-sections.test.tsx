// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { FactoryPanel } from "../src/components/admin/FactoryPanel";
import { api } from "../src/api";
import type { Factory, InstallationSettings } from "../src/types";

vi.mock("../src/api", () => ({ api: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
const factory: Factory = { id: 7, code: "PLANT_A", name: "Factory A", location: "North", country: "ES", timezone: "Europe/Madrid", active: true, created_at: "", updated_at: "" };
const settings: InstallationSettings = { default_factory_code: "PLANT_A", default_factory: factory, configuration_error: null };
const setup = () => vi.mocked(api.get).mockImplementation(async path => path.endsWith("/factories") ? [factory] : settings as never);

it("keeps factory identity/default normal and saves advanced details without changing timezone or status", async () => {
  setup();
  vi.mocked(api.put).mockImplementation(async (_url, payload) => payload as never);
  render(<FactoryPanel />);
  await screen.findByText("Factory A");
  expect((screen.getByLabelText("Default factory") as HTMLSelectElement).value).toBe("PLANT_A");
  fireEvent.click(screen.getByRole("button", { name: "Edit" }));
  expect(screen.getAllByLabelText("Factory code").length).toBe(2);
  expect(screen.getAllByLabelText("Factory name").length).toBe(2);
  expect(screen.getByLabelText("Active status")).toBeTruthy();
  const advanced = screen.getAllByText("Advanced Configuration")[0];
  fireEvent.click(advanced);
  fireEvent.change(screen.getAllByLabelText("Location")[0], { target: { value: "South" } });
  fireEvent.change(screen.getAllByLabelText("Country")[0], { target: { value: "PT" } });
  expect((screen.getAllByLabelText("Timezone")[0] as HTMLInputElement).value).toBe("Europe/Madrid");
  expect((screen.getAllByLabelText("Timezone")[0] as HTMLInputElement).readOnly).toBe(true);
  fireEvent.click(advanced);
  fireEvent.click(screen.getByRole("button", { name: "Save factory" }));
  await waitFor(() => expect(api.put).toHaveBeenCalledWith("/api/v1/admin/factories/7", { name: "Factory A", location: "South", country: "PT", timezone: "Europe/Madrid" }));
  expect(api.put).toHaveBeenCalledTimes(1);
});

it("places optional location, country and current timezone under Advanced when creating", async () => {
  setup();
  vi.mocked(api.post).mockResolvedValue(factory as never);
  render(<FactoryPanel />);
  await screen.findByText("Factory A");
  expect(screen.getByLabelText("Factory code")).toBeTruthy();
  expect(screen.getByLabelText("Factory name")).toBeTruthy();
  expect(screen.getAllByLabelText("Location").length).toBe(1);
  expect((screen.getAllByLabelText("Location")[0] as HTMLInputElement).closest("details")?.open).toBe(false);
  fireEvent.click(screen.getAllByText("Advanced Configuration")[0]);
  fireEvent.change(screen.getAllByLabelText("Location")[0], { target: { value: "West" } });
  fireEvent.change(screen.getAllByLabelText("Country")[0], { target: { value: "ES" } });
  fireEvent.change(screen.getAllByLabelText("Timezone")[0], { target: { value: "Europe/Lisbon" } });
  fireEvent.change(screen.getByLabelText("Factory code"), { target: { value: "NEW_PLANT" } });
  fireEvent.change(screen.getByLabelText("Factory name"), { target: { value: "New Plant" } });
  fireEvent.click(screen.getByRole("button", { name: "Create factory" }));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/v1/admin/factories", { code: "NEW_PLANT", name: "New Plant", location: "West", country: "ES", timezone: "Europe/Lisbon" }));
});

it("reveals Advanced Configuration when a required factory timezone is invalid", async () => {
  setup();
  render(<FactoryPanel />);
  await screen.findByText("Factory A");
  fireEvent.change(screen.getByLabelText("Factory code"), { target: { value: "NEW_PLANT" } });
  fireEvent.change(screen.getByLabelText("Factory name"), { target: { value: "New Plant" } });
  const advanced = screen.getAllByText("Advanced Configuration")[0];
  fireEvent.click(advanced);
  fireEvent.change(screen.getAllByLabelText("Timezone")[0], { target: { value: "" } });
  fireEvent.click(advanced);
  expect(advanced.closest("details")?.open).toBe(false);
  expect(document.querySelectorAll("form")[0].reportValidity()).toBe(false);
  expect(advanced.closest("details")?.open).toBe(true);
});
