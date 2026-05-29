Changelog
=========

1.0.1 - 2026-05-29
------------------

Maintenance
~~~~~~~~~~~

- **Tests**: Modernized the test suite structure. Rewrote utility tests (``test_utils.py``) to use ``pytest`` and pure unit test functions in ``tests/unit/test_utils.py``.
- **Test Isolation**: Moved fragile legacy integration tests to ``tests/legacy/`` and prefixed directories with ``legacy_`` to prevent Python path shadowing conflicts. Cleaned up the root ``tests/conftest.py`` and moved VCR/monkeypatching configuration into ``tests/legacy/conftest.py``.
- **Cryptography Tests**: Migrated and modernized the entire offline cryptography unit test suite (``test_aes.py``, ``test_base58.py``, ``test_bip32.py``, ``test_bip38.py``, ``test_ecdsa.py``, ``test_key_format.py``, ``test_tweak_add.py``, ``test_ec_basic.py``) into ``tests/unit/`` using standard pytest assertions, fixtures, and parameterizations.
- **API Contract & Shape Verification**: Added offline API contract signature checking (``test_api_signatures.py``) and mock JSON-RPC response shape verification (``test_api_shapes.py``) using static json payloads to protect the public API from future backward-compatibility breaks.
- **VCR**: Resolved connection pool leaks and deadlocks under VCR recording/playback by override patching default connection limits.

1.0.0 - 2026-05-22
------------------


Major Changes
~~~~~~~~~~~~~

- **Cryptography layer modernization**: Removed all legacy cryptography
  library dependencies (``ecdsa``, ``pycryptodomex``, ``scrypt``) and
  replaced them with standard ``cryptography`` and ``coincurve==20.0.0``
  for key derivation, signing, and encryption.
- **Docker/Kubernetes Support**: Implemented a transparent fallback to
  in-memory (RAM) SQLite database storage (using a shared cache URI) if
  writing to the local data directory or creating the database file
  fails (e.g., in unprivileged Docker containers or read-only
  filesystems).
- **HTTPX2**: With HTTPX itself seeing limited activity recently,
  Pydantic is picking up stewardship under the HTTPX2 name so that users
  have a reliably maintained path forward - including timely security
  updates for a library that sits in the critical path of so many
  production systems.

Maintenance
~~~~~~~~~~~

- **Docs**: Regenerate the Sphinx API reference from the ``src/`` layout
  so the documentation sidebar lists package modules instead of ``src``.
- **Tests**: Isolate pytest-xdist worker homes so wallet/config SQLite
  databases do not collide during parallel storage, password, key, and
  CLI tests.

.. _section-1:

0.2.15 - 2026-04-05
-------------------

- **Logging**: stop repeated log spam when retrying a failed network
  connection

.. _section-2:

0.2.14 - 2026-01-21
-------------------

- **Feature**: Updated node fetching to use both PeakD beacon and the
  new v4v beacon API.

.. _section-3:

0.2.13 - 2025-12-24
-------------------

- **Fix**: Serialize node configuration lists to JSON strings to fix
  ``sqlite3`` errors in Docker/fresh installs.

.. _section-4:

0.2.12 - 2025-12-23
-------------------

- **Feature**: Allow specifying a node list or offline mode in
  ``generate_config_store``.

.. _section-5:

0.2.11 - 2025-12-23
-------------------

- **Feature**: Implemented disk-based caching for beacon node list (5
  min TTL) to prevent API rate limits.
- **Feature**: Added separate MD5-based file caching for NectarEngine
  node lists (standard & history).

.. _section-6:

0.2.10 - 2025-12-23
-------------------

- **Refactor**: Only fetch default nodes if “node” key is missing in
  configuration.

.. _section-7:

0.2.9 - 2025-12-22
------------------

- **Refactor**: Deprecated ``hive_instance`` in favor of
  ``blockchain_instance`` across all classes with backward compatibility
  warnings.

0.2.3 through 0.2.8 - 2025-12-19
--------------------------------

- **Maintenance**: Various fixes and stability improvements during rapid
  iteration.

.. _section-8:

0.2.2 - 2025-12-16
------------------

Improvements
~~~~~~~~~~~~

- **HTTP Client**: Completed the migration to ``httpx`` by replacing all
  remaining ``requests`` and ``urllib`` usage in ``market.py``,
  ``haf.py``, and ``nodelist.py``.
- **Logging**: Reduced log verbosity by setting ``httpx`` and
  ``httpcore`` loggers to ``WARNING`` level.

.. _section-9:

0.2.0 - 2025-12-01
------------------

Breaking Changes
~~~~~~~~~~~~~~~~

- **Refactor**: Removed ``use_stored_data`` parameter from
  ``_calc_resulting_vote`` call in ``hive.py``.
- **Refactor**: Converted ``Amount.tuple`` property to ``as_tuple()``
  method.
- **Refactor**: Converted API method calls from dict parameters to
  positional arguments across multiple modules.
