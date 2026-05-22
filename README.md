# 🍯 Nectar

**A modern, secure, and resilient Python library for the Hive blockchain.**

Nectar is a high-performance, container-native Python client built for developers who demand security, speed, and reliability. It is a modernized, opinionated spiritual successor to `beem`, re-engineered from the ground up for the next decade of decentralized applications.

---

[![PyPI version](https://img.shields.io/pypi/v/hive-nectar.svg)](https://pypi.python.org/pypi/hive-nectar/)
[![Python Versions](https://img.shields.io/pypi/pyversions/hive-nectar.svg)](https://pypi.python.org/pypi/hive-nectar/)
[![License](https://img.shields.io/github/license/thecrazygm/hive-nectar.svg)](LICENSE.txt)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/TheCrazyGM/hive-nectar)

---

## ⚡ Key Pillars of Nectar

### 🔒 Audited & Modern Cryptography

We have completely stripped out obsolete, unmaintained, and vulnerable cryptography libraries. Nectar is powered exclusively by:

- **[Coincurve](https://github.com/ofek/coincurve)**: Leveraging the highly optimized C-based `libsecp256k1` library for blazingly fast signature generation, verification, and BIP32 hierarchical deterministic key derivation.
- **Standard Cryptography**: Using Python's industry-standard `cryptography` library for AES encryption/decryption, password hashing, and DER serialization.
- _No legacy `python-ecdsa`, `pycryptodomex`, or `scrypt` dependencies._

### 🐳 Container & Cloud Native

Standard blockchain libraries often fail in modern stateless or read-only containerized environments (like unprivileged Docker pods or Kubernetes clusters) due to file system permission constraints.

- Nectar resolves this with a **transparent in-memory fallback**. If the library cannot write to the host directory to create or update the local wallet, it automatically falls back to an in-memory SQLite shared-cache database.
- Run your applications in any read-only, non-root environment with zero configuration or storage mounts.

### 🔌 Clean, Consolidated RPC Surface

Nectar streamlines node communication by removing old condenser API legacy wrappers and local JSON specs:

- **Single Unified Path**: All JSON-RPC calls utilize the direct `api.method` shape using a clean, static OpenAPI mapping.
- **Shared Pooled Transport**: Built on `httpx`, utilizing connection pooling, keep-alive, and automatic retry/backoff logic to ensure resilient communication with blockchain nodes.

---

## 🚀 Quick Start

Ensure you have your environment ready (Python >= 3.10), then install Nectar:

```bash
pip install hive-nectar
```

### Basic Usage Example

```python
from nectar import Hive
from nectar.account import Account

# Initialize Nectar (uses the optimal shared connection-pooled node list)
hive = Hive()

# Fetch an account and query its balance
account = Account("thecrazygm", blockchain_instance=hive)
print(f"Account: {account.name}")
print(f"HIVE Balance: {account.balances['HIVE']}")
print(f"HBD Balance: {account.balances['HBD']}")
```

---

## 🛠️ System Prerequisites

For platforms where binary wheels for `coincurve` and `cryptography` are not precompiled, build tools are required to compile the C extensions:

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

## 🔒 Ledger Hardware Wallet Support

For Ledger (Nano S/X) hardware wallet signing, install the Ledger communication helper:

```bash
pip install ledgerblue
```

---

## 📜 Acknowledgements

Nectar is a modernized fork of [beem](https://github.com/holgern/beem), originally created by Holger Nahrstaedt, and includes [python-graphenelib](https://github.com/xeroc/python-graphenelib) created by Fabian Schuh (`xeroc`). We are deeply grateful to the original authors for laying the groundwork of Python-based blockchain tools.

---

## 🌐 Part of the SRBDE Ecosystem

This repository is proudly developed and maintained by the **Sustainable Resource and Business Development Enterprise (SRBDE)**. We build open-source tools and infrastructure for communities that build things together.

### ⚖️ The "Soil" Philosophy

We apply the logic of agricultural sustainability to software: our goal is to return more to the digital ecosystem than we extract.

- **Open source is our value, not our business model.**
- **Our commercial SaaS products fund our open-source core: the open work is the mission.**

### 🚀 Explore Our Work

- **Corporate Hub**: [ecoinstats.net](https://ecoinstats.net)
- **Open Gaming & TTRPGs**: [thecrazygm.com](https://thecrazygm.com)
- **Contribute**: We welcome audits, forks, and pull requests. Built to last for the decade, not the quarter.
