# Legacy web dashboard — archived

This directory contains the historical V18.2 browser dashboard and Cloudflare Pages deployment notes.

Under the controlling V21.0/V21.1 architecture:

- Telegram is the exclusive user-facing delivery channel.
- No Cloudflare Pages deployment or browser dashboard is part of the production system.
- No email fallback or user-operated web interface is required.
- The C++ GitHub Actions pipeline is the production path; Python/browser assets here are retained for audit and historical compatibility only.

Do not deploy `web/` or `web/futures/` as a production signal interface. The historical signal JSON and CSV links below are not V21 production sources.

The folder remains in the repository only to preserve provenance.