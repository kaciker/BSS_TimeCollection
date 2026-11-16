// @vitest-environment jsdom
import { afterEach, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { revealInvalidAdvancedField } from "../src/components/admin/advancedConfiguration";

afterEach(cleanup);

it("opens and focuses a collapsed Advanced Configuration section for native required-field validation", async () => {
  const { container } = render(
    <form onInvalidCapture={revealInvalidAdvancedField}>
      <details>
        <summary>Advanced Configuration</summary>
        <input aria-label="Required advanced value" required />
      </details>
    </form>,
  );
  const details = container.querySelector("details")!;
  const required = container.querySelector("input")!;

  expect(details.open).toBe(false);
  expect(container.querySelector("form")!.reportValidity()).toBe(false);
  expect(details.open).toBe(true);
  await new Promise(resolve => requestAnimationFrame(resolve));
  expect(document.activeElement).toBe(required);
});
