#!/usr/bin/env python3
"""
kalpha_afe.py
=============
Pull the current XRB vs AGN iron-abundance (A_Fe) distribution from the Kalpha
MCP server and write `afe_data.json`, which powers the interactive web plot in
`index.html`. The plot's stat cards (median, mean ± sigma, IQR, n) recompute as
the limit/pegged and fixed toggles change, so this script fetches the exact
statistics for each of the four toggle states from the database (no binned
estimation) and writes them under classes.<cls>.stats.

Per class, four queries define the four samples / toggle states:
    free        limit OFF, fixed OFF  -> only_free, include_limits=False
    free_limit  limit ON,  fixed OFF  -> only_free, include_limits=True   (default)
    free_fixed  limit OFF, fixed ON   -> include_fixed, include_limits=False
    all         limit ON,  fixed ON   -> include_fixed, include_limits=True

The per-bin stacked segments are derived by nested difference (always >= 0):
    free  = count(free)
    limit = count(free_limit) - count(free)
    fixed = count(all)        - count(free_limit)

Install:  pip install "mcp>=1.0"        (and matplotlib for --png)
Run:      python kalpha_afe.py [--serve] [--png] [--header "Authorization: Bearer X"]
"""

import argparse
import asyncio
import datetime as dt
import json
import os
import sys

DEFAULT_URL = "https://kalpha-production.up.railway.app/mcp"
BINNING = {"bin_width": 0.5, "bin_min": 0.5, "bin_max": 10.5,
           "plot_type": "histogram", "aggregation": "per_fit"}

# (sample key, tool args) for the four toggle states.
SAMPLES = {
    "free":       dict(only_free=True,  include_fixed=False, include_limits=False),
    "free_limit": dict(only_free=True,  include_fixed=False, include_limits=True),
    "free_fixed": dict(only_free=False, include_fixed=True,  include_limits=False),
    "all":        dict(only_free=False, include_fixed=True,  include_limits=True),
}


def _payload(result):
    sc = getattr(result, "structuredContent", None)
    if isinstance(sc, dict) and "bins" in sc:
        return sc
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            try:
                p = json.loads(text)
                if "bins" in p:
                    return p
            except (ValueError, TypeError):
                continue
    raise RuntimeError("Could not find histogram JSON in the tool response.")


def _stat(p):
    m = p["metadata"]
    return {k: (int(m["n_values"]) if k == "n" else round(float(m[src]), 3))
            for k, src in (("n", "n_values"), ("median", "median"), ("mean", "mean"),
                           ("std", "std"), ("q1", "q1"), ("q3", "q3"))}


def _counts(p):
    return {round(float(b["left_edge"]), 3): int(b["count"]) for b in p["bins"]}


def _bins(free_p, free_limit_p, all_p):
    cf, cfl, ca = _counts(free_p), _counts(free_limit_p), _counts(all_p)
    edges = sorted(ca)
    bins, n_lim, n_fix = [], 0, 0
    for e in edges:
        free = cf.get(e, 0)
        limit = max(0, cfl.get(e, 0) - free)
        fixed = max(0, ca.get(e, 0) - cfl.get(e, 0))
        bins.append([e, free, limit, fixed])
        n_lim += limit
        n_fix += fixed
    return bins, n_lim, n_fix


async def fetch(url, extra_headers):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    classes = {}
    async with streamablehttp_client(url, headers=extra_headers or None) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for key, cls in (("xrb", "XRB"), ("agn", "AGN")):
                payloads = {}
                for skey, sargs in SAMPLES.items():
                    res = await session.call_tool("generate_iron_histogram",
                                                  dict(BINNING, class_filter=cls, **sargs))
                    payloads[skey] = _payload(res)
                stats = {k: _stat(p) for k, p in payloads.items()}
                bins, n_lim, n_fix = _bins(payloads["free"], payloads["free_limit"], payloads["all"])
                classes[key] = {"n_limit": n_lim, "n_fixed": n_fix, "stats": stats, "bins": bins}
    return classes


