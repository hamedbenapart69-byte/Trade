# Stage 1 — Zero-Cost Dependency Ledger

**Verification date:** 2026-11-18  
**Canonical source:** V18.2  
**Scope:** Stage 1 C++ L1/L2/L3 vertical slice

## Repository and compute

| Component | Observed configuration | Cost evidence | Control |
|---|---|---|---|
| GitHub repository | `hamedbenapart69-byte/Trade`, visibility `public` | Public visibility confirmed through the repository API | No private/larger runner |
| Actions runner | `ubuntu-24.04` standard GitHub-hosted runner | GitHub documents standard runners in public repositories as free and unlimited | Do not use larger runners |
| Build toolchain | CMake, GCC, libcurl, nlohmann-json, OpenSSL from Ubuntu packages | Open-source packages; no commercial license or subscription configured | Installed at runtime; no paid package registry |
| Schema validator | `ajv-cli@5.0.0` via npm | Open-source package; no paid API or subscription | Validation only; no hosted service |
| Artifact retention | Current workflow has no Actions artifact uploads; compact evidence is committed to the public `signals` branch | No new Actions artifact storage is created by current workflow | Historical artifact 14352156550 was deleted and verified; zero artifacts remain for the Stage 1 run |

Official GitHub billing references:
- https://docs.github.com/en/billing/concepts/product-billing/github-actions
- https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax

**Storage caveat:** GitHub's public-runner compute is free, while Actions and Packages storage share the account-level allowance. The owner confirmed the account is GitHub Free. The sole known Stage 1 artifact (ID `14352156550`, 866,358 bytes) was deleted in workflow run `44246854270`; the API subsequently returned HTTP 404 and the original run's artifact list is empty. Current Stage 1 and quarantined legacy workflows contain no artifact uploads. L2, provider-health, Fear & Greed, signals, history, performance, coverage, system-status and run-manifest evidence is committed to the public `signals` branch; raw L1 JSON is validated and hashed on the runner, then discarded. The repository integration cannot expose unrelated repositories' Packages usage or the account-wide spending cap, so those remain outside project observability. No paid project dependency, billable runner, or paid feature is configured.

## Data providers

| Provider | Stage 1 role | Authentication/cost status | Fallback rule |
|---|---|---|---|
| OKX public REST | Primary futures market data | Live public endpoints returned real data without exchange account credentials or private API keys | Primary only |
| Bybit public REST | Candidate fallback probe | Endpoint returned HTTP 403 in the runner; no authenticated access attempted | Fallback UNAVAILABLE |
| Binance public REST | Candidate fallback probe | Endpoint returned HTTP 451 in the runner; no authenticated access attempted | Fallback UNAVAILABLE |
| KuCoin, MEXC, Bitget | Candidate fallback probes | Public endpoints reachable, but no equivalence-verified C++ adapter exists | Fallback UNAVAILABLE; no substitution |
| CoinGecko | Reference provider probe | Reference-only; not a futures contract fallback | Never substitute for futures OHLCV |
| Alternative.me Fear & Greed | Sentiment reference series | Public endpoint `https://api.alternative.me/fng/?limit=0`; no API key used. The official page publishes API usage rules and attribution requirements; it does not state a separate fee on the FNG page | Store as an independent reference series; label source and do not treat as exchange data |

Official provider references:
- OKX API documentation: https://www.okx.com/docs-v5/en/
- Alternative.me FNG API and attribution rules: https://alternative.me/crypto/fear-and-greed-index/
- Alternative.me API documentation and free-use terms: https://alternative.me/crypto/api/ (free use, including commercial projects, under published terms).

**FNG fee certainty:** Public access without a key was observed and the endpoint returned 730 historical observations. A distinct FNG-specific price statement was not found on its official page. Treat this as **public/no-key, fee not explicitly stated**, not as a contractual guarantee of perpetual free service. The source requires prominent attribution whenever the data is displayed; Stage 1 currently stores it in the data artifact and does not display it in Telegram.

## Delivery

| Component | Use | Cost status |
|---|---|---|
| Telegram Bot API | `sendMessage` and `getUpdates` | Telegram describes its Bot API as free; normal standard bot messaging is used |
| Paid Telegram broadcasts | Not used | `allow_paid_broadcast` is never set |
| Telegram secrets | `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` | Repository secrets only; never written into artifacts or logs |
| Email / SendGrid | Not used | Excluded |
| Cloudflare Pages / R2 | Not used by this Telegram-only stage | Excluded |

Official Telegram references:
- https://core.telegram.org/bots/api
- https://core.telegram.org/api

## Measured Stage 1 evidence

- One-symbol two-year L1 artifact: 17,532 completed hourly candles; 100% OHLCV coverage.
- Funding: 90 observations; 29.67 days.
- Open interest: 720 observations; 29.96 days.
- Fear & Greed: 730 observations.
- First complete push run: GitHub Actions run `44135013370`; Telegram returned HTTP 200 and message ID `39`.
- Second distinct complete push run: GitHub Actions run `44149930383`; Telegram returned HTTP 200 and message ID `40`; scan ID differs from the first run.
- Current workflow contains no `actions/upload-artifact` step. Eight persisted outputs were independently SHA-256 recomputed and matched their run manifest.
- Historical artifact 14352156550 (866,358 bytes) deleted and verified; the original run's artifact list is empty. Current workflow uploads no new Actions artifacts.
- Four artifact hashes matched independently when recalculated from the uploaded ZIP.

## S1-12 assessment

**PASS — project-attributable costs are within GitHub Free allowances and no paid service is configured.** The owner confirmed GitHub Free. Official GitHub documentation lists 500 MB shared Actions/Packages storage and confirms standard GitHub-hosted runners in public repositories are free. The only known Stage 1 artifact was deleted and its absence independently verified; current Stage 1 and quarantined legacy workflows upload no artifacts. The repository is public and uses `ubuntu-24.04` standard runners, not larger runners. Alternative.me's official API terms explicitly describe the API as free for commercial use, subject to its terms and attribution rules. Account-wide storage consumption in unrelated repositories/packages remains unobservable, but the project itself stores no Actions artifacts. No paid provider, larger runner, exchange account, private trading key, paid broadcast, email service, Railway deployment, or dashboard is part of this stage.
