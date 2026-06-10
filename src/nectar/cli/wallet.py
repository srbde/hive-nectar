import json
import logging
import os

import click
from prettytable import PrettyTable

from nectar.account import Account
from nectar.cli import cli
from nectar.cli.utils import (
    is_keyring_available,
    prompt_flag_callback,
    unlock_wallet,
)
from nectar.instance import set_shared_blockchain_instance, shared_blockchain_instance
from nectar.memo import Memo
from nectar.message import Message
from nectar.utils import (
    create_new_password,
    generate_password,
    import_coldcard_wif,
)
from nectargraphenebase.account import (
    Mnemonic,
    MnemonicKey,
    PasswordKey,
    PrivateKey,
)

log = logging.getLogger(__name__)


@cli.command()
@click.option("--wipe", is_flag=True, default=False, help="Wipe old wallet without prompt.")
def createwallet(wipe):
    """Create new wallet with a new password"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if hv.wallet.created() and not wipe:
        wipe_answer = click.prompt(
            "'Do you want to wipe your wallet? Are your sure? This is IRREVERSIBLE! If you dont have a backup you may lose access to your account! [y/n]",
            default="n",
        )
        if wipe_answer in ["y", "ye", "yes"]:
            hv.wallet.wipe(True)
        else:
            return
    elif wipe:
        hv.wallet.wipe(True)
    password = None
    password = click.prompt("New wallet password", confirmation_prompt=True, hide_input=True)
    if not bool(password):
        print("Password cannot be empty! Quitting...")
        return
    password_storage = hv.config["password_storage"]
    if password_storage == "keyring" and is_keyring_available():
        import keyring  # type: ignore

        password = keyring.set_password("nectar", "wallet", password)
    elif password_storage == "environment":
        print(
            "The new wallet password can be stored in the UNLOCK environment variable to skip password prompt!"
        )
    hv.wallet.wipe(True)
    hv.wallet.create(password)
    set_shared_blockchain_instance(hv)


@cli.command()
@click.option("--unlock", "-u", is_flag=True, default=False, help="Unlock wallet")
@click.option("--lock", "-l", is_flag=True, default=False, help="Lock wallet")
def walletinfo(unlock, lock):
    """Show info about wallet"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if lock:
        hv.wallet.lock()
    elif unlock:
        unlock_wallet(hv, allow_wif=False)

    t = PrettyTable(["Key", "Value"])
    t.align = "l"
    t.add_row(["created", hv.wallet.created()])
    t.add_row(["locked", hv.wallet.locked()])
    t.add_row(["Number of stored keys", len(hv.wallet.getPublicKeys())])
    t.add_row(["sql-file", hv.wallet.store.sqlite_file])
    password_storage = hv.config["password_storage"]
    t.add_row(["password_storage", password_storage])
    password = os.environ.get("UNLOCK")
    if password is not None:
        t.add_row(["UNLOCK env set", "yes"])
    else:
        t.add_row(["UNLOCK env set", "no"])
    if is_keyring_available():
        t.add_row(["keyring installed", "yes"])
    else:
        t.add_row(["keyring installed", "no"])

    if unlock:
        if unlock_wallet(hv, allow_wif=False):
            t.add_row(["Wallet unlock", "successful"])
        else:
            t.add_row(["Wallet unlock", "not working"])
    print(t)


