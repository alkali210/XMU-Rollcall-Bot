"""Check the frozen CLI without credentials or network requests."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    executable = Path(sys.argv[1]).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="xmu-exe-smoke-") as directory:
        env = dict(os.environ, XMU_ROLLCALL_CONFIG_DIR=directory, PYTHONUTF8="1")
        for args, user_input, expected_code, expected_text in [
            (["--help"], "", 0, "Commands:"),
            ([], "", 0, "Welcome back"),
            (["config"], "q\n", 0, "Configuration"),
            (["start"], "", 1, "Configuration incomplete"),
        ]:
            result = subprocess.run(
                [str(executable), *args], input=user_input, capture_output=True,
                text=True, encoding="utf-8", errors="replace", env=env,
                cwd=directory, timeout=60,
            )
            output = result.stdout + result.stderr
            if result.returncode != expected_code or expected_text not in output:
                raise RuntimeError(f"EXE check failed for {args}: {result.returncode}\n{output}")
            print(f"Passed: {args or ['interactive / EOF']}")


if __name__ == "__main__":
    main()
