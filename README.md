# Kalpha — project website

A single-page site for **Kalpha**, a curated, queryable census of iron-abundance
(A_Fe) and black-hole spin measurements from the RELXILL-family X-ray reflection
literature. The centerpiece is a live interactive histogram of the XRB vs AGN
iron-abundance distribution, generated from the Kalpha database.

Built by Javier García (NASA GSFC · Caltech) and Juan González.

## What's in here

| File | Role |
|------|------|
| `index.html` | The whole website (HTML/CSS/JS inline; Chart.js + Google Fonts via CDN). Embeds the interactive histogram and reads `afe_data.json`. |
| `afe_data.json` | Current snapshot of the binned A_Fe data + per-sample statistics that powers the plot. |
| `kalpha_afe.py` | Refreshes `afe_data.json` from the Kalpha MCP server. Optional local viewer (`--serve`) and figure export (`--png`). |
| `.github/workflows/refresh.yml` | Optional scheduled job that re-runs the refresh and commits new data. |

The page has an embedded fallback copy of the data, so it renders correctly even
before any refresh or when opened as a local file.

## Deploy it on GitHub Pages

```bash
# 1. create the repo on github.com (e.g. named "kalpha-site"), then locally:
cd kalpha-site
git init
git add .
git commit -m "Kalpha project site"
git branch -M main
git remote add origin https://github.com/USERNAME/kalpha-site.git
git push -u origin main
```

Then on GitHub: **Settings → Pages → Build and deployment → Deploy from a branch →
`main` / root**. The site appears at `https://USERNAME.github.io/kalpha-site/`
within a minute or two.

**One edit before pushing:** open `index.html`, find `const REPO_URL=` near the
bottom, and replace `USERNAME` with your GitHub username so the "GitHub" links
point at your repo. (You can also set a custom domain in the Pages settings.)

## Refresh the data

```bash
pip install "mcp>=1.0"
python kalpha_afe.py            # rewrite afe_data.json from the live database
python kalpha_afe.py --serve    # refresh + open the live plot locally
python kalpha_afe.py --png      # refresh + export afe_distribution.pdf / .png
```

Commit the updated `afe_data.json` to refresh the public site. To keep it current
automatically, the included GitHub Action runs weekly — enable Actions on the repo
(and add a `KALPHA_TOKEN` secret if the server requires auth; the workflow shows
where it plugs in).

## Notes

- The plot's statistics (median, mean ± σ, IQR, n) recompute exactly for each
  toggle state — they are real per-sample values from the database, not binned
  estimates.
- The MCP endpoint is not callable directly from a browser (session handshake +
  CORS), which is why the data is baked into `afe_data.json` and served as a
  static file. The Python script is the bridge.
