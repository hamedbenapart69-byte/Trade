# Cloudflare Pages — Stage 1 deployment

The dashboard is a static site in `web/`. It does not need a server, database, framework build, exchange account, or trading key.

## One-time deployment (10 steps)

1. Sign in to Cloudflare and confirm the Free plan.
2. Open **Workers & Pages**.
3. Choose **Create application**.
4. Select **Pages**.
5. Select **Connect to Git**.
6. Authorize GitHub and choose `hamedbenapart69-byte/Trade`.
7. Select branch `stage-1-data-layer-v1` for the preview deployment.
8. Choose **None** as framework preset; leave the build command empty.
9. Set the build output directory to `web` (repository root remains `/`).
10. Save and deploy. Open the generated `*.pages.dev` URL and check that the dashboard shows a timestamp, provider, 100 symbols and the current C10 status counts.

## Important checks

- Do not add API keys, Telegram tokens or exchange credentials to Pages environment variables. The site only reads public JSON/CSV.
- The pipeline publishes `web/data/signals.json` and `web/data/history.csv`; a Git-connected Pages project redeploys after these files change on the selected branch.
- Add the deployed URL as GitHub repository variable `DASHBOARD_URL` if Telegram messages should include it.
- Test the URL from the network/device where it will be used. A successful Cloudflare deployment does not prove reachability from every Iranian ISP.
- If Cloudflare account creation or Pages access is blocked, do not claim a live URL. Keep the GitHub Pages build as a preview artifact only until an accessible free static host is verified.