@cli.command()
@click.option(
    "--unsafe-import-key",
    help="WIF key to parse (unsafe, unless shell history is deleted afterwards)",
    multiple=True,
)
def parsewif(unsafe_import_key):
    """Parse a WIF private key without importing"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if unsafe_import_key:
        for key in unsafe_import_key:
            try:
                pubkey = PrivateKey(key, prefix=hv.prefix).pubkey
                print(pubkey)
                account = hv.wallet.getAccountFromPublicKey(str(pubkey))
                account = Account(account, blockchain_instance=hv)
                key_type = hv.wallet.getKeyType(account, str(pubkey))
                print(f"Account: {account['name']} - {key_type}")
            except Exception as e:
                print(str(e))
    else:
        while True:
            wifkey = click.prompt("Enter private key", confirmation_prompt=False, hide_input=True)
            if not wifkey or wifkey == "quit" or wifkey == "exit":
                break
            try:
                pubkey = PrivateKey(wifkey, prefix=hv.prefix).pubkey
                print(pubkey)
                account = hv.wallet.getAccountFromPublicKey(str(pubkey))
                account = Account(account, blockchain_instance=hv)
                key_type = hv.wallet.getKeyType(account, str(pubkey))
                print(f"Account: {account['name']} - {key_type}")
            except Exception as e:
                print(str(e))
                continue


@cli.command()
@click.option(
    "--unsafe-import-key",
    help="Private key to import to wallet (unsafe, unless shell history is deleted afterwards)",
)
def addkey(unsafe_import_key):
    """Add key to wallet

    When no [OPTION] is given, a password prompt for unlocking the wallet
    and a prompt for entering the private key are shown.
    """
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not unlock_wallet(hv, allow_wif=False):
        return
    if not unsafe_import_key:
        unsafe_import_key = click.prompt(
            "Enter private key", confirmation_prompt=False, hide_input=True
        )
    hv.wallet.addPrivateKey(unsafe_import_key)
    set_shared_blockchain_instance(hv)


@cli.command()
@click.option(
    "--confirm",
    prompt="Are your sure? This is IRREVERSIBLE! If you dont have a backup you may lose access to your account!",
    hide_input=False,
    callback=prompt_flag_callback,
    is_flag=True,
    confirmation_prompt=False,
    help="Please confirm!",
)
@click.argument("pub")
def delkey(confirm, pub):
    """Delete key from the wallet

    PUB is the public key from the private key
    which will be deleted from the wallet
    """
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not unlock_wallet(hv, allow_wif=False):
        return
    hv.wallet.removePrivateKeyFromPublicKey(pub)
    set_shared_blockchain_instance(hv)


@cli.command()
@click.option(
    "--import-word-list",
    "-l",
    help="Imports a BIP39 wordlist and derives a private and public key",
    is_flag=True,
    default=False,
)
@click.option("--strength", help="Defines word list length for BIP39 (default = 256).", default=256)
@click.option("--passphrase", "-p", help="Sets a BIP39 passphrase", is_flag=True, default=False)
@click.option(
    "--path",
    "-m",
    help="Sets a path for BIP39 key creations. When path is set, network, role, account_keys, account and sequence is not used",
)
@click.option(
    "--network",
    "-n",
    help="Network index for BIP39 (default is 13 for Hive)",
    default=13,
)
@click.option(
    "--role",
    "-r",
    help="Defines which key role should be created (default = owner).",
    default="owner",
)
@click.option(
    "--account-keys",
    "-k",
    help="Derives four BIP39 keys for each role",
    is_flag=True,
    default=False,
)
@click.option(
    "--sequence", "-s", help="Sequence key number, when using BIP39 (default is 0)", default=0
)
@click.option("--account", "-a", help="sequence number for BIP39 key, default = 0")
@click.option(
    "--wif",
    "-w",
    help="Defines how many times the password is replaced by its WIF representation for password based keys (default = 0).",
)
@click.option(
    "--export-pub",
    "-u",
    help="Exports the public account keys to a json file for account creation or keychange",
)
@click.option("--export", "-e", help="The results are stored in a text file and will not be shown")
def keygen(
    import_word_list,
    strength,
    passphrase,
    path,
    network,
    role,
    account_keys,
    sequence,
    account,
    wif,
    export_pub,
    export,
):
    """Creates a new random BIP39 key and prints its derived private key and public key.
    The generated key is not stored. Can also be used to create new keys for an account.
    Can also be used to derive account keys from a password or BIP39 wordlist.
    """
    hv = shared_blockchain_instance()
    pub_json = {"owner": "", "active": "", "posting": "", "memo": ""}

    if not account_keys and len(role.split(",")) > 1:
        roles = role.split(",")
        account_keys = True
    else:
        roles = ["owner", "active", "posting", "memo"]
    if wif is not None:
        wif = int(wif)
    else:
        wif = 0

    if hv.use_ledger:
        if hv.rpc is not None:
            hv.rpc.rpcconnect()
        ledgertx = hv.new_tx()
        ledgertx.constructTx()
        if account is None:
            account = 0
        else:
            account = int(account)
        t = PrettyTable(["Key", "Value"])
        t_pub = PrettyTable(["Key", "Value"])
        t.align = "l"
        t_pub.align = "l"
        t.add_row(["Account sequence", account])
        t.add_row(["Key sequence", sequence])

        if account_keys and path is None:
            for r in roles:
                path = ledgertx.ledgertx.build_path(r, account, sequence)
                pubkey = ledgertx.ledgertx.get_pubkey(path, request_screen_approval=False)
                aprove_key = PrettyTable(["Approve %s Key" % r])
                aprove_key.align = "l"
                aprove_key.add_row([format(pubkey, "STM")])
                print(aprove_key)
                ledgertx.ledgertx.get_pubkey(path, request_screen_approval=True)
                t_pub.add_row(["%s Public Key" % r, format(pubkey, "STM")])
                t.add_row(["%s path" % r, path])
                pub_json[r] = format(pubkey, "STM")
        else:
            if path is None:
                path = ledgertx.ledgertx.build_path(role, account, sequence)
            t.add_row(["Key role", role])
            t.add_row(["path", path])
            pubkey = ledgertx.ledgertx.get_pubkey(path, request_screen_approval=False)
            aprove_key = PrettyTable(["Approve %s Key" % role])
            aprove_key.align = "l"
            aprove_key.add_row([format(pubkey, "STM")])
            print(aprove_key)
            ledgertx.ledgertx.get_pubkey(path, request_screen_approval=True)
            t_pub.add_row(["Public Key", format(pubkey, "STM")])
            pub_json[role] = format(pubkey, "STM")
    else:
        if account is None:
            account = 0
        else:
            account = int(account)
        if import_word_list:
            n_words = click.prompt("Enter word list length or complete word list")
            if len(n_words.split(" ")) > 0:
                word_list = n_words
            else:
                n_words = int(n_words)
                word_array = []
                word = None
                m = Mnemonic()
                while len(word_array) < n_words:
                    word = click.prompt(
                        "Enter %d. mnemnoric word" % (len(word_array) + 1), type=str
                    )
                    word = m.expand_word(word)
                    if m.check_word(word):
                        word_array.append(word)
                    print(" ".join(word_array))
                word_list = " ".join(word_array)
            if passphrase:
                passphrase = click.prompt(
                    "Enter passphrase", confirmation_prompt=True, hide_input=True
                )
            else:
                passphrase = ""
            mk = MnemonicKey(
                word_list=word_list,
                passphrase=passphrase,
                account_sequence=account,
                key_sequence=sequence,
            )
            if path is not None:
                mk.set_path(path)
            else:
                mk.set_path_BIP48(
                    network_index=network,
                    role=role,
                    account_sequence=account,
                    key_sequence=sequence,
                )
        else:
            mk = MnemonicKey(account_sequence=account, key_sequence=sequence)
            if path is not None:
                mk.set_path(path)
            else:
                mk.set_path_BIP48(
                    network_index=network,
                    role=role,
                    account_sequence=account,
                    key_sequence=sequence,
                )
            if passphrase:
                passphrase = click.prompt(
                    "Enter passphrase", confirmation_prompt=True, hide_input=True
                )
            else:
                passphrase = ""
            word_list = mk.generate_mnemonic(passphrase=passphrase, strength=strength)
        t = PrettyTable(["Key", "Value"])
        t_pub = PrettyTable(["Key", "Value"])
        t.align = "l"
        t_pub.align = "l"
        t.add_row(["Account sequence", account])
        t.add_row(["Key sequence", sequence])
        if account_keys and path is None:
            for r in roles:
                t.add_row(["%s Private Key" % r, str(mk.get_private())])
                mk.set_path_BIP48(
                    network_index=network, role=r, account_sequence=account, key_sequence=sequence
                )
                t_pub.add_row(["%s Public Key" % r, format(mk.get_public(), "STM")])
                t.add_row(["%s path" % r, mk.get_path()])
                pub_json[r] = format(mk.get_public(), "STM")
            if passphrase != "":
                t.add_row(["Passphrase", passphrase])
            t.add_row(["BIP39 wordlist", word_list])
        else:
            t.add_row(["Key role", role])
            t.add_row(["path", mk.get_path()])
            t.add_row(["BIP39 wordlist", word_list.lower()])
            if passphrase != "":
                t.add_row(["Passphrase", passphrase])
            t.add_row(["Private Key", str(mk.get_private())])
            t_pub.add_row(["Public Key", format(mk.get_public(), "STM")])
            pub_json[role] = format(mk.get_public(), "STM")
    if export_pub and export_pub != "":
        pub_json = json.dumps(pub_json, indent=4)
        with open(export_pub, "w") as fp:
            fp.write(pub_json)
        print("%s was sucessfully saved." % export_pub)
    if export and export != "":
        with open(export, "w") as fp:
            fp.write(str(t))
            fp.write("\n")
            fp.write(str(t_pub))
        print("%s was sucessfully saved." % export)
    else:
        print(t_pub)
        print(t)


@cli.command()
@click.option(
    "--role",
    "-r",
    help="Defines which key role should be created. When owner is not set as role and an cold card wif is imported, the Master Password is not shown. (default = owner,active,posting,memo when creating account keys).",
    default="owner,active,posting,memo",
)
@click.option("--account", "-a", help="account name for password based key generation")
@click.option(
    "--import-password",
    "-i",
    help="Imports a password and derives all four account keys",
    is_flag=True,
    default=False,
)
@click.option(
    "--import-coldcard",
    "-o",
    help="Text file with a BIP85 WIF generated by a coldcard. The imported WIF is used to derives all four account keys",
)
@click.option(
    "--wif",
    "-w",
    help="Defines how many times the password is replaced by its WIF representation for password based keys (default = 0 or 1 when importing a cold card wif).",
)
@click.option(
    "--export-pub",
    "-u",
    help="Exports the public account keys to a json file for account creation or keychange",
)
@click.option("--export", "-e", help="The results are stored in a text file and will not be shown")
def passwordgen(role, account, import_password, import_coldcard, wif, export_pub, export):
    """Creates a new password based key and prints its derived private key and public key.
    The generated key is not stored. The password is used to create new keys for an account.
    """
    hv = shared_blockchain_instance()
    if not account:
        account = hv.config["default_account"]
    if import_password:
        import_password = click.prompt("Enter password", confirmation_prompt=False, hide_input=True)
    elif import_coldcard is not None:
        import_password, path = import_coldcard_wif(import_coldcard)
    else:
        import_password = create_new_password(length=32)
    pub_json = {"owner": "", "active": "", "posting": "", "memo": ""}

    if len(role.split(",")) > 1:
        roles = role.split(",")
    elif role in ["owner", "active", "posting", "memo"]:
        roles = [role]
    else:
        roles = ["owner", "active", "posting", "memo"]
    if wif is not None:
        wif = int(wif)
    elif import_coldcard:
        wif = 1
    else:
        wif = 0

    password = generate_password(import_password, wif)
    t = PrettyTable(["Key", "Value"])
    t_pub = PrettyTable(["Key", "Value"])
    t.add_row(["Username", account])
    t_pub.add_row(["Username", account])
    if import_coldcard:
        t_pub.add_row(["cold card path", path])
    t.align = "l"
    t_pub.align = "l"
    for r in roles:
        pk = PasswordKey(account, password, role=r)
        t.add_row(["%s Private Key" % r, str(pk.get_private())])
        t_pub.add_row(["%s Public Key" % r, format(pk.get_public(), "STM")])
        pub_json[r] = format(pk.get_public(), "STM")
    if "owner" in roles or import_coldcard is None:
        t.add_row(["Backup (Master) Password", password])
    if wif > 0:
        t.add_row(["WIF itersions", wif])
        if "owner" in roles or import_coldcard is None:
            t.add_row(["Entered/created Password", import_password])

    if export_pub and export_pub != "":
        pub_json = json.dumps(pub_json, indent=4)
        with open(export_pub, "w") as fp:
            fp.write(pub_json)
        print("%s was sucessfully saved." % export_pub)
    if export and export != "":
        with open(export, "w") as fp:
            fp.write(str(t))
            fp.write("\n")
            fp.write(str(t_pub))
        print("%s was sucessfully saved." % export)
    else:
        print(t_pub)
        print(t)


@cli.command()
@click.option("--path", "-p", help="Set path (when using ledger)")
@click.option(
    "--ledger-approval",
    "-a",
    is_flag=True,
    default=False,
    help="When set, you can confirm the shown pubkey on your ledger.",
)
def listkeys(path, ledger_approval):
    """Show stored keys

    Can be used to receive and approve the pubkey obtained from the ledger
    """
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()

    if hv.use_ledger:
        if path is None:
            path = hv.config["default_path"]
        t = PrettyTable(["Available Key for %s" % path])
        t.align = "l"
        ledgertx = hv.new_tx()
        ledgertx.constructTx()
        pubkey = ledgertx.ledgertx.get_pubkey(path, request_screen_approval=False)
        t.add_row([str(pubkey)])
        if ledger_approval:
            print(t)
            ledgertx.ledgertx.get_pubkey(path, request_screen_approval=True)
    else:
        t = PrettyTable(["Available Key"])
        t.align = "l"
        for key in hv.wallet.getPublicKeys():
            t.add_row([key])
    print(t)


@cli.command()
def changewalletpassphrase():
    """Change wallet password"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not unlock_wallet(hv, allow_wif=False):
        return
    newpassword = None
    newpassword = click.prompt("New wallet password", confirmation_prompt=True, hide_input=True)
    if not bool(newpassword):
        print("Password cannot be empty! Quitting...")
        return
    password_storage = hv.config["password_storage"]
    if password_storage == "keyring" and is_keyring_available():
        import keyring  # type: ignore

        keyring.set_password("nectar", "wallet", newpassword)
    elif password_storage == "environment":
        print(
            "The new wallet password can be stored in the UNLOCK invironment variable to skip password prompt!"
        )
    hv.wallet.changePassphrase(newpassword)


