class Prefix:
    """This class is meant to allow changing the prefix.
    The prefix is used to link a public key to a specific blockchain.
    """

    prefix: str = "STM"

    def set_prefix(self, prefix: str | None) -> None:
        if prefix:
            self.prefix = prefix
