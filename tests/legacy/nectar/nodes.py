from nectar import Hive
from nectar.nodelist import NodeList


def get_hive_nodes():
    """
    Return static Hive node endpoints for testing.

    Using static nodes to avoid hammering the beacon API during tests.

    Returns:
        list[str]: Static Hive node endpoint URLs.
    """
    # Use a few reliable static nodes for testing
    return [
        "https://api.hive.blog",
        "https://api.openhive.network",
        "https://api.syncad.com",
        "https://api.deathwing.me",
        "https://rpc.mahdiyari.info",
    ]


def get_hive_nodes_with_beacon():
    """
    Return the current Hive node endpoints after refreshing the NodeList.

    This function instantiates a NodeList, retrieves its Hive node endpoints, uses those endpoints to construct a Hive client (with num_retries=10) and calls NodeList.update_nodes(...) to refresh the stored node information. It then returns the updated list of Hive node endpoints.

    NOTE: This hits the beacon API and should only be used when explicitly needed.

    Returns:
        list[str]: Updated Hive node endpoint URLs.
    """
    nodelist = NodeList()
    nodes = nodelist.get_hive_nodes()
    nodelist.update_nodes(blockchain_instance=Hive(node=nodes, num_retries=10, use_condenser=False))
    return nodelist.get_hive_nodes()
