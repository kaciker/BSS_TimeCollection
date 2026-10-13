// Keyboard-wedge timing is a heuristic: ordinary slow typing never completes a scan.
export class KeyboardWedge {
  private buffer = "";
  private lastAt = 0;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private lastBadge = "";
  private submittedAt = -Infinity;
  constructor(private submit: (badge: string) => void) {}

  reset = () => {
    clearTimeout(this.timer);
    this.buffer = "";
    this.lastAt = 0;
  };

  private finish = () => {
    const badge = this.buffer;
    this.reset(); // Enter and timeout can consume a buffer only once.
    if (badge.length < 4 || badge.length > 160) return;
    const now = performance.now();
    if (badge === this.lastBadge && now - this.submittedAt < 1000) return;
    this.lastBadge = badge;
    this.submittedAt = now;
    this.submit(badge);
  };

  keydown = (event: KeyboardEvent) => {
    const target = event.target instanceof Element ? event.target : null;
    if (event.ctrlKey || event.altKey || event.metaKey || event.repeat || event.isComposing ||
        target?.closest("input, textarea, [contenteditable]:not([contenteditable='false'])")) {
      this.reset();
      return;
    }
    const now = performance.now();
    if (event.key === "Enter") {
      if (this.buffer.length >= 4 || now - this.submittedAt < 150) event.preventDefault();
      this.finish();
      return;
    }
    if (this.buffer && now - this.lastAt > 50) this.reset();
    if (event.key.length !== 1 || /\s|[\x00-\x1f\x7f]/.test(event.key)) {
      // Shift can precede characters on alphanumeric readers.
      if (event.key !== "Shift") this.reset();
      return;
    }
    this.buffer += event.key;
    this.lastAt = now;
    clearTimeout(this.timer);
    if (this.buffer.length > 160) { this.reset(); return; }
    this.timer = setTimeout(this.finish, 100);
  };
}