- **Refactor**: Removed legacy ``HiveSigner`` integration and related
  dependencies.
- **Refactor**: Standardized API endpoint naming to use ``_api`` suffix
  throughout codebase.
- **Refactor**: Deprecated ``appbase`` utility functions.

.. _improvements-1:

Improvements
~~~~~~~~~~~~

- **HTTP Client**: Standardized HTTP/RPC communication by transitioning
  to ``httpx`` and implementing a single, shared client instance for
  improved efficiency and consistency.
- **Transaction**: Increased default transaction expiration from 30
  seconds to 300 seconds to better handle node clock skew and network
  latency.

Features
~~~~~~~~

- **Transaction**: Added ``json_str`` parameter to multiple transaction
  operations.
- **Node Management**: Simplified ``NodeList`` to use PeakD beacon API
  with static fallback nodes.
- **Performance**: Improved blockchain tests with limited data
  collection and structure validation.
- **Compatibility**: Removed Python 2 compatibility code and modernized
  syntax.
- **CLI**: Added string time parsing support to account history methods.

Fixes
~~~~~

- **Security**: Fixed ``PasswordKey`` seed generation and ``PublicKey``
  string methods.
- **Security**: Fixed cipher decoding in ``extract_memo_data``.
- **Reliability**: Improved type safety and null handling across almost
  all core modules (``Account``, ``BlockChainInstance``, ``Hive``,
  etc.).
- **Reliability**: Fixed circular import in instance module.
- **Reliability**: Improved RPC retry logic and error handling for
  witness and node operations.

.. _section-10:

0.1.5 - 2025-11-04
------------------

- **Feature**: Added a ``--witness/-w`` flag to the
  ``hive-nectar rewards`` CLI that aggregates producer rewards into a
  PrettyTable, respecting the requested date window.
- **Fix**: Resolved ``KeyError`` and zero-output issues in the rewards
  CLI by iterating over all relevant operations, normalizing producer
  reward timestamps, and gracefully handling curation entries missing
  ``comment_permlink`` data.
- **Tests**: Extended CLI coverage to ensure the new witness mode runs
  without errors.

0.1.4b - 2025-10-12
-------------------

- **Refactor**: Refactored **Account**\ ’s vote‑pct calculation to
  correctly convert the desired token value to an ``Amount``, introduce
  a safe ratio clamp (‑10 to 10) to avoid extreme values, and return 0
  for zero‑vote scenarios; updated all discussion query fallbacks to use
  the *condenser* API and handle dict‑style responses, and tweaked tests
  to instantiate ``Account`` directly.

0.1.4b - 2025-09-19
-------------------

- **Feature**: Added payout-based vote helpers on ``Comment`` :

  - ``Comment.to_zero(account, partial=100.0)`` computes the UI downvote
    percent to reduce a post’s pending payout to approximately zero
    (uses reward fund + median price + effective vesting shares; scales
    by the account’s downvoting power). Returns negative UI percent and
    broadcasts automatically (suppress via the blockchain instance’s
    ``no_broadcast``).
  - ``Comment.to_token_value(account, hbd, partial=100.0)`` computes the
    UI upvote percent to contribute approximately the given HBD value.
    Returns positive UI percent and broadcasts automatically (suppress
    via ``no_broadcast``).

- **Fix**: Corrected vote value math to align with the beem reference
  formula:

  - Restored ``get_hbd_per_rshares()`` to derive HBD/share as
    ``(reward_balance / recent_claims) * median_price(HBD/HIVE)`` .
  - Applied the missing ``/ 100`` scale factor from the sample when
    converting rshares to HBD-equivalent in payout-based helpers.
  - ``ActiveVotes.get_downvote_pct_to_zero()`` updated to use effective
    vesting shares and the account’s downvoting power; analytic path
    improved and payout-based path added via ``Comment.to_zero()`` .
  - ``vests_to_rshares()`` reverted to chain-accurate power computation
    via ``_calc_resulting_vote`` and dust-threshold handling.
  - ``rshares_to_vote_pct()`` updated to invert the chain power model
    consistently (taking max_vote_denom into account).

- **Docs/Examples**: Added ``examples/get_vote_pct_script.py`` showing
  how to compute both the downvote-to-zero percent and the upvote
  percent to reach a target HBD.

.. _section-11:

0.1.3 - 2025-09-18
------------------

- **Test**: Working on getting 100% test coverage
- **Feature**: Added some HAF features for things like reputation.

.. _section-12:

0.1.2 - 2025-09-17
------------------

- **Fix**: Replaced missing ``**kwargs`` in ``Blocks`` constructor.

.. _section-13:

0.1.1 - 2025-09-17
------------------

- **Fix**: Added support for ``only_ops`` and ``only_virtual_ops``
  parameters in ``Blocks`` constructor.

0.1.0b - 2025-09-17
-------------------

