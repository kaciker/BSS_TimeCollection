# RFID keyboard-wedge support

USB HID readers that type a badge ID as a rapid keyboard burst work on the
operational terminal page after browser provisioning. Enable `RFID` or `BOTH`
in the terminal configuration. `KEYPAD` terminals do not listen for scans.

The active T&A browser/window must have focus. The operating system sends the
reader's keystrokes to its currently active window, so scanning with another
application focused sends the ID to that application. Keep T&A active or use a
kiosk deployment. This implementation does not capture background OS input.

## Capture and flow

The parser accepts non-whitespace printable characters at intervals of up to
50 ms. A burst must contain 4–160 characters. Enter completes it; 100 ms of
inactivity provides a fallback. Slow typing, short bursts, modifier shortcuts,
repeats, composition, navigation and editable fields are ignored. Focus loss or
visibility changes clear partial input. Timing is a scanner heuristic, not a
hardware identity guarantee; unusually fast human typing can resemble a reader.

IDs remain strings, with no numeric conversion or fixed ten-digit requirement.
The scanned value goes directly to `/api/v1/terminal/scan` with method `RFID`.
The same ID and method are retained through exit and sub-action selection.
Manual keypad submission always uses `KEYPAD`, including in BOTH mode.

A buffer is consumed once, preventing Enter/timeout duplicates. Identical scans
within one second are suppressed. Requests use an immediate lock; scans during
processing, exit selection or the 2.2-second confirmation cannot replace the
current person. Existing policy/API errors remain visible; an error releases
the request lock so a subsequent deliberate scan can retry.

## Operator check with the physical reader

1. Use an already provisioned browser on a terminal configured as RFID or BOTH.
   Open `/terminal`, reload once to obtain the new frontend, and keep it focused.
2. Present a card once. Expect one entry confirmation, or exit selection if its
   last local event is ENTER. In event logs, check the exact ID (including leading
   zeros) and `identification_method=RFID`.
3. After entry confirmation clears, scan again and select Factory exit, then
   Medical. Check that one final exit event has the same ID and RFID method;
   opening the parent menu alone must not record an exit.
4. In BOTH mode, enter an ID with the on-screen keypad and Continue; check keypad
   capture as `identification_method=KEYPAD`.
5. Scan while another window is active; T&A must not capture it. Restore T&A
   focus before the next scan. Policy rejection may be expected when the entry
   terminal/work cell differs; do not change production policies to bypass it.

Automated validation uses fake-timer parser/React tests and synthetic browser
keyboard input with mocked APIs. These do not constitute physical reader testing
and create no production attendance records. Run frontend tests with `npm test`;
the web Docker build also runs them before TypeScript/Vite compilation.
