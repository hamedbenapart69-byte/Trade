# Provider Eligibility and Data Federation Policy — V21.1

## 1. Two independent questions

A provider adapter is production-eligible only when both questions are answered:

1. **Technical reachability:** can the GitHub Actions backend retrieve the required endpoint reliably, parse it, validate freshness and map asset identities?
2. **Contractual eligibility:** do the provider's published API terms, account eligibility, data license, automation rights, attribution requirements and intended-use restrictions permit this system to use the data?

HTTP 200 answers only part of question 1. It does not answer question 2.

## 2. Do not confuse website access with provider eligibility

- If the owner cannot open a provider's website from a personal device but the provider's terms permit the intended use, test the backend from GitHub Actions. Personal-device reachability is not a rejection criterion.
- If published provider terms exclude the account context or prohibit the intended automated use, disable the adapter even if GitHub Actions receives HTTP 200.
- Do not infer contractual eligibility from HTTP status, IP reachability, a successful parse, or the absence of an error page.
- Do not store the owner's location or account eligibility details in public source files, workflow logs or artifacts.

## 3. V21.1 quorum

Production market-wide references require at least two independent, fresh, license-eligible providers with overlapping asset identity coverage. A provider is counted only after terms/account eligibility review, successful backend request and schema validation, freshness verification, canonical asset identity matching, explicit provenance and attribution, and failure-mode tests.

One live provider is discovery evidence only. It cannot satisfy provider quorum.

## 4. Current adapter disposition

The machine-readable authority is config/provider-policy.v1.json; do not duplicate secrets or personal context here.

- **CoinPaprika:** one currently qualified market-wide provider; personal-use and endpoint limits remain enforced.
- **CoinRanking:** candidate second provider; free authenticated key is not configured in the repository runtime. No request is made without the key.
- **CoinMarketCap:** candidate alternative; authenticated key and account eligibility are not configured/verified. Keyless 429 observations are not treated as valid market data.
- **CoinGecko:** disabled under its published API terms for the applicable excluded account context. This is a contractual decision, not a network-access decision. No adapter request should be sent.
- **CoinCap:** not production-qualified under the current policy.
- **CoinLore:** not production-qualified for automated polling under the current policy.

The exact provider URLs and review evidence remain in config/provider-policy.v1.json.

## 5. Fail-closed behavior

If fewer than two providers qualify, if overlapping identity coverage is incomplete, or if any provider's terms are unresolved, set the federation state to degraded/partial, preserve raw source status and timestamps, do not synthesize a second source from another endpoint belonging to the same provider, do not promote candidate data to a frozen production universe, and do not emit actionable signals from the blocked L1 state.

This policy supplements V21.0 and implements the V21.1 provider-independence requirement. It does not relax any statistical, risk, cost, zero-cost or manual-trading constraint.
