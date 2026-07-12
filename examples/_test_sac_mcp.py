"""End-to-end test of sac-mcp against the local SAC install.

Uses a SAC example file as input, then drives every tool via the imported
function (bypassing MCP transport) to confirm the REPL batch wrapping
produces valid SAC output.
"""
import os
import sys
import shutil
import tempfile

sys.path.insert(0, os.path.expanduser("~/src/seismo-mcp/packages/sac-mcp/src"))

from sac_mcp import server as S

SAC_EXAMPLE = os.path.expanduser(
    "~/src/sac/doc/examples/time_shift/sample-run/lpco5np4.sac")


def main():
    # Ensure SAC is discoverable.
    sac_home = os.path.expanduser("~/src/sac")
    os.environ["SACHOME"] = sac_home
    os.environ["SACAUX"] = os.path.join(sac_home, "aux")
    os.environ["PATH"] = os.pathsep.join(
        [os.path.join(sac_home, "bin"), os.environ["PATH"]])

    tmp = tempfile.mkdtemp(prefix="sac_mcp_test_")
    print(f"workdir: {tmp}")

    if not os.path.isfile(SAC_EXAMPLE):
        print(f"SKIP: SAC example file not found at {SAC_EXAMPLE}")
        return

    raw = os.path.join(tmp, "raw.sac")
    shutil.copy(SAC_EXAMPLE, raw)

    # 0) diagnose
    print("\n== diagnose_environment ==")
    print(S.diagnose_environment())

    # 1) listhdr
    print("\n== sac_listhdr ==")
    print(S.sac_listhdr([raw]))

    # 2) preprocess
    proc = os.path.join(tmp, "proc.sac")
    print("\n== sac_preprocess (rtrend+rmean+taper5) ==")
    print(S.sac_preprocess(raw, proc))

    # 3) filter (bandpass)
    filt = os.path.join(tmp, "filt.sac")
    print("\n== sac_filter bandpass 0.05-0.5 Hz ==")
    print(S.sac_filter(raw, filt, filter_type="bandpass",
                       freqmin=0.05, freqmax=0.5))

    # 4) cut — use a window WITHIN the file's [B,E] (this file is B=50.89 E=60.88)
    cut = os.path.join(tmp, "cut.sac")
    print("\n== sac_cut 52.0-55.0 s (within file range) ==")
    print(S.sac_cut(raw, cut, 52.0, 55.0))

    # 5) merge — identical files (compatible) to exercise the command path
    merged = os.path.join(tmp, "merged.sac")
    print("\n== sac_merge [raw, raw-copy] ==")
    print(S.sac_merge([raw, raw], merged))

    # Sanity: every output must be a non-trivial SAC file (header is 632 bytes).
    print("\n== output file sizes (must be > 632) ==")
    for f in [proc, filt, cut, merged]:
        sz = os.path.getsize(f) if os.path.exists(f) else 0
        mark = "✓" if sz > 632 else "✗ TOO SMALL"
        print(f"  {os.path.basename(f):14s} {sz} bytes {mark}")
        assert sz > 632, f"{f} too small ({sz})"

    # Verify data actually changed after filter (proves the op ran, not just copy).
    import numpy as np
    def _data(p):
        with open(p, "rb") as fh:
            fh.read(632)
            return np.frombuffer(fh.read(), dtype="<f4")
    d_raw = _data(raw)
    d_filt = _data(filt)
    changed = not np.allclose(d_raw, d_filt)
    print(f"\nfilter changed data: {changed} (std {d_raw.std():.3e} → {d_filt.std():.3e})")
    assert changed, "filter did not alter data"

    print("\nALL SAC TOOLS PASSED ✅")


if __name__ == "__main__":
    main()
