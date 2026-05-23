Installation
============
The minimal working python version is 3.10

nectar can be installed parallel to python-steem/beem.

For Debian and Ubuntu, please ensure that the following packages are installed:

.. code:: bash

    sudo apt-get install build-essential libssl-dev python3-dev python3-pip libffi-dev libtool autoconf automake pkg-config

For Fedora and RHEL-derivatives, please ensure that the following packages are installed:

.. code:: bash

    sudo dnf install gcc openssl-devel python3-devel libffi-devel libtool autoconf automake pkgconfig

For OSX, please do the following::

    brew install openssl libtool autoconf automake libffi pkg-config
    export CFLAGS="-I$(brew --prefix openssl)/include $CFLAGS"
    export LDFLAGS="-L$(brew --prefix openssl)/lib $LDFLAGS"

For Termux on Android, please install the following packages:

.. code:: bash

    pkg install clang openssl python libtool autoconf automake libffi

Install hive-nectar
-------------------

The recommended way to install and manage dependencies is using `uv <https://docs.astral.sh/uv/>`_:

.. code:: bash

    uv add hive-nectar

Alternatively, you can use pip:

.. code:: bash

    pip install -U hive-nectar

Manual installation
-------------------

You can install nectar from this repository if you want the latest development version:

.. code:: bash

    git clone https://github.com/srbde/hive-nectar.git
    cd hive-nectar
    uv sync
    uv sync --dev

Run tests after install:

.. code:: bash

    uv run pytest

Enable Logging
--------------

Add the following for enabling logging in your python script::

    import logging
    log = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO)

When you want to see only critical errors, replace the last line by::

    logging.basicConfig(level=logging.CRITICAL)

Enable Logging
--------------

Add the following for enabling logging in your python script::

    import logging
    log = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO)

When you want to see only critical errors, replace the last line by::

    logging.basicConfig(level=logging.CRITICAL)
