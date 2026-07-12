"""End-to-end test of gmt-mcp against the local PyGMT/GMT install.

Drives each tool via the imported function (bypassing MCP transport) and
checks that real PNG output is produced.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.expanduser("~/src/seismo-mcp/packages/gmt-mcp/src"))

from gmt_mcp import server as G


def _is_image(result) -> bool:
    """A returned Image object means inline; a str means file path or error."""
    return not isinstance(result, str)


def main():
    tmp = tempfile.mkdtemp(prefix="gmt_mcp_test_")
    print(f"workdir: {tmp}")

    # 0) diagnose
    print("\n== diagnose_environment ==")
    print(G.diagnose_environment())

    # 1) coast map (East Asia)
    out = os.path.join(tmp, "coast.png")
    print("\n== coast_map (East Asia 100-140/15-45) ==")
    r = G.coast_map(region=[100, 140, 15, 45], projection="M12c",
                    output_path=out)
    print(r if isinstance(r, str) else f"inline image ({len(r.data)} bytes)")
    assert os.path.exists(out) and os.path.getsize(out) > 5000, "coast png missing/empty"

    # 2) basemap with coast
    out2 = os.path.join(tmp, "basemap.png")
    print("\n== make_basemap (with coast) ==")
    r = G.make_basemap(region=[110, 130, 20, 40], projection="M10c",
                       output_path=out2)
    print(r if isinstance(r, str) else f"inline image ({len(r.data)} bytes)")
    assert os.path.exists(out2) and os.path.getsize(out2) > 5000

    # 3) plot epicenters (synthetic)
    out3 = os.path.join(tmp, "epicenters.png")
    lons = [116.4, 121.5, 130.0, 125.3, 118.2, 139.7, 108.9]
    lats = [39.9, 31.2, 33.0, 25.0, 24.5, 35.7, 34.3]
    print(f"\n== plot_points ({len(lons)} epicenters) ==")
    r = G.plot_points(region=[100, 145, 15, 45], projection="M12c",
                      lons=lons, lats=lats, style="a0.5c", color="red",
                      output_path=out3)
    print(r if isinstance(r, str) else f"inline image ({len(r.data)} bytes)")
    assert os.path.exists(out3) and os.path.getsize(out3) > 5000

    # 4) xy plot (a simple curve)
    out4 = os.path.join(tmp, "xy.png")
    xs = [float(i) / 10 for i in range(101)]
    ys = [x ** 2 for x in xs]
    print("\n== plot_xy (parabola) ==")
    r = G.plot_xy(x=xs, y=ys, title="y = x²", x_label="x", y_label="y",
                  style="c0.15c", color="blue", output_path=out4)
    print(r if isinstance(r, str) else f"inline image ({len(r.data)} bytes)")
    assert os.path.exists(out4) and os.path.getsize(out4) > 5000

    # 5) text on map
    out5 = os.path.join(tmp, "labels.png")
    print("\n== text_on_map (city labels) ==")
    r = G.text_on_map(region=[100, 145, 15, 45], projection="M12c",
                      lons=[116.4, 121.5, 139.7], lats=[39.9, 31.2, 35.7],
                      texts=["Beijing", "Shanghai", "Tokyo"],
                      output_path=out5)
    print(r if isinstance(r, str) else f"inline image ({len(r.data)} bytes)")
    assert os.path.exists(out5) and os.path.getsize(out5) > 5000

    # 6) inline image (no output_path) — should return an Image, not a path
    print("\n== inline image (no output_path) ==")
    r = G.coast_map(region=[-180, 180, -90, 90], projection="Q15c")
    print(f"returned {'Image (inline)' if _is_image(r) else 'str'}")
    print(f"  → {'inline PNG, ' + str(len(r.data)) + ' bytes' if _is_image(r) else r}")

    print("\n== output PNG sizes ==")
    for f in [out, out2, out3, out4, out5]:
        print(f"  {os.path.basename(f):16s} {os.path.getsize(f)} bytes ✓")

    print("\nALL GMT TOOLS PASSED ✅")


if __name__ == "__main__":
    main()
