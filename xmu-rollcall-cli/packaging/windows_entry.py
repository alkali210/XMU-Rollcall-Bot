"""Console executable entry point for Nuitka."""

import sys


if __name__ == "__main__":
    # Explicit UTF-8 also keeps redirected Windows output consistent.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    from xmu_rollcall.cli import cli

    cli()
