# Stage 1 — Zero-Cost Dependency Ledger

**Verification date:** 2026-11-17  
**Canonical source:** V18.2  
**Scope:** Stage 1 C++ L1/L2/L3 vertical slice

## Repository and compute

| Component | Observed configuration | Cost evidence | Control |
|---|---|---|---|
| GitHub repository | `hamedbenapart69-byte/Trade`, visibility `public` | Public visibility confirmed through the repository API | No private/larger runner |
| Actions runner | `ubuntu-24.04` standard GitHub-hosted runner | GitHub documents standard runners in public repositories as free and unlimited | Do not use larger runners |
| Build toolchain | CMake, GCC, libcurl, nlohmann-json, OpenSSL from Ubuntu packages | Open-source packages; no commercial license or subscription configured | Installed at runtime; no paid package registry |
| Schema validator | `ajv-cli@5.0.0` via npm | Open-source package; no paid API or subscription | Validation only; no hosted service |
| Artifact retention | One day; full L1 only for one-symbol validation; scheduled multi-symbol runs upload compact evidence | Limits sustained artifact accumulation | See storage caveat below |

Official GitHub billing references:
- https://docs.github.com/en/billing/concepts/product-billing/github-actions
- https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax

**Storage caveat:** GitHub's public-runner compute is free, but artifact storage is governed by account-level allowances and can incur charges above the included amount. The repository API does not expose the account's billing plan or current storage usage. The current workflow has no `upload-artifact` steps. L2, provider-health, Fear & Greed, signals, history, performance, coverage, system-status and run-manifest evidence is committed to the public `signals` branch on non-PR runs; the large raw L1 JSON is validated and hashed on the runner, then discarded. One historical validation artifact from an earlier workflow revision remains under its original 30-day retention policy. The account's plan, shared Actions/Packages storage usage and billing guard remain **UNVERIFIED**.

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
- Alternative.me API documentation: https://alternative.me/crypto/api/

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
- One historical compressed evidence artifact from the earlier workflow revision: 866,358 bytes, originally retained for 30 days. Current workflow uploads no new Actions artifacts.
- Four artifact hashes matched independently when recalculated from the uploaded ZIP.

## S1-12 assessment

**PARTIAL — public standard-runner compute is verified free; full account billing state is not.** GitHub's official billing documentation confirms standard GitHub-hosted runners in public repositories remain free. The current workflow disables all Actions artifact uploads, avoiding new artifact-storage accrual. However, one historical artifact remains retained under its earlier policy, and the account's plan, shared Actions/Packages storage usage and billing guard are not exposed by the repository API. Therefore S1-12 remains PARTIAL until the owner verifies the account-level billing settings and existing storage. No paid provider, larger runner, exchange account, private trading key, paid broadcast, email service, or dashboard is part of this stage.
