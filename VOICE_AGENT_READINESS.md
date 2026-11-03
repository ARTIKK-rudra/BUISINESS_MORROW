# Restaurant Provision Voice Agent — Readiness

## Verified local workflow

The local, browser-based workflow is the active ₹0 implementation. It persists
tenant-scoped provision cases, conversation turns, manager recommendations,
supplier quotations, owner approvals, purchases, and audit entries. It does not
dial contacts, send supplier messages, or make Gemini requests when the optional
Gemini key is absent.

The shortage calculation assesses pending `pending`, `preparing`, and `ready`
orders. It expands configured recipes into ingredient demand, includes unreceived
`ordered` and `partially_received` purchase quantities, and reports affected
orders. A missing inventory record or incompatible recipe unit is reported as a
data-quality issue for manager review; quantities are never guessed.

## Current safeguards

- `VOICE_TEST_MODE=true`
- `VOICE_LIVE_CALLS_ENABLED=false`
- All registered contacts remain inactive for calling until their individual
  consent is explicitly recorded.
- Supplier contact authorization and final purchase authorization remain separate.
- Local demonstration mode never creates a purchase order.

## Exotel readiness

An Exotel Connect Voice AI adapter is present in
`backend/app/services/exotel_voice.py`. It is deliberately separate from the
automatic stock-alert worker and returns a simulated call identifier while test
mode is enabled. Its live path requires an explicit future integration point to
perform recipient-consent and owner-scope checks before it can be invoked.

No Exotel credentials, ExoPhone, public HTTPS/WSS endpoint, or configured
AgentStream endpoint were found in the local runtime when this document was
first created. A subsequent credentialed, read-only balance validation against
the configured Singapore endpoint returned HTTP 403. No call was attempted.
This does not establish whether the credentials are invalid, the account is
trial-restricted, the API is not enabled, or the account/region pairing is
incorrect; Exotel support/dashboard information is required to distinguish them.

Subsequent unauthenticated diagnostics reached `api.exotel.com` with both curl
and Python's standard `urllib` and received HTTP 400, while DNS and TLS 1.2
also succeeded. Therefore the historical `transport_error` is not a general
hostname, TLS, proxy, redirect, or base-HTTP connectivity failure. The previous
adapter discarded the underlying `URLError` reason, so its exact historic cause
cannot be recovered without a new credentialed request. The adapter now records
only the safe exception class (for example `URLError:ConnectionRefusedError`)
for future diagnostics, never the credential, URL query, or raw provider body.

For a future authorized live integration, Exotel documents Mumbai Connect Voice
AI at `https://api.in.exotel.com/v1/Accounts/{account_sid}/Calls/connect`, with
HTTP Basic API-key/token authentication, a configured ExoPhone caller ID, a public
`wss://` stream URL, and an HTTPS status callback. The provider account must first
confirm trial outbound eligibility and the required recipient consent.

The existing Twilio implementation remains preserved but disabled by the same
test-mode safeguards.

## Remaining human actions for real phone calls

1. Obtain and store Exotel API credentials and ExoPhone configuration in local
   secrets only.
2. Resolve the Exotel read-only API HTTP 403 in the Exotel dashboard/support,
   then confirm trial/KYC/regulatory eligibility for outbound Indian calls and
   AgentStream.
3. Obtain and record explicit calling consent from every recipient.
4. Provide a publicly reachable HTTPS/WSS endpoint and verify Exotel's documented
   callback/authentication mechanism with the provider.
5. Explicitly authorize one test call to a consented test recipient.