def render_png(classes, stem):
    """Static figure (PNG + PDF), all three segments, amber/sky scheme."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    XC, AC = "#f59e0b", "#0ea5e9"
    edges = [b[0] for b in classes["xrb"]["bins"]]
    x = list(range(len(edges)))
    w = 0.4

    def parts(cls):
        bb = classes[cls]["bins"]
        return [b[1] for b in bb], [b[2] for b in bb], [b[3] for b in bb]

    def stack(ax, xs, free, limit, fixed, c):
        ax.bar(xs, free, width=w, color=c)
        base = list(free)
        ax.bar(xs, limit, width=w, bottom=base, color=c, alpha=0.38, edgecolor=c, linewidth=0.6)
        base = [a + b for a, b in zip(base, limit)]
        ax.bar(xs, fixed, width=w, bottom=base, color=c, alpha=0.16, edgecolor=c, linewidth=0.6, linestyle=":")

    xf, xl, xx = parts("xrb")
    af, al, ax2 = parts("agn")
    fig, ax = plt.subplots(figsize=(9.5, 5.2), dpi=200)
    stack(ax, [i - w / 2 for i in x], xf, xl, xx, XC)
    stack(ax, [i + w / 2 for i in x], af, al, ax2, AC)

    leg = [Patch(facecolor=XC, label="XRB free"),
           Patch(facecolor=XC, alpha=0.38, edgecolor=XC, label="XRB limit"),
           Patch(facecolor=XC, alpha=0.16, edgecolor=XC, linestyle=":", label="XRB fixed"),
           Patch(facecolor=AC, label="AGN free"),
           Patch(facecolor=AC, alpha=0.38, edgecolor=AC, label="AGN limit"),
           Patch(facecolor=AC, alpha=0.16, edgecolor=AC, linestyle=":", label="AGN fixed")]
    ax.legend(handles=leg, frameon=False, fontsize=8, ncol=2)
    tick_pos = [i for i in x if abs((0.5 + 0.5 * i) - round(0.5 + 0.5 * i)) < 1e-9]
    ax.set_xticks(tick_pos)
    ax.set_xticklabels([f"{0.5 + 0.5 * i:.0f}" for i in tick_pos])
    ax.set_xlabel(r"Iron abundance $A_{\mathrm{Fe}}$ ($\times$ solar)")
    ax.set_ylabel("Fit count")
    ax.set_title(r"Iron abundance — X-ray binaries vs AGN  (Kalpha)")
    ax.grid(axis="y", alpha=0.15)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(f"{stem}.{ext}", bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {stem}.png and {stem}.pdf")


def serve(directory, port=8000):
    import http.server, socketserver, threading, webbrowser
    os.chdir(directory)
    with socketserver.TCPServer(("", port), http.server.SimpleHTTPRequestHandler) as httpd:
        url = f"http://localhost:{port}/index.html"
        print(f"  serving {directory} at {url}  (Ctrl-C to stop)")
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  stopped.")


def main():
    p = argparse.ArgumentParser(description="Refresh Kalpha A_Fe data for the web plot.")
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--out", default="afe_data.json")
    p.add_argument("--header", action="append", default=[],
                   help='extra HTTP header, e.g. --header "Authorization: Bearer XYZ"')
    p.add_argument("--serve", action="store_true")
    p.add_argument("--png", action="store_true")
    p.add_argument("--port", type=int, default=8000)
    a = p.parse_args()

    headers = {}
    for h in a.header:
        if ":" in h:
            k, v = h.split(":", 1)
            headers[k.strip()] = v.strip()

    print(f"Fetching from {a.url} ...")
    try:
        classes = asyncio.run(fetch(a.url, headers))
    except ModuleNotFoundError:
        sys.exit('Missing dependency. Run:  pip install "mcp>=1.0"')
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Fetch failed: {e}\n"
                 f"If the server needs auth, pass --header \"Authorization: Bearer <token>\".")

    out = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "source": "Kalpha MCP — generate_iron_histogram",
        "filters": {**{k: BINNING[k] for k in ("bin_width", "bin_min", "bin_max")},
                    "note": "bins via nested differences; stats[*] exact per-sample"},
        "classes": classes,
    }
    with open(a.out, "w") as f:
        json.dump(out, f, indent=2)
    sx, sa = classes["xrb"]["stats"], classes["agn"]["stats"]
    print(f"  wrote {a.out}")
    print(f"    XRB n: free={sx['free']['n']} free+lim={sx['free_limit']['n']} "
          f"free+fix={sx['free_fixed']['n']} all={sx['all']['n']}")
    print(f"    AGN n: free={sa['free']['n']} free+lim={sa['free_limit']['n']} "
          f"free+fix={sa['free_fixed']['n']} all={sa['all']['n']}")

    if a.png:
        render_png(classes, "afe_distribution")
    if a.serve:
        serve(os.path.dirname(os.path.abspath(a.out)) or ".", a.port)


if __name__ == "__main__":
    main()
