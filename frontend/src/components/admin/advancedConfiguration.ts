import type { FormEvent } from "react";

export function revealInvalidAdvancedField(event: FormEvent<HTMLFormElement>) {
  const field = event.target;
  if (!(field instanceof HTMLElement)) return;
  const advancedSection = field.closest("details");
  if (!(advancedSection instanceof HTMLDetailsElement) || advancedSection.open) return;

  advancedSection.open = true;
  requestAnimationFrame(() => field.focus());
}
