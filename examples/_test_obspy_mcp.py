"""End-to-end test of obspy-mcp tools using a synthetic waveform.

This directly invokes the tool functions (bypassing MCP transport) to verify
the actual seismology logic works, before bothering with the MCP Inspector.
"""
import sys
import tempfile
import os

sys.path.insert(0, os.path.expanduser("~/src/seismo-mcp/packages/obspy-mcp/src"))

from obspy_mcp import server as S


def main():
    tmp = tempfile.mkdtemp(prefix="obspy_mcp_test_")
    print(f"workdir: {tmp}\n")

    # 0) diagnose
    print("== diagnose_environment ==")
    print(S.diagnose_environment())

    # Make a synthetic SAC file: 5 Hz sine + noise, 100 Hz sampling, 60 s.
    import numpy as np
    from obspy import Trace, Stream, UTCDateTime
    fs = 100.0
    n = int(fs * 60)
    t = np.arange(n) / fs
    data = np.sin(2 * np.pi * 5 * t) + 0.3 * np.random.randn(n)
    tr = Trace(data=data.astype(np.float32),
               header={"station": "TEST", "channel": "BHZ",
                       "sampling_rate": fs, "starttime": UTCDateTime("2024-01-01T00:00:00")})
    sac = os.path.join(tmp, "test.sac")
    Stream(traces=[tr]).write(sac, format="SAC")
    print(f"\nwrote synthetic SAC: {sac}\n")

    # 1) read
    print("== read_waveform ==")
    print(S.read_waveform(sac))

    # 2) preprocess
    proc = os.path.join(tmp, "test_proc.sac")
    print("\n== preprocess ==")
    print(S.preprocess(sac, proc))

    # 3) filter
    filt = os.path.join(tmp, "test_filt.sac")
    print("\n== filter_waveform (bandpass 2-10 Hz) ==")
    print(S.filter_waveform(proc, filt, filter_type="bandpass", freqmin=2.0, freqmax=10.0))

    # 4) convert to mseed
    mseed = os.path.join(tmp, "test.mseed")
    print("\n== convert_format SAC -> MSEED ==")
    print(S.convert_format(filt, mseed, "MSEED"))
    assert os.path.exists(mseed)

    # 5) plot
    plot_path = os.path.join(tmp, "plot.png")
    print("\n== plot_waveform ==")
    result = S.plot_waveform(filt, plot_path)
    print(f"returned type: {type(result).__name__}")
    if isinstance(result, str):
        assert os.path.exists(result), f"plot file missing: {result}"
        print(f"plot written to: {result} ({os.path.getsize(result)} bytes)")
    else:
        print(f"inline image, data size: {len(result.data)} bytes")

    # 6) resample
    rs = os.path.join(tmp, "test_50hz.sac")
    print("\n== resample 100 -> 50 Hz ==")
    print(S.resample(filt, rs, 50.0))

    print("\nALL TOOLS PASSED ✅")


if __name__ == "__main__":
    main()
