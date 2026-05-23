# 🍯 Nectar

**The modern Python library for the Hive blockchain. Built for 2025 and beyond.**

`beem` built the foundation of Python development on Hive — but it carries a decade of legacy: unmaintained cryptography, filesystem assumptions that break in containers, and a sprawling API surface held together by history. Nectar is its opinionated spiritual successor, rebuilt from the ground up for security, resilience, and the environments developers actually deploy to today.

If you are using `beem`, Nectar is where you go next.

---

[![PyPI version](https://img.shields.io/pypi/v/hive-nectar.svg)](https://pypi.python.org/pypi/hive-nectar/)
[![Python Versions](https://img.shields.io/pypi/pyversions/hive-nectar.svg)](https://pypi.python.org/pypi/hive-nectar/)
[![License](https://img.shields.io/github/license/thecrazygm/hive-nectar.svg)](LICENSE.txt)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/TheCrazyGM/hive-nectar)

---

## Why Nectar?

Three problems that break `beem` in modern deployments — and how Nectar solves them.

### 🔒 Cryptography You Can Trust

Nectar strips out `python-ecdsa`, `pycryptodomex`, and `scrypt` entirely — unmaintained libraries that represent real supply-chain risk in production systems. In their place:

- **[Coincurve](https://github.com/ofek/coincurve)**: A Python binding to the battle-tested C library `libsecp256k1` — the same one used by Bitcoin Core — for fast, audited signature generation, verification, and BIP32 HD key derivation.
- **[cryptography](https://cryptography.io/)**: Python's industry-standard library for AES encryption, password hashing, and DER serialization.

No legacy dependencies. No known vulnerable paths. Just modern, auditable cryptography.

### 🐳 Runs Anywhere — Including Read-Only Containers

Standard blockchain libraries assume they can write to the host filesystem. In unprivileged Docker pods, Kubernetes clusters, or any read-only environment, that assumption causes silent failures or crashes at startup.

Nectar solves this with a **transparent in-memory fallback**: if the library cannot write to disk to create or update its local wallet, it automatically switches to an in-memory SQLite shared-cache database. No configuration. No storage mounts. No workarounds.

Deploy to any environment and it just works.

### 🔌 A Clean, Consolidated RPC Surface

Nectar removes the condenser API legacy wrappers and local JSON specs that accumulated in `beem` over the years. What replaces them:

- **Single Unified Path**: Every JSON-RPC call uses the direct `api.method` shape, backed by a clean static OpenAPI mapping.
- **Shared Pooled Transport**: Built on `httpx2` with connection pooling, keep-alive, and automatic retry/backoff — resilient by default, not by configuration.

---

## 🚀 Quick Start

Requires Python >= 3.10.

```bash
pip install hive-nectar
```

### Read account data

```python
from nectar import Hive
from nectar.account import Account

hive = Hive()

account = Account("thecrazygm", blockchain_instance=hive)
print(f"Account:      {account.name}")
print(f"HIVE Balance: {account.balances['HIVE']}")
print(f"HBD Balance:  {account.balances['HBD']}")
```

### Sign and broadcast a transaction

```python
from nectar import Hive
from nectar.transactionbuilder import TransactionBuilder
from nectarbase.operations import Transfer

hive = Hive(keys=["your-active-private-key"])

tb = TransactionBuilder(blockchain_instance=hive)
tb.appendOps(Transfer(**{
    "from": "youraccount",
    "to": "recipientaccount",
    "amount": "1.000 HIVE",
    "memo": "Sent with Nectar"
}))
tb.sign()
tb.broadcast()
```

### Deploy in a container — no config needed

```dockerfile
FROM python:3.12-slim
RUN pip install hive-nectar
# No volume mounts or permissions required.
# Nectar detects the read-only environment and uses in-memory storage automatically.
```

---

## 🛠️ System Prerequisites

On platforms where binary wheels for `coincurve` and `cryptography` are not precompiled, build tools are required to compile the C extensions.

### Debian / Ubuntu

```bash
sudo apt-get install build-essential libssl-dev python3-dev python3-pip libffi-dev libtool autoconf automake pkg-config
```

### Fedora / RHEL

```bash
sudo yum install gcc openssl-devel python-devel libffi-devel libtool autoconf automake pkgconfig
```

### macOS

```bash
brew install openssl libtool autoconf automake libffi pkg-config
export CFLAGS="-I$(brew --prefix openssl)/include $CFLAGS"
export LDFLAGS="-L$(brew --prefix openssl)/lib $LDFLAGS"
```

### Termux (Android)

```bash
pkg install clang openssl python libtool autoconf automake libffi
```

---

## 🔑 Ledger Hardware Wallet Support

For Ledger Nano S/X hardware wallet signing:

```bash
pip install ledgerblue
```

---

## 📜 Standing on Shoulders

Nectar is a modernized fork of [beem](https://github.com/holgern/beem), originally built by Holger Nahrstaedt, and incorporates [python-graphenelib](https://github.com/xeroc/python-graphenelib) by Fabian Schuh (`xeroc`). Their decade of work made this possible. Nectar exists to carry that work forward — not to replace the people behind it.

---

## 🌐 Built by SRBDE

Nectar is developed and maintained by the **Sustainable Resource and Business Development Enterprise (SRBDE)** — an open-source infrastructure organization building tools and platforms for communities that build things together.

We apply the logic of agricultural sustainability to software: the goal is always to return more to the ecosystem than we extract.

- **Open source is our value, not just our business model.**
- **Our commercial products fund our open-source core. The open work is the mission.**

### Explore the Ecosystem

| Project                                  | Description                |
| ---------------------------------------- | -------------------------- |
| [ecoinstats.net](https://ecoinstats.net) | SRBDE corporate hub        |
| [thecrazygm.com](https://thecrazygm.com) | Open gaming tools & TTRPGs |

---

## 🤝 Contributing

Audits, forks, and pull requests are welcome. Nectar is built to last for the decade, not the quarter. If you find a security issue, please open a private advisory rather than a public issue.
