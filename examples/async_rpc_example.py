#!/usr/bin/env python3
"""Example script demonstrating the asynchronous RPC client (AsyncNodeRPC) in hive-nectar."""

import asyncio

from nectarapi.noderpc import AsyncNodeRPC


async def main() -> None:
    # Initialize the asynchronous RPC client with fallback public nodes
    nodes = ["https://api.hive.blog", "https://api.openhive.network"]
    rpc = AsyncNodeRPC(nodes)

    print("Connecting to Hive nodes asynchronously...")
    rpc.rpcconnect()

    try:
        # Fetch dynamic global properties asynchronously
        print("Fetching dynamic global properties...")
        props = await rpc.get_dynamic_global_properties()
        head_block = props.get("head_block_number")
        head_time = props.get("time")
        print(f"Success! Head block number: {head_block} (Time: {head_time})")

        # Fetch the connected node's configuration asynchronously
        print("\nFetching node config...")
        config = await rpc.get_config()
        version = config.get("HIVE_BLOCKCHAIN_VERSION", "unknown")
        print(f"Blockchain Version: {version}")

    except Exception as e:
        print(f"Error executing async RPC calls: {e}")


if __name__ == "__main__":
    asyncio.run(main())
