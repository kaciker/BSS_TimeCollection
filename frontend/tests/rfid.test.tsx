// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { KeyboardWedge } from "../src/keyboardWedge";
import { TerminalPage } from "../src/pages/TerminalPage";
import { api } from "../src/api";
vi.mock("../src/api", () => ({ api: { get: vi.fn(), post: vi.fn() } }));
const card = "00098765AB";
const key = (value: string, target: EventTarget = window, options = {}) =>
  target.dispatchEvent(new KeyboardEvent("keydown", { key: value, bubbles: true, cancelable: true, ...options }));
const burst = (value = card, enter = true, delay = 8) => {
  for (const character of value) { key(character); vi.advanceTimersByTime(delay); }
  if (enter) key("Enter");
};
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date", "performance"] });
  vi.spyOn(document, "hasFocus").mockReturnValue(true);
  localStorage.setItem("bss-timecollection-language", "en");
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); vi.clearAllMocks(); });
describe("keyboard wedge", () => {
  let reader: KeyboardWedge;
  let submit: ReturnType<typeof vi.fn>;
  beforeEach(() => { submit = vi.fn(); reader = new KeyboardWedge(submit); window.addEventListener("keydown", reader.keydown); });
  afterEach(() => { reader.reset(); window.removeEventListener("keydown", reader.keydown); });
  it("rapid Enter scan preserves string and completes once despite timeout", () => {
    burst(); vi.advanceTimersByTime(300); expect(submit).toHaveBeenCalledExactlyOnceWith(card);
  });
  it("ignores spaces and Tab separators inserted between badge characters", () => {
    for (const character of "0582609699") {
      key(character); vi.advanceTimersByTime(8);
      key(" "); vi.advanceTimersByTime(8);
    }
    const tab = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
    window.dispatchEvent(tab); vi.advanceTimersByTime(8); key("Enter");
    expect(tab.defaultPrevented).toBe(true);
    expect(submit).toHaveBeenCalledExactlyOnceWith("0582609699");
  });
  it("timeout fallback completes once", () => {
    burst(card, false); vi.advanceTimersByTime(100); key("Enter"); expect(submit).toHaveBeenCalledExactlyOnceWith(card);
  });
  it("slow typing and short bursts do not scan", () => {
    burst(card, true, 150); burst("123"); vi.advanceTimersByTime(200); expect(submit).not.toHaveBeenCalled();
  });
  it("accepts a slightly delayed Enter and suppresses its default button activation", () => {
    burst(card, false); vi.advanceTimersByTime(60);
    const event = new KeyboardEvent("keydown", { key: "Enter", cancelable: true });
    window.dispatchEvent(event); expect(event.defaultPrevented).toBe(true);
    expect(submit).toHaveBeenCalledExactlyOnceWith(card);
  });
  it("late Enter after timeout cannot activate the focused button", () => {
    burst(card, false); vi.advanceTimersByTime(100);
    const event = new KeyboardEvent("keydown", { key: "Enter", cancelable: true });
    window.dispatchEvent(event); expect(event.defaultPrevented).toBe(true);
    expect(submit).toHaveBeenCalledTimes(1);
  });
  it("same physical scan is debounced", () => { burst(); burst(); expect(submit).toHaveBeenCalledTimes(1); });
  it("rejects oversized identifiers", () => { burst("X".repeat(161)); expect(submit).not.toHaveBeenCalled(); });
  it.each(["input", "textarea", "div"])("ignores typing in editable %s", tag => {
    const element = document.createElement(tag); if (tag === "div") element.contentEditable = "true";
    if (tag === "div") element.setAttribute("contenteditable", "true");
    document.body.append(element);
    for (const c of card) { key(c, element); vi.advanceTimersByTime(8); }
    key("Enter", element); expect(submit).not.toHaveBeenCalled(); element.remove();
  });
  it("ignores shortcuts/repeats/navigation and resets incomplete scans", () => {
    for (const options of [{ ctrlKey: true }, { altKey: true }, { metaKey: true }, { repeat: true }]) {
      for (const c of card) key(c, window, options); key("Enter");
    }
    burst("123", false); key("ArrowLeft"); burst("456", true);
    expect(submit).not.toHaveBeenCalled();
  });
});
async function terminal(mode: string) {
  vi.mocked(api.get).mockResolvedValue({ code: "TEST", name: "Test clock", identification_mode: mode, exit_menu_timeout_seconds: 5, actions: [] });
  await act(async () => { render(<TerminalPage />); });
}
async function scan(value = card) { await act(async () => { burst(value); }); }
describe("terminal RFID flow", () => {
  it.each(["RFID", "BOTH"])("%s scan uses explicit RFID reporter and locks pending request", async mode => {
    vi.mocked(api.post).mockImplementation(() => new Promise(() => {}));
    await terminal(mode); await scan(); await scan("99999999");
    expect(api.post).toHaveBeenCalledExactlyOnceWith("/api/v1/terminal/scan", { reporter_id: card, identification_method: "RFID" });
    expect(screen.getByText("Reading card…")).toBeTruthy();
  });
  it("KEYPAD does not listen to reader input", async () => { await terminal("KEYPAD"); await scan(); expect(api.post).not.toHaveBeenCalled(); });
  it("KEYPAD accepts typed and pasted digits and submits with Enter", async () => {
    vi.mocked(api.post).mockResolvedValue({ flow: "ENTRY_RECORDED", event: { event_datetime: new Date().toISOString() } });
    await terminal("KEYPAD");
    const input = screen.getByRole("textbox", { name: "Enter badge number" });
    fireEvent.change(input, { target: { value: "00012345" } });
    await act(async () => { fireEvent.keyDown(input, { key: "Enter" }); });
    expect(api.post).toHaveBeenCalledWith("/api/v1/terminal/scan", { reporter_id: "00012345", identification_method: "KEYPAD" });
  });
  it("manual keypad remains KEYPAD in BOTH", async () => {
    vi.mocked(api.post).mockResolvedValue({ flow: "ENTRY_RECORDED", event: { event_datetime: new Date().toISOString() } });
    await terminal("BOTH"); fireEvent.click(screen.getByRole("button", { name: "1", exact: true }));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Continue" })); });
    expect(api.post).toHaveBeenCalledWith("/api/v1/terminal/scan", { reporter_id: "1", identification_method: "KEYPAD" });
  });
  it("reporter and RFID method survive exit and sub-action selection; other scans cannot replace them", async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ flow: "EXIT_REQUIRED", actions: [{ code: "FACTORY_EXIT", label: "Factory exit", has_subactions: true }] })
      .mockResolvedValueOnce({ flow: "SUBACTION_REQUIRED", actions: [{ code: "MEDICAL", label: "Medical" }] })
      .mockResolvedValueOnce({ flow: "EXIT_RECORDED", event: { event_datetime: new Date().toISOString() } });
    await terminal("BOTH"); await scan(); await scan("77777777");
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Factory exit ›" })); });
    expect(api.post).toHaveBeenLastCalledWith("/api/v1/terminal/exit", { reporter_id: card, identification_method: "RFID", action_code: "FACTORY_EXIT" });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Medical" })); });
    expect(api.post).toHaveBeenLastCalledWith("/api/v1/terminal/exit", { reporter_id: card, identification_method: "RFID", action_code: "MEDICAL" });
    expect(api.post).toHaveBeenCalledTimes(3);
  });
  it.each([0, 5, 120])( "exit menu timeout %i seconds", async timeout => {
    vi.mocked(api.get).mockResolvedValue({ code: "TEST", name: "Test clock", identification_mode: "KEYPAD", exit_menu_timeout_seconds: timeout, actions: [] });
    vi.mocked(api.post).mockResolvedValue({ flow: "EXIT_REQUIRED", worker_state: "INSIDE", actions: [{ code: "STOP", label: "Stop" }] });
    await act(async () => { render(<TerminalPage />); });
    await act(async () => { fireEvent.change(screen.getByRole("textbox", { name: "Enter badge number" }), { target: { value: "00123" } }); fireEvent.click(screen.getByRole("button", { name: "Continue" })); });
    expect(screen.getByText("Select the reason for leaving")).toBeTruthy();
    if (timeout === 0) {
      await act(async () => { vi.advanceTimersByTime(121_000); });
      expect(screen.getByText("Select the reason for leaving")).toBeTruthy();
    } else {
      await act(async () => { vi.advanceTimersByTime(timeout * 1000 - 1); });
      expect(screen.getByText("Select the reason for leaving")).toBeTruthy();
      await act(async () => { vi.advanceTimersByTime(1); });
      expect(screen.queryByText("Select the reason for leaving")).toBeNull();
      expect(screen.getByRole("textbox", { name: "Enter badge number" })).toBeTruthy();
    }
  });
  it("restarts the full exit menu timeout after an action fails", async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ flow: "EXIT_REQUIRED", actions: [{ code: "STOP", label: "Stop" }] })
      .mockRejectedValueOnce(new Error("Exit rejected by policy"));
    await terminal("KEYPAD");
    await act(async () => { fireEvent.change(screen.getByRole("textbox", { name: "Enter badge number" }), { target: { value: "00123" } }); fireEvent.click(screen.getByRole("button", { name: "Continue" })); });
    await act(async () => { vi.advanceTimersByTime(4000); });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Stop" })); });
    expect(screen.getByText("Exit rejected by policy")).toBeTruthy();
    await act(async () => { vi.advanceTimersByTime(4999); });
    expect(screen.getByText("Select the reason for leaving")).toBeTruthy();
    await act(async () => { vi.advanceTimersByTime(1); });
    expect(screen.queryByText("Select the reason for leaving")).toBeNull();
  });
  it("returns API errors and allows a subsequent scan", async () => {
    vi.mocked(api.post).mockRejectedValueOnce(new Error("Exit rejected by policy"))
      .mockResolvedValueOnce({ flow: "ENTRY_RECORDED", event: { event_datetime: new Date().toISOString() } });
    await terminal("RFID"); await scan(); expect(screen.getByText("Exit rejected by policy")).toBeTruthy();
    await scan("77777777"); expect(api.post).toHaveBeenCalledTimes(2);
  });
  it("unprovisioned browser does not capture scans", async () => {
    vi.mocked(api.get).mockRejectedValue(new Error("Not provisioned"));
    vi.mocked(api.post).mockResolvedValue({ pairing_code: "TEST-CODE", expires_at: new Date().toISOString(), poll_after_seconds: 2 });
    await act(async () => { render(<TerminalPage />); }); await scan();
    expect(api.post).toHaveBeenCalledTimes(1); expect(api.post).toHaveBeenCalledWith("/api/v1/terminal/pairing", {});
  });
});

describe("perimeter terminal feedback", () => {
  it.each([
    ["DUPLICATE_IGNORED", "Scan already recorded"],
    ["ALREADY_INSIDE", "Badge already inside factory"],
    ["ALREADY_OUTSIDE", "Badge already outside factory"],
    ["FACTORY_ENTRY_RECORDED", "Entry registered"],
    ["FACTORY_EXIT_RECORDED", "Exit registered"],
  ])("%s returns readable feedback and retains the RFID UID", async (flow, feedback) => {
    vi.mocked(api.post).mockResolvedValue({ flow, worker_state: "OUTSIDE", actions: [], event: null });
    await terminal("RFID"); await scan();
    expect(screen.getByText(feedback)).toBeTruthy();
    expect(api.post).toHaveBeenCalledExactlyOnceWith("/api/v1/terminal/scan", { reporter_id: card, identification_method: "RFID" });
    await act(async () => { vi.advanceTimersByTime(2200); });
    expect(screen.queryByText(feedback)).toBeNull();
  });
});
