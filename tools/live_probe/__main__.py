from __future__ import annotations

import sys

from tools.live_probe import analyze, longbridge_probe, session_smoke, sina_probe, tencent_probe


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help"}:
        print(
            "usage: python -m tools.live_probe "
            "{tencent|sina|longbridge|analyze|session} [probe args]"
        )
        return 0
    command, rest = args[0], args[1:]
    if command == "tencent":
        return tencent_probe.main(rest)
    if command == "sina":
        return sina_probe.main(rest)
    if command == "longbridge":
        return longbridge_probe.main(rest)
    if command == "analyze":
        return analyze.main(rest)
    if command == "session":
        return session_smoke.main(rest)
    print(f"unknown probe {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
