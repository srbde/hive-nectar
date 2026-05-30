import json
import logging
import re
import warnings
from bisect import bisect_left
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Generator, List, Optional, Union

from nectar.account import Account
from nectar.amount import Amount
from nectar.constants import HIVE_100_PERCENT, HIVE_VOTE_REGENERATION_SECONDS
from nectar.instance import shared_blockchain_instance
from nectar.utils import (
    addTzInfo,
    formatTimeString,
    parse_time,
    reputation_to_score,
)
from nectar.vote import Vote

log = logging.getLogger(__name__)


class AccountSnapshot(list):
    """This class allows to easily access Account history

    :param str account_name: Name of the account
    :param Hive blockchain_instance: Hive instance
    """

    def __init__(
        self,
        account: Union[str, Account],
        account_history: Optional[List[Dict[str, Any]]] = None,
        blockchain_instance: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(account_history or [])
        # Warn about any unused kwargs to maintain backward compatibility
        """
        Initialize an AccountSnapshot for the given account.

        Creates an Account object for the target account (using the provided blockchain instance or the shared instance), resets internal snapshot state, and populates the snapshot list with any provided account_history. Any unexpected keyword arguments are accepted but ignored; a DeprecationWarning is emitted for each.

        Parameters:
            account (str or Account): Account identifier or existing Account object to build the snapshot for.
            account_history (iterable, optional): Pre-fetched sequence of account operations to initialize the snapshot with. Defaults to an empty list.

        Notes:
            - blockchain_instance is accepted but not documented here as a service-like parameter; if provided it overrides the shared blockchain instance used to construct the Account.
            - This initializer mutates internal state (calls reset) and appends account_history into the snapshot's underlying list.
        """
        if kwargs:
            for key in kwargs:
                warnings.warn(
                    f"Unexpected keyword argument '{key}' passed to AccountSnapshot.__init__. "
                    "This may be a deprecated parameter and will be ignored.",
                    DeprecationWarning,
                    stacklevel=2,
                )
        self.blockchain = blockchain_instance or shared_blockchain_instance()
        self.account = Account(account, blockchain_instance=self.blockchain)
        self.reset()
        # super().__init__(account_history or [])

    def reset(self) -> None:
        """
        Reset internal time-series and aggregation arrays while preserving the stored account history.

        Reinitializes per-timestamp state used to build derived metrics (vesting, Hive/HBD balances, delegations,
        operation statistics, reward and vote timelines, reputation and voting-power arrays). Does not modify
        the list contents (the stored raw account history).
        """
        self.own_vests = [
            Amount(0, self.blockchain.vest_token_symbol, blockchain_instance=self.blockchain)
        ]
        self.own_hive = [
            Amount(0, self.blockchain.token_symbol, blockchain_instance=self.blockchain)
        ]
        self.own_hbd = [
            Amount(0, self.blockchain.backed_token_symbol, blockchain_instance=self.blockchain)
        ]
        self.delegated_vests_in = [{}]
        self.delegated_vests_out = [{}]
        self.timestamps = [addTzInfo(datetime(1970, 1, 1, 0, 0, 0, 0))]
        self.ops_statistics = {}
        for key in self.blockchain.get_operation_names():
            self.ops_statistics[key] = 0
        self.reward_timestamps = []
        self.author_rewards = []
        self.curation_rewards = []
        self.curation_per_1000_HP_timestamp = []
        self.curation_per_1000_HP = []
        self.out_vote_timestamp = []
        self.out_vote_weight = []
        self.in_vote_timestamp = []
        self.in_vote_weight = []
        self.in_vote_rep = []
        self.in_vote_rshares = []
        self.vp = []
        self.vp_timestamp = []
        self.downvote_vp = []
        self.downvote_vp_timestamp = []
        self.rep = []
        self.rep_timestamp = []

    def search(
        self,
        search_str: str,
        start: Optional[Union[datetime, date, time, int]] = None,
        stop: Optional[Union[datetime, date, time, int]] = None,
        use_block_num: bool = True,
    ) -> List[Dict[str, Any]]:
        """Returns ops in the given range"""
        ops = []
        if start is not None and not isinstance(start, int):
            start = addTzInfo(start)
        if stop is not None and not isinstance(stop, int):
            stop = addTzInfo(stop)
        for op in self:
            if use_block_num and start is not None and isinstance(start, int):
                if op["block"] < start:
                    continue
            elif not use_block_num and start is not None and isinstance(start, int):
                if op["index"] < start:
                    continue
            elif start is not None and isinstance(start, (datetime, date, time)):
                start_dt = addTzInfo(start) if isinstance(start, (date, time)) else start
                # Ensure start_dt is always datetime for comparison
                if isinstance(start_dt, (date, time)):
                    start_dt = addTzInfo(start_dt)
                if start_dt is None:
                    continue
                # Convert to datetime if still not datetime
                if isinstance(start_dt, time):
                    start_dt = datetime.combine(datetime.now().date(), start_dt)
                elif isinstance(start_dt, date):
                    start_dt = datetime.combine(start_dt, time.min)
                op_timestamp_dt = formatTimeString(op["timestamp"])
                if isinstance(op_timestamp_dt, str):
                    op_timestamp_dt = parse_time(op_timestamp_dt)
                if start_dt > op_timestamp_dt:
                    continue
            if use_block_num and stop is not None and isinstance(stop, int):
                if op["block"] > stop:
                    continue
            elif not use_block_num and stop is not None and isinstance(stop, int):
                if op["index"] > stop:
                    continue
            elif stop is not None and isinstance(stop, (datetime, date, time)):
                stop_dt = addTzInfo(stop) if isinstance(stop, (date, time)) else stop
                # Ensure stop_dt is always datetime for comparison
                if isinstance(stop_dt, (date, time)):
                    stop_dt = addTzInfo(stop_dt)
                if stop_dt is None:
                    continue
                # Convert to datetime if still not datetime
                if isinstance(stop_dt, time):
                    stop_dt = datetime.combine(datetime.now().date(), stop_dt)
                elif isinstance(stop_dt, date):
                    stop_dt = datetime.combine(stop_dt, time.min)
                op_timestamp_dt = formatTimeString(op["timestamp"])
                if isinstance(op_timestamp_dt, str):
                    op_timestamp_dt = parse_time(op_timestamp_dt)
                if stop_dt < op_timestamp_dt:
                    continue
            op_string = json.dumps(list(op.values()))
            if re.search(search_str, op_string):
                ops.append(op)
        return ops

    def get_ops(
        self,
        start: Optional[Union[datetime, date, time, int]] = None,
        stop: Optional[Union[datetime, date, time, int]] = None,
        use_block_num: bool = True,
        only_ops: Optional[List[str]] = None,
        exclude_ops: Optional[List[str]] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """Returns ops in the given range"""
        if only_ops is None:
            only_ops = []
        if exclude_ops is None:
            exclude_ops = []
        if start is not None and not isinstance(start, int):
            start = addTzInfo(start)
        if stop is not None and not isinstance(stop, int):
            stop = addTzInfo(stop)
        for op in self:
            if use_block_num and start is not None and isinstance(start, int):
                if op["block"] < start:
                    continue
            elif not use_block_num and start is not None and isinstance(start, int):
                if op["index"] < start:
                    continue
            elif start is not None and isinstance(start, (datetime, date, time)):
                start_dt = addTzInfo(start) if isinstance(start, (date, time)) else start
                # Ensure start_dt is always datetime for comparison
                if isinstance(start_dt, (date, time)):
                    start_dt = addTzInfo(start_dt)
                if start_dt is None:
                    continue
                # Convert to datetime if still not datetime
                if isinstance(start_dt, time):
                    start_dt = datetime.combine(datetime.now().date(), start_dt)
                elif isinstance(start_dt, date):
                    start_dt = datetime.combine(start_dt, time.min)
                op_timestamp_dt = formatTimeString(op["timestamp"])
                if isinstance(op_timestamp_dt, str):
                    op_timestamp_dt = parse_time(op_timestamp_dt)
                if start_dt > op_timestamp_dt:
                    continue
            if use_block_num and stop is not None and isinstance(stop, int):
                if op["block"] > stop:
                    continue
            elif not use_block_num and stop is not None and isinstance(stop, int):
                if op["index"] > stop:
                    continue
            elif stop is not None and isinstance(stop, (datetime, date, time)):
                stop_dt = addTzInfo(stop) if isinstance(stop, (date, time)) else stop
                # Ensure stop_dt is always datetime for comparison
                if isinstance(stop_dt, (date, time)):
                    stop_dt = addTzInfo(stop_dt)
                if stop_dt is None:
                    continue
                # Convert to datetime if still not datetime
                if isinstance(stop_dt, time):
                    stop_dt = datetime.combine(datetime.now().date(), stop_dt)
                elif isinstance(stop_dt, date):
                    stop_dt = datetime.combine(stop_dt, time.min)
                op_timestamp_dt = formatTimeString(op["timestamp"])
                if isinstance(op_timestamp_dt, str):
                    op_timestamp_dt = parse_time(op_timestamp_dt)
                if stop_dt < op_timestamp_dt:
                    continue
            if exclude_ops and op["type"] in exclude_ops:
                continue
            if not only_ops or op["type"] in only_ops:
                yield op

    def get_data(
        self, timestamp: Optional[Union[datetime, date, time]] = None, index: int = 0
    ) -> Dict[str, Any]:
        """
        Return a dictionary snapshot of the account state at or immediately before the given timestamp.

        If timestamp is None the current UTC time is used. The timestamp is normalized to a timezone-aware UTC value. The method finds the most recent stored tick whose timestamp is <= the requested time and returns a dict with the corresponding state:
        - "timestamp": stored timestamp used
        - "vests": own vesting shares at that tick
        - "delegated_vests_in": mapping of incoming delegations at that tick
        - "delegated_vests_out": mapping of outgoing delegations at that tick
        - "sp_own": Hive Power equivalent of own vests at that tick
        - "sp_eff": effective Hive Power (own + delegated_in - delegated_out) at that tick
        - "hive": liquid HIVE balance at that tick
        - "hbd": liquid HBD balance at that tick
        - "index": index into the internal arrays for that tick

        Returns an empty dict if the requested timestamp is earlier than the earliest stored timestamp.
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        timestamp = addTzInfo(timestamp)
        # Ensure timestamp is datetime for bisect_left
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        elif isinstance(timestamp, (date, time)):
            timestamp = addTzInfo(timestamp)
            if timestamp is None:
                timestamp = datetime.now(timezone.utc)
        # Find rightmost value less than x
        i = bisect_left(self.timestamps, timestamp)
        if i:
            index = i - 1
        else:
            return {}
        ts = self.timestamps[index]
        own = self.own_vests[index]
        din = self.delegated_vests_in[index]
        dout = self.delegated_vests_out[index]
        hive = self.own_hive[index]
        hbd = self.own_hbd[index]
        sum_in = sum([din[key].amount for key in din])
        sum_out = sum([dout[key].amount for key in dout])
        sp_in = self.blockchain.vests_to_hp(sum_in, timestamp=ts)
        sp_out = self.blockchain.vests_to_hp(sum_out, timestamp=ts)
        sp_own = self.blockchain.vests_to_hp(own, timestamp=ts)
        sp_eff = sp_own + sp_in - sp_out
        return {
            "timestamp": ts,
            "vests": own,
            "delegated_vests_in": din,
            "delegated_vests_out": dout,
            "sp_own": sp_own,
            "sp_eff": sp_eff,
            "hive": hive,
            "hbd": hbd,
            "index": index,
        }

    def get_account_history(
        self,
        start: Optional[Union[datetime, date, time, int]] = None,
        stop: Optional[Union[datetime, date, time, int]] = None,
        use_block_num: bool = True,
    ) -> None:
        """
        Populate the snapshot with the account's history between start and stop.

        Fetches operations from the underlying Account.history iterator and replaces the snapshot's contents with those operations. If start/stop are provided they may be block numbers or datetimes; set use_block_num=False to interpret them as virtual operation indices/timestamps instead of block numbers.
        """
        self.clear()
        self.extend(
            h for h in self.account.history(start=start, stop=stop, use_block_num=use_block_num)
        )

    def update_rewards(
        self,
        timestamp: Union[datetime, int],
        curation_reward: Union[Amount, float],
        author_vests: Union[Amount, float],
        author_hive: Union[Amount, float],
        author_hbd: Union[Amount, float],
    ) -> None:
        """
        Record a reward event at a given timestamp.

        Appends the reward timestamp, the curation portion, and the author's reward components (vests, hive, hbd)
        to the snapshot's internal reward arrays so they can be used by later aggregation and analysis.

        Parameters:
            timestamp (datetime or int): Event time (timezone-aware datetime or block/time integer) for the reward.
            curation_reward (Amount or number): Curation reward amount (in vests or numeric representation used by the codebase).
            author_vests (Amount or number): Author reward in vesting shares.
            author_hive (Amount or number): Author reward in liquid HIVE.
            author_hbd (Amount or number): Author reward in HBD.

        Returns:
            None
        """
        self.reward_timestamps.append(timestamp)
        self.curation_rewards.append(curation_reward)
        self.author_rewards.append({"vests": author_vests, "hive": author_hive, "hbd": author_hbd})

    def update_out_vote(self, timestamp: Union[datetime, int], weight: int) -> None:
        """
        Record an outbound vote event.

        Appends the vote timestamp and weight to the snapshot's outbound-vote arrays for later voting-power and history calculations.

        Parameters:
            timestamp (datetime | int): Time of the vote (timezone-aware datetime or block timestamp).
            weight (int): Vote weight as an integer (e.g., range -10000..10000).
        """
        self.out_vote_timestamp.append(timestamp)
        self.out_vote_weight.append(weight)

    def update_in_vote(
        self, timestamp: Union[datetime, int], weight: int, op: Dict[str, Any]
    ) -> None:
        """
        Record an incoming vote event by parsing a Vote operation and appending its data to the snapshot's in-vote arrays.

        Parses the provided operation into a Vote, refreshes it, and on success appends:
        - timestamp to in_vote_timestamp
        - weight to in_vote_weight
        - the voter's reputation to in_vote_rep (as int)
        - the vote's rshares to in_vote_rshares (as int)

        Parameters:
            timestamp: datetime
                Time of the vote event (should be timezone-aware).
            weight: int
                Vote weight as provided by the operation.
            op:
                Raw operation data used to construct the Vote.

        Notes:
            If the operation cannot be parsed into a valid Vote, the function prints an error message and returns without modifying the snapshot.
        """
        v = Vote(op)
        try:
            v.refresh()
            self.in_vote_timestamp.append(timestamp)
            self.in_vote_weight.append(weight)
            self.in_vote_rep.append(int(v["reputation"]))
            self.in_vote_rshares.append(int(v["rshares"]))
        except Exception:
            print("Could not find: %s" % v)
            return

    def update(
        self,
        timestamp: datetime,
        own: Union[Amount, float],
        delegated_in: Optional[Union[Dict[str, Any], int]] = None,
        delegated_out: Optional[Union[Dict[str, Any], int]] = None,
        hive: Union[Amount, float] = 0,
        hbd: Union[Amount, float] = 0,
    ) -> None:
        """
        Update internal time-series state with a new account event.

        Appends two timeline entries: a one-second "pre-tick" preserving the previous state at timestamp - 1s, then a tick at timestamp with updated balances and delegation maps. This updates the snapshot's arrays for timestamps, own vests, liquid HIVE/HBD balances, and incoming/outgoing vesting delegations.

        Parameters:
            timestamp (datetime): Event time (timezone-aware). A "pre-tick" is created at timestamp - 1s.
            own (Amount or float): Change in the account's own vesting shares (vests) to apply at the tick.
            delegated_in (dict or None): Incoming delegation change of form {"account": name, "amount": vests} or None.
                If amount == 0 the delegation entry for that account is removed.
            delegated_out (dict or None): Outgoing delegation change. Typical forms:
                - {"account": name, "amount": vests} to add/update a non-zero outgoing delegation.
                - {"account": None, "amount": vests} indicates a return_vesting_delegation; the matching outgoing entry with the same amount is removed.
                If omitted or empty, outgoing delegations are unchanged.
            hive (Amount or float): Change in liquid HIVE to apply at the tick.
            hbd (Amount or float): Change in liquid HBD to apply at the tick.

        Returns:
            None
        """
        self.timestamps.append(timestamp - timedelta(seconds=1))
        self.own_vests.append(self.own_vests[-1])
        self.own_hive.append(self.own_hive[-1])
        self.own_hbd.append(self.own_hbd[-1])
        self.delegated_vests_in.append(self.delegated_vests_in[-1])
        self.delegated_vests_out.append(self.delegated_vests_out[-1])

        self.timestamps.append(timestamp)
        self.own_vests.append(self.own_vests[-1] + own)
        self.own_hive.append(self.own_hive[-1] + hive)
        self.own_hbd.append(self.own_hbd[-1] + hbd)

        new_deleg = dict(self.delegated_vests_in[-1])
        if delegated_in is not None and delegated_in:
            if delegated_in["amount"] == 0:
                del new_deleg[delegated_in["account"]]
            else:
                new_deleg[delegated_in["account"]] = delegated_in["amount"]
        self.delegated_vests_in.append(new_deleg)

        new_deleg = dict(self.delegated_vests_out[-1])
        if delegated_out is not None and delegated_out:
            if delegated_out["account"] is None:
                # return_vesting_delegation
                for delegatee in new_deleg:
                    if new_deleg[delegatee]["amount"] == delegated_out["amount"]:
                        del new_deleg[delegatee]
                        break

            elif delegated_out["amount"] != 0:
                # new or updated non-zero delegation
                new_deleg[delegated_out["account"]] = delegated_out["amount"]
                # TODO
                # skip undelegations here, wait for 'return_vesting_delegation'
                # del new_deleg[delegated_out['account']]

        self.delegated_vests_out.append(new_deleg)

    def build(
        self,
        only_ops: Optional[List[str]] = None,
        exclude_ops: Optional[List[str]] = None,
        enable_rewards: bool = False,
        enable_out_votes: bool = False,
        enable_in_votes: bool = False,
    ) -> None:
        """Builds the account history based on all account operations

        :param array only_ops: Limit generator by these
            operations (*optional*)
        :param array exclude_ops: Exclude these operations from
            generator (*optional*)

        """
        if only_ops is None:
            only_ops = []
        if exclude_ops is None:
            exclude_ops = []
        if len(self.timestamps) > 0:
            start_timestamp = self.timestamps[-1]
        else:
            start_timestamp = None
        for op in sorted(self, key=lambda k: k["timestamp"]):
            ts = parse_time(op["timestamp"])
            if start_timestamp is not None:
                # Convert start_timestamp to datetime if it's time or date
                if isinstance(start_timestamp, time):
                    start_timestamp_dt = datetime.combine(datetime.now().date(), start_timestamp)
                elif isinstance(start_timestamp, date):
                    start_timestamp_dt = datetime.combine(start_timestamp, time.min)
                else:
                    start_timestamp_dt = start_timestamp
                if start_timestamp_dt > ts:
                    continue
            if op["type"] in exclude_ops:
                continue
            if len(only_ops) > 0 and op["type"] not in only_ops:
                continue
            self.ops_statistics[op["type"]] += 1
            self.parse_op(
                op,
                only_ops=only_ops,
                enable_rewards=enable_rewards,
                enable_out_votes=enable_out_votes,
                enable_in_votes=enable_in_votes,
            )

    def parse_op(
        self,
        op: Dict[str, Any],
        only_ops: Optional[List[str]] = None,
        enable_rewards: bool = False,
        enable_out_votes: bool = False,
        enable_in_votes: bool = False,
    ) -> None:
        """
        Parse a single account-history operation and update the snapshot's internal state.

        Parses the provided operation dictionary `op` (expects keys like "type" and "timestamp"), converts amounts using the snapshot's blockchain instance, and applies its effect to the snapshot by calling the appropriate update methods (e.g. update, update_rewards, update_out_vote, update_in_vote). Handles Hive-specific operations such as account creation, transfers, vesting/delegation, reward payouts, order fills, conversions, interest, votes, and hardfork-related adjustments. Many other operation types are intentionally ignored.

        Parameters:
            op (dict): A single operation entry from account history. Must contain a parsable "timestamp" and a "type" key; other required keys depend on the operation type.
            only_ops (list): If non-empty, treat operations listed here as affecting balances/votes even when reward/vote-collection flags are disabled.
            enable_rewards (bool): When True, record reward aggregates via update_rewards in addition to applying balance changes.
            enable_out_votes (bool): When True, record outbound votes (this account as voter) via update_out_vote.
            enable_in_votes (bool): When True, record inbound votes (this account as author/recipient) via update_in_vote.

        Returns:
            None
        """
        if only_ops is None:
            only_ops = []
        ts = parse_time(op["timestamp"])

        if op["type"] == "account_create":
            fee_hive = Amount(op["fee"], blockchain_instance=self.blockchain).amount
            fee_vests = self.blockchain.hp_to_vests(
                Amount(op["fee"], blockchain_instance=self.blockchain).amount, timestamp=ts
            )
            if op["new_account_name"] == self.account["name"]:
                self.update(ts, fee_vests, 0, 0)
                return
            if op["creator"] == self.account["name"]:
                self.update(ts, 0, 0, 0, fee_hive * (-1), 0)
                return

        if op["type"] == "account_create_with_delegation":
            fee_hive = Amount(op["fee"], blockchain_instance=self.blockchain).amount
            fee_vests = self.blockchain.hp_to_vests(
                Amount(op["fee"], blockchain_instance=self.blockchain).amount, timestamp=ts
            )
            if op["new_account_name"] == self.account["name"]:
                if Amount(op["delegation"], blockchain_instance=self.blockchain).amount > 0:
                    delegation = {
                        "account": op["creator"],
                        "amount": Amount(op["delegation"], blockchain_instance=self.blockchain),
                    }
                else:
                    delegation = None
                self.update(ts, fee_vests, delegation, 0)
                return

            if op["creator"] == self.account["name"]:
                delegation = {
                    "account": op["new_account_name"],
                    "amount": Amount(op["delegation"], blockchain_instance=self.blockchain),
                }
                self.update(ts, 0, 0, delegation, fee_hive * (-1), 0)
                return

        elif op["type"] == "delegate_vesting_shares":
            vests = Amount(op["vesting_shares"], blockchain_instance=self.blockchain)
            if op["delegator"] == self.account["name"]:
                delegation = {"account": op["delegatee"], "amount": vests}
                self.update(ts, 0, 0, delegation)
                return
            if op["delegatee"] == self.account["name"]:
                delegation = {"account": op["delegator"], "amount": vests}
                self.update(ts, 0, delegation, 0)
                return

        elif op["type"] == "transfer":
            amount = Amount(op["amount"], blockchain_instance=self.blockchain)
            if op["from"] == self.account["name"]:
                if amount.symbol == self.blockchain.blockchain_symbol:
                    self.update(ts, 0, None, None, hive=amount * (-1), hbd=0)
                elif amount.symbol == self.blockchain.backed_token_symbol:
                    self.update(ts, 0, None, None, hive=0, hbd=amount * (-1))
            if op["to"] == self.account["name"]:
                if amount.symbol == self.blockchain.blockchain_symbol:
                    self.update(ts, 0, None, None, hive=amount, hbd=0)
                elif amount.symbol == self.blockchain.backed_token_symbol:
                    self.update(ts, 0, None, None, hive=0, hbd=amount)
            return

        elif op["type"] == "fill_order":
            current_pays = Amount(op["current_pays"], blockchain_instance=self.blockchain)
            open_pays = Amount(op["open_pays"], blockchain_instance=self.blockchain)
            if op["current_owner"] == self.account["name"]:
                if current_pays.symbol == self.blockchain.token_symbol:
                    self.update(ts, 0, None, None, hive=current_pays * (-1), hbd=open_pays)
                elif current_pays.symbol == self.blockchain.backed_token_symbol:
                    self.update(ts, 0, None, None, hive=open_pays, hbd=current_pays * (-1))
            if op["open_owner"] == self.account["name"]:
                if current_pays.symbol == self.blockchain.token_symbol:
                    self.update(ts, 0, None, None, hive=current_pays, hbd=open_pays * (-1))
                elif current_pays.symbol == self.blockchain.backed_token_symbol:
                    self.update(ts, 0, None, None, hive=open_pays * (-1), hbd=current_pays)
            return

        elif op["type"] == "transfer_to_vesting":
            hive_amt = Amount(op["amount"], blockchain_instance=self.blockchain)
            vests = self.blockchain.hp_to_vests(hive_amt.amount, timestamp=ts)
            if op["from"] == self.account["name"] and op["to"] == self.account["name"]:
                self.update(
                    ts, vests, 0, 0, hive_amt * (-1), 0
                )  # power up from and to given account
            elif op["from"] != self.account["name"] and op["to"] == self.account["name"]:
                self.update(ts, vests, 0, 0, 0, 0)  # power up from another account
            else:  # op['from'] == self.account["name"] and op['to'] != self.account["name"]
                self.update(ts, 0, 0, 0, hive_amt * (-1), 0)  # power up to another account
            return

        elif op["type"] == "fill_vesting_withdraw":
            vests = Amount(op["withdrawn"], blockchain_instance=self.blockchain)
            self.update(ts, vests * (-1), None, None, hive=0, hbd=0)
            return

        elif op["type"] == "return_vesting_delegation":
            delegation = {
                "account": None,
                "amount": Amount(op["vesting_shares"], blockchain_instance=self.blockchain),
            }
            self.update(ts, 0, None, delegated_out=delegation)
            return

        elif op["type"] == "claim_reward_balance":
            vests = Amount(op["reward_vests"], blockchain_instance=self.blockchain)
            hive = Amount(op["reward_hive"], blockchain_instance=self.blockchain)
            hbd = Amount(op["reward_hbd"], blockchain_instance=self.blockchain)
            self.update(ts, vests, None, None, hive=hive, hbd=hbd)
            return

        elif op["type"] == "curation_reward":
            if "curation_reward" in only_ops or enable_rewards:
                vests = Amount(op["reward"], blockchain_instance=self.blockchain)
            if "curation_reward" in only_ops:
                self.update(ts, vests, None, None, hive=0, hbd=0)
            if enable_rewards:
                self.update_rewards(ts, vests, 0, 0, 0)
            return

        elif op["type"] == "author_reward":
            if "author_reward" in only_ops or enable_rewards:
                vests = Amount(op["vesting_payout"], blockchain_instance=self.blockchain)
                hive = Amount(op["hive_payout"], blockchain_instance=self.blockchain)
                hbd = Amount(op["hbd_payout"], blockchain_instance=self.blockchain)
            if "author_reward" in only_ops:
                self.update(ts, vests, None, None, hive=hive, hbd=hbd)
            if enable_rewards:
                self.update_rewards(ts, 0, vests, hive, hbd)
            return

        elif op["type"] == "producer_reward":
            vests = Amount(op["vesting_shares"], blockchain_instance=self.blockchain)
            self.update(ts, vests, None, None, hive=0, hbd=0)
            return

        elif op["type"] == "comment_benefactor_reward":
            if op["benefactor"] == self.account["name"]:
                if "reward" in op:
                    vests = Amount(op["reward"], blockchain_instance=self.blockchain)
                    self.update(ts, vests, None, None, hive=0, hbd=0)
                else:
                    vests = Amount(op["vesting_payout"], blockchain_instance=self.blockchain)
                    hive = Amount(op["hive_payout"], blockchain_instance=self.blockchain)
                    hbd = Amount(op["hbd_payout"], blockchain_instance=self.blockchain)
                    self.update(ts, vests, None, None, hive=hive, hbd=hbd)
                return
            else:
                return

        elif op["type"] == "fill_convert_request":
            amount_in = Amount(op["amount_in"], blockchain_instance=self.blockchain)
            amount_out = Amount(op["amount_out"], blockchain_instance=self.blockchain)
            if op["owner"] == self.account["name"]:
                self.update(ts, 0, None, None, hive=amount_out, hbd=amount_in * (-1))
            return

        elif op["type"] == "interest":
            interest = Amount(op["interest"], blockchain_instance=self.blockchain)
            self.update(ts, 0, None, None, hive=0, hbd=interest)
            return

        elif op["type"] == "vote":
            if "vote" in only_ops or enable_out_votes:
                weight = int(op["weight"])
                if op["voter"] == self.account["name"]:
                    self.update_out_vote(ts, weight)
            if "vote" in only_ops or enable_in_votes and op["author"] == self.account["name"]:
                weight = int(op["weight"])
                self.update_in_vote(ts, weight, op)
            return

        elif op["type"] == "hardfork_hive":
            vests = Amount(op["vests_converted"])
            hbd = Amount(op["hbd_transferred"])
            hive = Amount(op["hive_transferred"])
            self.update(ts, vests * (-1), None, None, hive=hive * (-1), hbd=hbd * (-1))

        elif op["type"] in [
            "comment",
            "feed_publish",
            "shutdown_witness",
            "account_witness_vote",
            "witness_update",
            "custom_json",
            "limit_order_create",
            "account_update",
            "account_witness_proxy",
            "limit_order_cancel",
            "comment_options",
            "delete_comment",
            "interest",
            "recover_account",
            "pow",
            "fill_convert_request",
            "convert",
            "request_account_recovery",
            "update_proposal_votes",
        ]:
            return

    def build_sp_arrays(self) -> None:
        """
        Build timelines of own and effective Hive Power (HP) for each stored timestamp.

        For every timestamp in the snapshot, convert the account's own vesting shares and the
        sum of delegated-in/out vesting shares to Hive Power via the blockchain's
        `vests_to_hp` conversion and populate:
        - self.own_sp: HP equivalent of the account's own vesting shares at each timestamp.
        - self.eff_sp: effective HP = own HP + HP delegated in - HP delegated out at each timestamp.

        This method mutates self.own_sp and self.eff_sp in-place and relies on
        self.timestamps, self.own_vests, self.delegated_vests_in, self.delegated_vests_out,
        and self.blockchain.vests_to_hp(timestamp=...).
        """
        self.own_sp = []
        self.eff_sp = []
        for ts, own, din, dout in zip(
            self.timestamps, self.own_vests, self.delegated_vests_in, self.delegated_vests_out
        ):
            sum_in = sum([din[key].amount for key in din])
            sum_out = sum([dout[key].amount for key in dout])
            sp_in = self.blockchain.vests_to_hp(sum_in, timestamp=ts)
            sp_out = self.blockchain.vests_to_hp(sum_out, timestamp=ts)
            sp_own = self.blockchain.vests_to_hp(own, timestamp=ts)

            sp_eff = sp_own + sp_in - sp_out
            self.own_sp.append(sp_own)
            self.eff_sp.append(sp_eff)

    def build_rep_arrays(self) -> None:
        """Build reputation arrays"""
        self.rep_timestamp = [self.timestamps[1]]
        self.rep = [reputation_to_score(0)]
        current_reputation = 0
        for ts, rshares, rep in zip(self.in_vote_timestamp, self.in_vote_rshares, self.in_vote_rep):
            if rep > 0:
                if rshares > 0 or (rshares < 0 and rep > current_reputation):
                    current_reputation += rshares >> 6
            self.rep.append(reputation_to_score(current_reputation))
            self.rep_timestamp.append(ts)

    def build_vp_arrays(self) -> None:
        """
        Build timelines for upvote and downvote voting power.

        Populates the following instance arrays with parallel timestamps and voting-power values:
        - self.vp_timestamp, self.vp: upvoting power timeline
        - self.downvote_vp_timestamp, self.downvote_vp: downvoting power timeline

        The method iterates over recorded outgoing votes (self.out_vote_timestamp / self.out_vote_weight),
        applies Hive vote-regeneration rules (using HIVE_VOTE_REGENERATION_SECONDS and HIVE_100_PERCENT),
        accounts for the HF_21 downvote timing change, and models vote drains via the blockchain's
        _vote/resulting calculation and the account's manabar recharge intervals (account.get_manabar_recharge_timedelta).
        Values are stored as integer percentage units where HIVE_100_PERCENT (typically 10000) represents 100.00%.

        Side effects:
        - Modifies self.vp_timestamp, self.vp, self.downvote_vp_timestamp, and self.downvote_vp in place.
        """
        self.vp_timestamp = [self.timestamps[1]]
        self.vp = [HIVE_100_PERCENT]
        HF_21 = datetime(2019, 8, 27, 15, tzinfo=timezone.utc)
        # Ensure timestamps[1] is datetime for comparison
        ts1 = self.timestamps[1]
        if isinstance(ts1, time):
            ts1 = datetime.combine(datetime.now().date(), ts1)
        elif isinstance(ts1, date):
            ts1 = datetime.combine(ts1, time.min)
        if ts1 is not None and ts1 > HF_21:
            self.downvote_vp_timestamp = [self.timestamps[1]]
        else:
            self.downvote_vp_timestamp = [HF_21]
        self.downvote_vp = [HIVE_100_PERCENT]

        for ts, weight in zip(self.out_vote_timestamp, self.out_vote_weight):
            regenerated_vp = 0
            if ts > HF_21 and weight < 0:
                self.downvote_vp.append(self.downvote_vp[-1])
                if self.downvote_vp[-1] < HIVE_100_PERCENT:
                    regenerated_vp = (
                        ((ts - self.downvote_vp_timestamp[-1]).total_seconds())
                        * HIVE_100_PERCENT
                        / HIVE_VOTE_REGENERATION_SECONDS
                    )
                    self.downvote_vp[-1] += int(regenerated_vp)

                if self.downvote_vp[-1] > HIVE_100_PERCENT:
                    self.downvote_vp[-1] = HIVE_100_PERCENT
                    recharge_time = self.account.get_manabar_recharge_timedelta(
                        {"current_mana_pct": self.downvote_vp[-2] / 100}
                    )
                    # Add full downvote VP once fully charged
                    last_ts = self.downvote_vp_timestamp[-1]
                    if isinstance(last_ts, time):
                        last_ts = datetime.combine(datetime.now().date(), last_ts)
                    elif isinstance(last_ts, date):
                        last_ts = datetime.combine(last_ts, time.min)
                    if last_ts is not None:
                        self.downvote_vp_timestamp.append(last_ts + recharge_time)
                        self.downvote_vp.append(HIVE_100_PERCENT)

                # Add charged downvote VP just before new Vote
                self.downvote_vp_timestamp.append(ts - timedelta(seconds=1))
                self.downvote_vp.append(
                    min([HIVE_100_PERCENT, self.downvote_vp[-1] + regenerated_vp])
                )

                self.downvote_vp[-1] -= (
                    self.blockchain._calc_resulting_vote(HIVE_100_PERCENT, weight) * 4
                )
                # Downvote mana pool is 1/4th of the upvote mana pool, so it gets drained 4 times as quick
                if self.downvote_vp[-1] < 0:
                    # There's most likely a better solution to this that what I did here
                    self.vp.append(self.vp[-1])

                    if self.vp[-1] < HIVE_100_PERCENT:
                        regenerated_vp = (
                            ((ts - self.vp_timestamp[-1]).total_seconds())
                            * HIVE_100_PERCENT
                            / HIVE_VOTE_REGENERATION_SECONDS
                        )
                        self.vp[-1] += int(regenerated_vp)

                    if self.vp[-1] > HIVE_100_PERCENT:
                        self.vp[-1] = HIVE_100_PERCENT
                        recharge_time = self.account.get_manabar_recharge_timedelta(
                            {"current_mana_pct": self.vp[-2] / 100}
                        )
                        # Add full VP once fully charged
                        last_vp_ts = self.vp_timestamp[-1]
                        if isinstance(last_vp_ts, time):
                            last_vp_ts = datetime.combine(datetime.now().date(), last_vp_ts)
                        elif isinstance(last_vp_ts, date):
                            last_vp_ts = datetime.combine(last_vp_ts, time.min)
                        if last_vp_ts is not None:
                            self.vp_timestamp.append(last_vp_ts + recharge_time)
                            self.vp.append(HIVE_100_PERCENT)
                    if self.vp[-1] == HIVE_100_PERCENT and ts - self.vp_timestamp[-1] > timedelta(
                        seconds=1
                    ):
                        # Add charged VP just before new Vote
                        self.vp_timestamp.append(ts - timedelta(seconds=1))
                        self.vp.append(min([HIVE_100_PERCENT, self.vp[-1] + regenerated_vp]))
                    self.vp[-1] += self.downvote_vp[-1] / 4
                    if self.vp[-1] < 0:
                        self.vp[-1] = 0

                    self.vp_timestamp.append(ts)
                    self.downvote_vp[-1] = 0
                self.downvote_vp_timestamp.append(ts)

            else:
                self.vp.append(self.vp[-1])

                if self.vp[-1] < HIVE_100_PERCENT:
                    regenerated_vp = (
                        ((ts - self.vp_timestamp[-1]).total_seconds())
                        * HIVE_100_PERCENT
                        / HIVE_VOTE_REGENERATION_SECONDS
                    )
                    self.vp[-1] += int(regenerated_vp)

                if self.vp[-1] > HIVE_100_PERCENT:
                    self.vp[-1] = HIVE_100_PERCENT
                    recharge_time = self.account.get_manabar_recharge_timedelta(
                        {"current_mana_pct": self.vp[-2] / 100}
                    )
                    # Add full VP once fully charged
                    last_vp_ts = self.vp_timestamp[-1]
                    if isinstance(last_vp_ts, time):
                        last_vp_ts = datetime.combine(datetime.now().date(), last_vp_ts)
                    elif isinstance(last_vp_ts, date):
                        last_vp_ts = datetime.combine(last_vp_ts, time.min)
                    if last_vp_ts is not None:
                        self.vp_timestamp.append(last_vp_ts + recharge_time)
                        self.vp.append(HIVE_100_PERCENT)
                if self.vp[-1] == HIVE_100_PERCENT and ts - self.vp_timestamp[-1] > timedelta(
                    seconds=1
                ):
                    # Add charged VP just before new Vote
                    self.vp_timestamp.append(ts - timedelta(seconds=1))
                    self.vp.append(min([HIVE_100_PERCENT, self.vp[-1] + regenerated_vp]))
                self.vp[-1] -= self.blockchain._calc_resulting_vote(self.vp[-1], weight)
                if self.vp[-1] < 0:
                    self.vp[-1] = 0

                self.vp_timestamp.append(ts)

        if self.account.get_voting_power() == 100:
            self.vp.append(10000)
            recharge_time = self.account.get_manabar_recharge_timedelta(
                {"current_mana_pct": self.vp[-2] / 100}
            )
            last_vp_ts = self.vp_timestamp[-1]
            if isinstance(last_vp_ts, time):
                last_vp_ts = datetime.combine(datetime.now().date(), last_vp_ts)
            elif isinstance(last_vp_ts, date):
                last_vp_ts = datetime.combine(last_vp_ts, time.min)
            if last_vp_ts is not None:
                self.vp_timestamp.append(last_vp_ts + recharge_time)

        if self.account.get_downvoting_power() == 100:
            self.downvote_vp.append(10000)
            recharge_time = self.account.get_manabar_recharge_timedelta(
                {"current_mana_pct": self.downvote_vp[-2] / 100}
            )
            last_downvote_ts = self.downvote_vp_timestamp[-1]
            if isinstance(last_downvote_ts, time):
                last_downvote_ts = datetime.combine(datetime.now().date(), last_downvote_ts)
            elif isinstance(last_downvote_ts, date):
                last_downvote_ts = datetime.combine(last_downvote_ts, time.min)
            if last_downvote_ts is not None:
                self.downvote_vp_timestamp.append(last_downvote_ts + recharge_time)

        self.vp.append(self.account.get_voting_power() * 100)
        self.downvote_vp.append(self.account.get_downvoting_power() * 100)
        self.downvote_vp_timestamp.append(datetime.now(timezone.utc))
        self.vp_timestamp.append(datetime.now(timezone.utc))

    def build_curation_arrays(
        self, end_date: Optional[Union[datetime, date, time]] = None, sum_days: int = 7
    ) -> None:
        """
        Compute curation-per-1000-HP time series and store them in
        self.curation_per_1000_HP_timestamp and self.curation_per_1000_HP.

        The method walks through recorded reward timestamps and curation rewards, converts
        each curation reward (vests) to HP using the blockchain conversion, and divides
        that reward by the effective stake (sp_eff) at the reward time to produce a
        "curation per 1000 HP" value. Values are aggregated into contiguous windows of
        length `sum_days`. Each window's aggregate is appended to
        self.curation_per_1000_HP with the corresponding window end timestamp in
        self.curation_per_1000_HP_timestamp.

        Parameters:
            end_date (datetime.datetime | None): End-boundary for the first aggregation
                window. If None, it is set to the last reward timestamp minus the total
                span of full `sum_days` windows that fit into the reward history.
            sum_days (int): Window length in days for aggregation. Must be > 0.

        Raises:
            ValueError: If sum_days <= 0.

        Notes:
            - Uses self.blockchain.vests_to_hp(vests, timestamp=ts) to convert vests to HP.
            - Uses self.get_data(timestamp=ts, index=index) to obtain the effective stake
              (`sp_eff`) and to advance a cached index for efficient lookups.
            - The per-window aggregation normalizes values to a "per 1000 HP" basis and
              scales them by (7 / sum_days) so the resulting numbers are comparable to a
              7-day baseline.
        """
        self.curation_per_1000_HP_timestamp = []
        self.curation_per_1000_HP = []
        if sum_days <= 0:
            raise ValueError("sum_days must be greater than 0")
        index = 0
        curation_sum = 0
        days = (self.reward_timestamps[-1] - self.reward_timestamps[0]).days // sum_days * sum_days
        if end_date is None:
            end_date = self.reward_timestamps[-1] - timedelta(days=days)
        for ts, vests in zip(self.reward_timestamps, self.curation_rewards):
            if vests == 0:
                continue
            sp = self.blockchain.vests_to_hp(vests, timestamp=ts)
            data = self.get_data(timestamp=ts, index=index)
            index = data["index"]
            if "sp_eff" in data and data["sp_eff"] > 0:
                curation_1k_sp = sp / data["sp_eff"] * 1000 / sum_days * 7
            else:
                curation_1k_sp = 0
            if ts < end_date:
                curation_sum += curation_1k_sp
            else:
                self.curation_per_1000_HP_timestamp.append(end_date)
                self.curation_per_1000_HP.append(curation_sum)
                # Ensure end_date is a datetime for arithmetic
                if isinstance(end_date, datetime):
                    end_date = end_date + timedelta(days=sum_days)
                elif isinstance(end_date, date):
                    end_date = datetime.combine(end_date, time.min, timezone.utc) + timedelta(
                        days=sum_days
                    )
                else:  # time object
                    end_date = datetime.combine(date.today(), end_date, timezone.utc) + timedelta(
                        days=sum_days
                    )
                curation_sum = 0

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        return "<{} {}>".format(self.__class__.__name__, str(self.account["name"]))
