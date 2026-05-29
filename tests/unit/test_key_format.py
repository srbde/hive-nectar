from nectargraphenebase.account import Address, PrivateKey, PublicKey

key = {
    "public_key": "STM7jDPoMwyjVH5obFmqzFNp4Ffp7G2nvC7FKFkrMBpo7Sy4uq5Mj",
    "private_key": "20991828d456b389d0768ed7fb69bf26b9bb87208dd699ef49f10481c20d3e18",
    "private_key_WIF_format": "5J4eFhjREJA7hKG6KcvHofHMXyGQZCDpQE463PAaKo9xXY6UDPq",
    "bts_address": "STM8DvGQqzbgCR5FHiNsFf8kotEXr8VKD3mR",
    "pts_address": "Po3mqkgMzBL4F1VXJArwQxeWf3fWEpxUf3",
    "encrypted_private_key": "5e1ae410919c450dce1c476ae3ed3e5fe779ad248081d85b3dcf2888e698744d0a4b60efb7e854453bec3f6883bcbd1d",
    "blockchain_address": "4f3a560442a05e4fbb257e8dc5859b736306bace",
    "Uncompressed_BTC": "STMLAFmEtM8as1mbmjVcj5dphLdPguXquimn",
    "Compressed_BTC": "STMANNTSEaUviJgWLzJBersPmyFZBY4jJETY",
    "Uncompressed_PTS": "STMEgj7RM6FBwSoccGaESJLC3Mi18785bM3T",
    "Compressed_PTS": "STMD5rYtofD6D4UHJH6mo953P5wpBfMhdMEi",
}


def test_public_from_private():
    private_key = PrivateKey(key["private_key"])
    public_key = private_key.get_public_key()
    assert key["public_key"] == str(public_key)


def test_short_address():
    public_key = PublicKey(key["public_key"])
    assert key["bts_address"] == str(public_key.address)


def test_blockchain_address():
    public_key = PublicKey(key["public_key"])
    assert key["blockchain_address"] == repr(public_key.address)


def test_import_export():
    public_key = PublicKey(key["public_key"])
    assert key["public_key"] == str(public_key)


def test_to_wif():
    private_key = PrivateKey(key["private_key"])
    assert key["private_key_WIF_format"] == str(private_key)


def test_calc_pub_key():
    private_key = PrivateKey(key["private_key"])
    public_key = private_key.pubkey
    assert key["bts_address"] == str(public_key.address)


def test_btc_uncompressed():
    public_key = PublicKey(key["public_key"])
    address = Address.from_pubkey(public_key.uncompressed(), compressed=False, version=0)
    assert str(key["Uncompressed_BTC"]) == (format(address, "STM"))


def test_btc_compressed():
    public_key = PublicKey(key["public_key"])
    address = Address.from_pubkey(repr(public_key), version=0)
    assert str(key["Compressed_BTC"]) == (format(address, "STM"))


def test_pts_uncompressed():
    public_key = PublicKey(key["public_key"])
    address = Address.from_pubkey(public_key.uncompressed(), compressed=False, version=56)
    assert str(key["Uncompressed_PTS"]) == (format(address, "STM"))


def test_pts_compressed():
    public_key = PublicKey(key["public_key"])
    address = Address.from_pubkey(repr(public_key), version=56)
    assert str(key["Compressed_PTS"]) == (format(address, "STM"))