@cli.command()
@click.argument("message_file", nargs=1, required=False)
@click.option("--account", "-a", help="Account which should sign")
@click.option(
    "--verify", "-v", help="Verify a message instead of signing it", is_flag=True, default=False
)
def message(message_file, account, verify):
    """Sign and verify a message"""
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    if message_file is not None:
        with open(message_file) as f:
            msg_content = f.read()
    elif verify:
        print(
            "Please store the signed message into a text file and append the file path to hive-nectar message -v"
        )
        return
    else:
        msg_content = input("Enter message: ")
    m = Message(msg_content, blockchain_instance=hv)
    if verify:
        if m.verify():
            print("Could verify message!")
        else:
            print("Could not verify message!")
    else:
        if not unlock_wallet(hv):
            return
        signed = m.sign(account)
        out = signed if isinstance(signed, str) else json.dumps(signed, indent=4)
    if message_file is not None and not verify:
        with open(message_file, "w", encoding="utf-8") as f:
            f.write(out)
    elif not verify:
        print(out)


@cli.command()
@click.argument("memo", nargs=-1)
@click.option("--account", "-a", help="Account which decrypts the memo with its memo key")
@click.option(
    "--output", "-o", help="Output file name. Result is stored, when set instead of printed."
)
@click.option(
    "--info",
    "-i",
    help="Shows information about public keys and used nonce",
    is_flag=True,
    default=False,
)
@click.option("--text", "-t", help="Reads the text file content", is_flag=True, default=False)
@click.option("--binary", "-b", help="Reads the binary file content", is_flag=True, default=False)
def decrypt(memo, account, output, info, text, binary):
    """decrypt a (or more than one) decrypted memo/file with your memo key"""
    if text and binary:
        print("You cannot set text and binary!")
        return
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    m = Memo(from_account=None, to_account=account, blockchain_instance=hv)

    if not unlock_wallet(hv):
        return
    for entry in memo:
        print("\n")
        if not binary and info:
            from_key, to_key, nonce = m.extract_decrypt_memo_data(entry)
            try:
                from_account = hv.wallet.getAccountFromPublicKey(str(from_key))
                to_account = hv.wallet.getAccountFromPublicKey(str(to_key))
                if from_account is not None:
                    print("from: %s" % str(from_account))
                else:
                    print("from: %s" % str(from_key))
                if to_account is not None:
                    print("to: %s" % str(to_account))
                else:
                    print("to: %s" % str(to_key))
                print("nonce: %s" % nonce)
            except Exception:
                print("from: %s" % str(from_key))
                print("to: %s" % str(to_key))
                print("nonce: %s" % nonce)
        if text:
            with open(entry) as f:
                message = f.read()
        elif binary:
            if output is None:
                output = entry + ".dec"
            ret = m.decrypt_binary(entry, output, buffer_size=2048)
            if info:
                if ret is None:
                    print("No information available for decrypt_binary result")
                    return
                t = PrettyTable(["Key", "Value"])
                t.align = "l"
                t.add_row(["file", entry])
                for key in ret:
                    t.add_row([key, ret[key]])
                print(t)
        else:
            message = entry
        if text:
            out = m.decrypt(message)
            if out is None:
                raise ValueError("Failed to decrypt message")
            if output is None:
                output = entry
            with open(output, "w", encoding="utf-8") as f:
                f.write(out)
        elif not binary:
            out = m.decrypt(message)
            if out is None:
                raise ValueError("Failed to decrypt message")
            if info:
                print("message: %s" % out)
            if output:
                with open(output, "w", encoding="utf-8") as f:
                    f.write(out)
            elif not info:
                print(out)


