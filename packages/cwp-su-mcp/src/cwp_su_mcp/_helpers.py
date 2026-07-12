"""Self-contained helpers for cwp-su-mcp.

Inlined (no shared-package dependency) so this server publishes and installs
standalone via ``uvx cwp-su-mcp``. The bits here — safe subprocess execution
and CWP-SU environment detection — are the price of independence.

CWP-SU programs follow a strict Unix-pipe discipline: each reads SU-format
traces from stdin and writes processed traces to stdout. That makes them
composable (``sufilter | sugain | suximage``) but also means our wrapper must
feed stdin and drain stdout concurrently to avoid pipe deadlocks — exactly
what :func:`run_su` below does via ``capture_output=True``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass

DEFAULT_TIMEOUT = 300  # seconds; override per-call for long gathers


@dataclass
class SUResult:
    """Normalized outcome of a CWP-SU program invocation."""

    returncode: int
    stdout: bytes  # SU trace data on stdout (binary!) — never decode to str
    stderr: str    # human-readable diagnostics/errors on stderr
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def error_text(self) -> str:
        """A context-friendly error summary (call only when not ok)."""
        tag = "TIMEOUT" if self.timed_out else f"exit {self.returncode}"
        # stderr is usually short (a line or two from CWP); keep it whole
        return f"sufilter failed ({tag}):\n{self.stderr.strip()[:2000]}"


def detect_su() -> dict:
    """Locate the local CWP-SU installation.

    Returns a dict with ``available``, ``root`` (CWPROOT), ``bin``, and a
    ``detail`` string. Probes CWPROOT env, then common roots.
    """
    roots = [
        os.environ.get("CWPROOT"),
        os.path.expanduser("~/src/cwp"),
        "/usr/local/cwp",
    ]
    for root in roots:
        if not root or not os.path.isdir(os.path.join(root, "bin")):
            continue
        sample = os.path.join(root, "bin", "sugethw")
        if os.path.isfile(sample):
            return {
                "available": True,
                "root": root,
                "bin": os.path.join(root, "bin"),
                "detail": f"CWP-SU found at {root}",
            }
    return {
        "available": False,
        "root": None,
        "bin": None,
        "detail": (
            "CWP-SU not found. Set CWPROOT (and put $CWPROOT/bin on PATH) or "
            "install it under ~/src/cwp or /usr/local/cwp."
        ),
    }


def _su_env() -> dict:
    """Build the launch env: CWP-SU bin on PATH + CWPROOT set."""
    env = os.environ.copy()
    info = detect_su()
    if info["available"]:
        env["PATH"] = os.pathsep.join([info["bin"], env.get("PATH", "")])
        env["CWPROOT"] = info["root"]
    return env


def run_su(
    program: str,
    args: list[str],
    *,
    stdin: bytes | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    stdout_to: str | None = None,
) -> SUResult:
    """Run a CWP-SU *program* with *args*, feeding *stdin* (SU trace data).

    This is the single chokepoint every tool below funnels through, so all
    the safety rules live here:

    - the program is resolved via PATH against the CWP env (clear error if
      missing, instead of an opaque subprocess failure);
    - ``capture_output=True`` drains stdout+stderr concurrently — no deadlock
      (unless *stdout_to* is given, see below);
    - a ``timeout`` caps every call so a hung trace can't wedge the server;
    - stdout stays ``bytes`` because SU traces are binary — decoding them as
      text would corrupt them silently.

    *stdout_to*: a few CWP-SU programs (notably ``susort``) refuse to write
    to a pipe and require output to a disk file ("PIPE->DISK" only). For
    those, pass the output path here; the program writes the file directly,
    avoiding an unsupported stdout pipe. The returned ``stdout`` is then
    empty and the caller should read from *stdout_to*.

    To chain two programs (e.g. filter then gain), call run_su twice and feed
    the first result's stdout into the next call's stdin.
    """
    env = _su_env()
    exe = shutil.which(program, path=env["PATH"])
    if exe is None:
        raise FileNotFoundError(
            f"CWP-SU program {program!r} not found on PATH. "
            f"Is CWP-SU installed? {detect_su()['detail']}"
        )

    try:
        if stdout_to is not None:
            # Program writes directly to a file (for PIPE->DISK-only tools
            # like susort). stderr still captured to memory.
            with open(stdout_to, "wb") as fout:
                proc = subprocess.run(  # noqa: S603
                    [exe, *args],
                    input=stdin,
                    stdout=fout,
                    stderr=subprocess.PIPE,
                    timeout=timeout,
                    env=env,
                    check=False,
                )
            return SUResult(
                returncode=proc.returncode,
                stdout=b"",  # written to file
                stderr=(proc.stderr or b"").decode("utf-8", errors="replace"),
            )
        proc = subprocess.run(  # noqa: S603 — exe resolved, args list
            [exe, *args],
            input=stdin,
            capture_output=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return SUResult(returncode=-1, stdout=b"", stderr="", timed_out=True)

    return SUResult(
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=(proc.stderr or b"").decode("utf-8", errors="replace"),
    )
