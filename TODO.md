# Cleanup Backlog

Practical refactors to strip legacy branches, rely on the static `nectarapi/openapi.py` map, and make the codebase type-checkable without changing behavior.

## Models and typing

- Replace `dict` inheritance for `Amount`, `Asset`, `Price`, `BlockchainObject`, and list-like helpers (VotesObject/WitnessesObject) with thin data classes/wrappers; align equality/contains/update semantics to satisfy the type checker and remove LSP violations.
- Tame `asciichart` number handling by rejecting `None` min/max upfront or defaulting them before float math.
- Resolve typing diagnostics across the codebase (600+ pyright/ty checks) to establish robust type safety.

## API & Network Refactoring

- Refactor `Account.get_blog` to use `bridge.get_account_posts` (Bridge API) instead of `condenser_api.get_blog`. This aligns with `Discussions_by_blog` but requires changing pagination from index-based (`entry_id`) to cursor-based (`start_author`/`start_permlink`).
- Introduce an asynchronous version of the RPC client (`nectarapi`) using `httpx` or `aiohttp` to support concurrent operations.
- Move node health checks and latency evaluations to non-blocking background routines so node failovers don't block request threads.

## Testing & Quality

- Expand integration tests with VCR-backed network mocks (`pytest-recording`/`vcrpy`) to validate complex operations like `get_discussions_by_x`, votes, and custom JSON posts.
