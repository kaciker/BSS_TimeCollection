"""Preview or send exactly one explicitly selected Oracle event."""

import argparse
import json
import sys

from app.services.oracle_delivery import send_one_event


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-id", required=True, help="Exact BSS TimeEvent UUID")
    parser.add_argument("--confirm-request-number", help="Required exact event requestNumber for --send")
    parser.add_argument("--send", action="store_true", help="Transmit this one event exactly once")
    args = parser.parse_args(argv)
    try:
        result = send_one_event(
            args.event_id,
            send=args.send,
            confirm_request_number=args.confirm_request_number,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