@cli.command()
@click.argument("receiver", nargs=1)
@click.argument("memo", nargs=-1)
@click.option("--account", "-a", help="Account which encrypts the memo with its memo key")
@click.option(
    "--output", "-o", help="Output file name. Result is stored, when set instead of printed."
)
@click.option("--text", "-t", help="Reads the text file content", is_flag=True, default=False)
@click.option("--binary", "-b", help="Reads the binary file content", is_flag=True, default=False)
def encrypt(receiver, memo, account, output, text, binary):
    """encrypt a (or more than one) memo text/file with the your memo key"""
    if text and binary:
        print("You cannot set text and binary!")
        return
    hv = shared_blockchain_instance()
    if hv.rpc is not None:
        hv.rpc.rpcconnect()
    if not account:
        account = hv.config["default_account"]
    m = Memo(from_account=account, to_account=receiver, blockchain_instance=hv)
    if not unlock_wallet(hv):
        return
    for entry in memo:
        print("\n")
        if text:
            with open(entry) as f:
                message = f.read()
            if message[0] == "#":
                message = message[1:]
        elif binary:
            if output is None:
                output = entry + ".enc"
            m.encrypt_binary(entry, output, buffer_size=2048)
        else:
            message = entry
            if message[0] == "#":
                message = message[1:]

        if text:
            encrypted = m.encrypt(message)
            if encrypted is None:
                print("Failed to encrypt message")
                return
            out = encrypted.get("message") if isinstance(encrypted, dict) else encrypted
            if out is None:
                print("Failed to encrypt message")
                return
            if output is None:
                output = entry
            with open(output, "w", encoding="utf-8") as f:
                f.write(out)
        elif not binary:
            encrypted = m.encrypt(message)
            if encrypted is None:
                print("Failed to encrypt message")
                return
            out = encrypted.get("message") if isinstance(encrypted, dict) else encrypted
            if out is None:
                print("Failed to encrypt message")
                return
            if output is None:
                print(out)
            else:
                with open(output, "w", encoding="utf-8") as f:
                    f.write(out)
