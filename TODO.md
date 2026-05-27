# Cleanup Backlog

Practical refactors to strip legacy branches, rely on the static `nectarapi/openapi.py` map (no bundled JSON specs), and make the codebase type-checkable without changing behavior.

## Models and typing

- Replace `dict` inheritance for `Amount`, `Asset`, `Price`, `BlockchainObject`, and list-like helpers (VotesObject/WitnessesObject) with thin data classes/wrappers; align equality/contains/update semantics to satisfy the type checker and remove LSP violations.
- Tame `asciichart` number handling by rejecting `None` min/max upfront or defaulting them before float math.

## Wallet and storage

- Finish unifying key/token store interfaces (`nectarstorage/interfaces.py` and backends): make `add/delete/getPrivateKeyForPublicKey` signatures match the interfaces, drop dict inheritance, and share encryption/decryption helpers. Introduce a keystore protocol for wallet/transactionbuilder use.

## Tests and docs

- Update docs/examples to describe the single RPC path, static OpenAPI map, and shared-instance/transport lifecycle; prune any references to shipping JSON specs.

## API Refactoring

- Refactor `Account.get_blog` to use `bridge.get_account_posts` (Bridge API) instead of `condenser_api.get_blog`. This aligns with `Discussions_by_blog` but requires changing pagination from index-based (`entry_id`) to cursor-based (`start_author`/`start_permlink`).
