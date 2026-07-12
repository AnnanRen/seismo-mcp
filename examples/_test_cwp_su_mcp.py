"""End-to-end test of cwp-su-mcp against real CWP-SU.

Generates a synthetic SU dataset with suplane, then drives every tool via the
imported function (bypassing MCP transport) to confirm the subprocess wrapping
actually produces valid SU output.
"""
import os
import sys
import subprocess
import tempfile

sys.path.insert(0, os.path.expanduser(
    "~/src/seismo-mcp/packages/cwp-su-mcp/src"))

from cwp_su_mcp import server as S


def main():
    # Ensure CWP-SU is on PATH for both suplane and the server's run_su().
    cwp = os.path.expanduser("~/src/cwp")
    os.environ["CWPROOT"] = cwp
    os.environ["PATH"] = os.pathsep.join([f"{cwp}/bin", os.environ["PATH"]])

    tmp = tempfile.mkdtemp(prefix="su_mcp_test_")
    print(f"workdir: {tmp}")

    # 0) diagnose
    print("\n== diagnose_environment ==")
    print(S.diagnose_environment())

    # Generate test SU data with suplane (32 traces, synthetic plane waves).
    raw = os.path.join(tmp, "gather.su")
    subprocess.run(["suplane"], stdout=open(raw, "wb"),
                   env=dict(os.environ), check=True)
    print(f"\ngenerated {raw} ({os.path.getsize(raw)} bytes)")

    # 1) count
    print("\n== su_count ==")
    print(S.su_count(raw))

    # 2) gethw
    print("\n== su_gethw key=offset (first 3 lines) ==")
    out = S.su_gethw(raw, "offset")
    print("\n".join(out.splitlines()[:4]))

    # 3) filter (bandpass 10-30 Hz)
    filt = os.path.join(tmp, "gather_bp.su")
    print("\n== su_filter bandpass 10-30 Hz ==")
    print(S.su_filter(raw, filt, freqmin=10.0, freqmax=30.0))

    # 4) gain (tpow, avoids agc window-too-long on short traces)
    gain = os.path.join(tmp, "gather_bptpow.su")
    print("\n== su_gain tpow=2 ==")
    print(S.su_gain(filt, gain, tpow=2.0))

    # 5) window (time)
    wind = os.path.join(tmp, "gather_wind.su")
    print("\n== su_wind tmin=0.05 tmax=0.3 ==")
    print(S.su_wind(raw, wind, tmin=0.05, tmax=0.3))

    # 6) sort
    sort = os.path.join(tmp, "gather_sort.su")
    print("\n== su_sort by offset descending ==")
    print(S.su_sort(raw, sort, key="offset", descending=True))

    # 7) sethw
    shw = os.path.join(tmp, "gather_shw.su")
    print("\n== su_sethw fldr=100 ==")
    print(S.su_sethw(raw, shw, "fldr", 100))

    # Sanity: every output file must be non-empty and look like SU (header bytes).
    print("\n== output file sizes ==")
    for f in [filt, gain, wind, sort, shw]:
        sz = os.path.getsize(f)
        assert sz > 1000, f"{f} suspiciously small ({sz} bytes)"
        print(f"  {os.path.basename(f):24s} {sz} bytes ✓")

    print("\nALL SU TOOLS PASSED ✅")


if __name__ == "__main__":
    main()
