"""Self-contained helpers for sac-mcp.

Inlined (no shared-package dependency) so this server publishes and installs
standalone via ``uvx sac-mcp``.

SAC is fundamentally different from CWP-SU: it is an **interactive REPL**
(like a seismology-oriented Python prompt), not a family of one-shot pipe
programs. So the core helper here, :func:`run_sac_batch`, feeds a *script* of
SAC commands to the interpreter's stdin, lets it run, and captures the
session log. The pattern is:

    printf 'r file.sac\\nrmean\\nbp co 0.1 1.0\\nw out.sac\\nq\\n' | sac

A second helper, :func:`saclst`, wraps the standalone ``saclst`` binary for
fast header reads without spinning up the whole REPL.

One macOS-specific quirk handled here: SAC's bundled ``sacinit.sh`` hard-codes
``SACHOME=/usr/local/sac``, which is wrong on user-dir installs. We override
``SACHOME``/``SACAUX`` from the *detected* root before every launch — without
``SACAUX`` SAC exits immediately with "aux directory not Found".
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass

DEFAULT_TIMEOUT = 120  # SAC REPL sessions are usually quick


@dataclass
class SACResult:
    """Outcome of a SAC batch session."""

    returncode: int
    log: str          # the full SAC session transcript (stdout)
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def error_text(self) -> str:
        tag = "TIMEOUT" if self.timed_out else f"exit {self.returncode}"
        # Surface ERROR lines from the log; they're what the user/agent needs.
        errs = [ln for ln in self.log.splitlines() if "ERROR" in ln.upper()]
        snippet = "\n".join(errs[:20]) or self.log.strip()[:2000]
        return f"SAC session failed ({tag}):\n{snippet}"


def detect_sac() -> dict:
    """Locate the local SAC installation (SACHOME)."""
    roots = [
        os.environ.get("SACHOME"),
        os.path.expanduser("~/src/sac"),
        "/usr/local/sac",
    ]
    for root in roots:
        if not root or not os.path.isfile(os.path.join(root, "bin", "sac")):
            continue
        return {
            "available": True,
            "root": root,
            "bin": os.path.join(root, "bin"),
            "aux": os.path.join(root, "aux"),
            "detail": f"SAC found at {root}",
        }
    return {
        "available": False, "root": None, "bin": None, "aux": None,
        "detail": (
            "SAC not found. Set SACHOME (and SACAUX) or install under "
            "~/src/sac or /usr/local/sac."
        ),
    }


def _sac_env() -> dict:
    """Launch env: SAC bin on PATH + SACHOME/SACAUX set from detected root.

    This override is essential — sacinit.sh hardcodes /usr/local/sac, so
    without it a user-dir install fails with 'aux directory not Found'.
    """
    env = os.environ.copy()
    info = detect_sac()
    if info["available"]:
        env["PATH"] = os.pathsep.join([info["bin"], env.get("PATH", "")])
        env["SACHOME"] = info["root"]
        env["SACAUX"] = info["aux"]
    return env


def run_sac_batch(
    commands: list[str],
    *,
    cwd: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> SACResult:
    """Feed a *script* of SAC commands to the interpreter and return the log.

    *commands* is a list of bare SAC commands WITHOUT trailing newlines (e.g.
    ``["r file.sac", "rmean", "bp co 0.1 1.0", "w out.sac", "q"]``). A
    ``QUIT`` is appended automatically if not present.
    """
    env = _sac_env()
    exe = shutil.which("sac", path=env["PATH"])
    if exe is None:
        raise FileNotFoundError(
            f"SAC 'sac' interpreter not found on PATH. {detect_sac()['detail']}"
        )

    script = "\n".join(commands)
    if commands and commands[-1].strip().lower() not in ("q", "quit"):
        script += "\nquit"
    script += "\n"

    try:
        proc = subprocess.run(  # noqa: S603
            [exe],
            input=script,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return SACResult(returncode=-1, log="", timed_out=True)

    # SAC writes everything to stdout; stderr is usually empty.
    return SACResult(returncode=proc.returncode, log=(proc.stdout or ""))


def saclst(
    fields: list[str],
    files: list[str],
    *,
    timeout: float = 30,
) -> str:
    """Run the standalone ``saclst`` for fast header reads (no REPL).

    Syntax: ``saclst f <file> <field1> <field2> ...`` — note the ``f``
    marker before the filename. Returns the raw text output.
    """
    env = _sac_env()
    exe = shutil.which("saclst", path=env["PATH"])
    if exe is None:
        raise FileNotFoundError("SAC 'saclst' not found on PATH.")

    # saclst syntax (from its selfdoc): <fields...> f <files...>
    args = [exe, *fields, "f", *files]
    try:
        proc = subprocess.run(  # noqa: S603
            args, capture_output=True, text=True,
            timeout=timeout, env=env, check=False,
        )
    except subprocess.TimeoutExpired:
        return "saclst TIMEOUT"
    if proc.returncode != 0:
        return f"saclst failed (exit {proc.returncode}):\n{(proc.stderr or '').strip()}"
    return proc.stdout.strip()
