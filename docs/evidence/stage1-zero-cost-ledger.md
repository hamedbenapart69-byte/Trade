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

**Storage caveat:** GitHub's public-runner compute is free, but artifact storage is governed by account-level allowances and can incur charges above the included amount. The repository API does not expose the account's billing plan or current storage usage. The workflow therefore uses one-day retention and omits the large raw L1 JSON artifact from scheduled multi-symbol uploads. It still validates and hashes the full L1 file before the runner discards it. The account's exact storage quota remains **UNVERIFIED**.

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
- Compressed full evidence artifact for that one-symbol run: 866,358 bytes, retained for 30 days under the earlier workflow revision. Future workflow revisions cap retention at one day.
- Four artifact hashes matched independently when recalculated from the uploaded ZIP.

## S1-12 assessment

**PASS with explicit storage caveat.** All compute and API components used in the tested vertical slice are public/free or open-source, and the repository is public. Public standard GitHub-hosted runners are free. Artifact storage is controlled through one-day retention and compact scheduled uploads, but the account's exact artifact-storage allowance is not exposed by the repository API and remains UNVERIFIED. No paid provider, larger runner, exchange account, private trading key, paid broadcast, email service, or dashboard is part of this stage.
