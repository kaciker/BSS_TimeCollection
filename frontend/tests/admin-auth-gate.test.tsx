// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { AdminAuthGate } from "../src/components/AdminAuthGate";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("renders the temporary admin sign-in form for an anonymous session", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ authenticated: false, username: null }),
    }),
  );

  render(
    <AdminAuthGate>
      <div>Protected admin page</div>
    </AdminAuthGate>,
  );

  expect(await screen.findByRole("heading", { name: "Admin access" })).toBeTruthy();
  expect(screen.getByLabelText("Username")).toBeTruthy();
  expect(screen.getByLabelText("Password")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Sign in" })).toBeTruthy();
  expect(screen.queryByText("Protected admin page")).toBeNull();
});
