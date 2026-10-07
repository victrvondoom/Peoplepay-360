# Bring your own key

**AI & Models → Connect a provider.** Choose a provider, name the connection, enter the fields its manifest asks for, acknowledge the provider-terms
notice, then *Connect and test*. A connection can be tested, refreshed, disabled and removed. You can hold several (personal, company gateway, AWS production…)
and alias models (“Company Claude”) or pin a route.

## Where credentials live

| Source | Storage | Visible to |
|---|---|---|
| Environment variables (`.env.example`) | process memory only, as `system` connections | all users of that deployment (read-only) |
| User BYOK, with `PEOPLEPAY_MODELS_VAULT_KEY` | `EncryptedSqliteVault`: AES-256-GCM, the owner scope and reference are authenticated data | that user only |
| User BYOK, no vault key | process memory only (lost on restart); the UI says so | that user only |

The vault **fails closed**: no key or no `cryptography` package ⇒ nothing is written in plaintext. A ciphertext copied to another owner's row fails authentication.
Secrets are write-only: no API returns them (responses carry `has_credential: true`), forms clear password fields after submit, errors and logs pass through
`errors.redact` (Authorization/Bearer, `sk-…`, `nvapi-…`, AWS key ids, `api_key=`/token query parameters, and the known secret values). Tests assert that a key
never appears in any API response nor in the model or vault database files.

Generate a vault key with `python -m peoplepay_models.vault`. Rotating the key requires re-entering credentials (no key-rotation tool yet — a known gap).
Export contains preferences only; exporting credentials is intentionally unsupported.
Before you connect: requests are processed under the provider's terms; PeoplePay makes no legal guarantee about them.
