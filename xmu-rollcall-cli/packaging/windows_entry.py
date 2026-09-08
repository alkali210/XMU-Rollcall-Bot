"""Executable entry point; use an absolute import for PyInstaller."""

import sys


if __name__ == "__main__":
    # Frozen Python ignores PYTHONUTF8; redirected Windows output may use GBK.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    from xmu_rollcall.cli import cli

    cli()