- **Breaking Change**: Killed everything that was not specifically HIVE
  related. If you used this for STEEM and / or Blurt, they are no longer
  supported.
- **Fix**: Corrected inverted fallback logic in chain detection to
  prefer HIVE over STEEM when ``blockchain_name`` is None.
- **Fix**: Restored backward compatibility for constructor parameters:

  - ``Vote.__init__``: Added support for deprecated ``steem_instance``
    and ``hive_instance`` kwargs with deprecation warnings.
  - ``ActiveVotes.__init__``: Added support for deprecated
    ``steem_instance`` and ``hive_instance`` kwargs with deprecation
    warnings.
  - ``Witness.__init__``: Added ``**kwargs`` with warnings for
    unexpected parameters.
  - ``Comment_options.__init__``: Added fallback support for deprecated
    ``percent_steem_dollars`` parameter.

- **Improvement**: Removed deprecated websocket support from
  GrapheneRPC, now only supports HTTP/requests for better reliability
  and maintainability.
- **Improvement**: Simplified ecdsasig.py to use only cryptography
  library, removing complex conditional logic for different secp256k1
  implementations. The ``tweak_add`` operation now raises
  NotImplementedError when called.
- **Major Feature**: Implemented pure Python secp256k1 elliptic curve
  operations for PublicKey.add() method, restoring compatibility with
  existing code that relies on key derivation. The implementation
  includes proper validation, error handling, and maintains the same API
  as before. All unit tests pass successfully.
- **Fix**: Fixed HiveSigner integration in TransactionBuilder:

  - Updated appendSigner() to restrict permissions to ‘posting’ when
    using HiveSigner
  - Fixed sign() method to properly call hivesigner.sign() and attach
    signatures instead of returning early
  - Fixed broadcast() method to use hivesigner.broadcast() when use_hs
    is True
  - Added proper error handling and fallbacks for non-HiveSigner flows
  - **Fix**: Fixed HiveSigner.broadcast() call in TransactionBuilder to
    pass operations list instead of full transaction JSON, and include
    username when available

- **Fix**: Fixed Claim_reward_balance operation serialization in
  nectarbase/operations.py:

  - Removed incorrect mutually-exclusive logic between reward_hive and
    reward_hbd
  - Updated to always serialize all four fields in canonical order:
    account, reward_hive, reward_hbd, reward_vests
  - Added proper zero-amount defaults (“0.000 HIVE”/“0.000 HBD”) for
    missing reward fields
  - Updated docstring to reflect correct behavior and field requirements

- **Fix**: Convert beneficiary weights from ``HIVE_100_PERCENT`` units
  (10000) to percentages in ``Comment.get_beneficiaries_pct()`` to
  ensure accurate outputs.
- **Fix**: Improve ECDSA signing to correctly handle prehashed messages
  and tighten signature canonicalization checks for better
  interoperability.
- **Refactor**: Reorder wallet lock verification to run after HiveSigner
  validation in ``TransactionBuilder``, preventing premature lock errors
  for HiveSigner flows.
- **Refactor**: Replace implicit stdin default with an explicit
  blockchain selection in the CLI argument parser to avoid ambiguous
  behavior.
- **Refactor**: Update default Hive node configuration to use HTTPS
  endpoints instead of WSS.
- **Feature**: Add a pure-Python fallback for public key derivation when
  the ``ecdsa`` library is unavailable, improving portability.

.. _section-14:

0.0.11 - 2025-07-25
-------------------

- Fixed handling of missing ``community`` field in comments
  (``Comment``) and improved ``weighted_score`` type check in node list
  ranking (``NodeList``).

.. _section-15:

0.0.10 - 2025-07-12
-------------------

- Emergency hotfix: lower-case the UTC timestamp suffix during permlink
  generation (in ``derive_permlink``) to resolve validation errors
  caused by the uppercase ``U``.

.. _section-16:

0.0.9 - 2025-07-12
------------------

- Refactored ``nodelist`` logic:

  - ``update_nodes`` now reads authoritative node metadata from
    ``nectarflower`` account ``json_metadata`` only.
  - Uses ``weighted_score`` directly for ranking and zeroes scores for
    nodes missing from the report.
  - Dynamically adds new nodes from the report and failing list,
    ensuring completeness.
  - Removed unused fall-back paths and cleaned up internal code.

.. _section-17:

0.0.8
-----

Added new documentation and type hints to community

.. _section-18:

0.0.7
-----

Removed all python2 legacy dependencies, drop python3 version
requirement to >=3.10

.. _section-19:

0.0.6
-----

Updated to more robust error reporting

.. _section-20:

0.0.5
-----

More community fixes, including the Community Title Property

.. _section-21:

0.0.4
-----

Small community fixes

.. _section-22:

0.0.3
-----

Working on bridge api

.. _section-23:

0.0.2
-----

Rebranded to Nectar

.. _section-24:

0.0.1
-----

- Initial release
- Beem stops and Nectar starts
