# Static method→API mapping derived from the hived OpenAPI spec.
# We intentionally embed a small, opinionated subset to avoid shipping the full
# OpenAPI document with the package while still providing sensible defaults.
METHOD_API_MAP: dict[str, str] = {
    # Broadcast
    "broadcast_transaction": "network_broadcast_api",
    "broadcast_transaction_synchronous": "network_broadcast_api",
    # Accounts / database
    "find_accounts": "database_api",
    "get_accounts": "database_api",
    "get_dynamic_global_properties": "database_api",
    "get_reward_fund": "database_api",
    "get_reward_funds": "database_api",
    "get_feed_history": "database_api",
    "get_hardfork_properties": "database_api",
    "get_config": "database_api",
    "find_owner_histories": "database_api",
    "find_escrows": "database_api",
    "find_recurrent_transfers": "database_api",
    "get_owner_history": "database_api",
    "get_withdraw_routes": "database_api",
    "find_witness_schedule": "database_api",
    "find_accounts_recovery_requests": "database_api",
    "find_change_recovery_account_requests": "database_api",
    "find_savings_withdrawals": "database_api",
    "find_vesting_delegation_expirations": "database_api",
    "find_conversion_requests": "database_api",
    "find_hbd_conversion_requests": "database_api",
    # Blocks
    "get_block": "block_api",
    "get_block_header": "block_api",
    "get_block_range": "block_api",
    "get_account_count": "condenser_api",
    # Account history
    "get_account_history": "account_history_api",
    "get_transaction": "account_history_api",
    "get_ops_in_block": "account_history_api",
    "enum_virtual_ops": "account_history_api",
    # Keys
    "get_key_references": "account_by_key_api",
    # Witnesses (some nodes do not expose witness_api; database_api supports these)
    "get_witness_by_account": "condenser_api",
    "find_witnesses": "database_api",
    "get_witness_schedule": "database_api",
    "get_witness_count": "database_api",
    "get_active_witnesses": "database_api",
    "get_witness": "database_api",
    "get_witnesses": "database_api",
    "list_witnesses": "database_api",
    "list_witness_votes": "database_api",
    # Bridge (hivemind)
    "get_ranked_posts": "bridge",
    "get_account_posts": "bridge",
    "get_discussion": "bridge",
    "get_replies_by_last_update": "bridge",
    "get_follow_count": "condenser_api",
    "get_followers": "condenser_api",
    "get_following": "condenser_api",
    "get_blog": "condenser_api",
    "get_blog_entries": "condenser_api",
    "get_blog_authors": "bridge",
    "get_content": "bridge",
    "get_post": "bridge",
    "get_reblogged_by": "condenser_api",
    "get_active_votes": "condenser_api",
    "get_tags_used_by_author": "bridge",
    "get_follow_list": "bridge",
    "list_subscribers": "bridge",
    "list_community_roles": "bridge",
    "account_notifications": "bridge",
    "unread_notifications": "bridge",
    "list_all_subscriptions": "bridge",
    "list_communities": "bridge",
    # RC
    "get_resource_params": "rc_api",
    "get_resource_pool": "rc_api",
    "find_rc_accounts": "rc_api",
    # Market history
    "get_ticker": "market_history_api",
    "get_volume": "market_history_api",
    "get_order_book": "market_history_api",
    "get_recent_trades": "market_history_api",
    "get_trade_history": "market_history_api",
    "get_market_history": "market_history_api",
    "get_market_history_buckets": "market_history_api",
    # JSON-RPC meta
    "get_methods": "jsonrpc",
    # Proposals
    "find_proposals": "condenser_api",
    "get_trending_tags": "condenser_api",
    "get_discussions_by_promoted": "condenser_api",
}


def get_default_api_for_method(method_name: str) -> str | None:
    """
    Return the default API name for a method using the static map.

    Args:
        method_name: The RPC method (without API prefix), e.g., "get_account_history".

    Returns:
        The API name string (e.g., "account_history_api") or None if unknown.
    """
    return METHOD_API_MAP.get(method_name)
