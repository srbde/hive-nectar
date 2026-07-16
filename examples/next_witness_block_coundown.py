#!/usr/bin/python
import sys
from time import sleep

from nectar import Hive
from nectar.witness import Witness, WitnessesRankedByVote


def convert_block_diff_to_time_string(block_diff_est):
    next_block_s = int(block_diff_est) * 3
    next_block_min = next_block_s / 60
    next_block_h = next_block_min / 60
    next_block_d = next_block_h / 24
    time_diff_est = ""
    if next_block_d > 1:
        time_diff_est = "%.2f days" % next_block_d
    elif next_block_h > 1:
        time_diff_est = "%.2f hours" % next_block_h
    elif next_block_min > 1:
        time_diff_est = "%.2f minutes" % next_block_min
    else:
        time_diff_est = "%.2f seconds" % next_block_s
    return time_diff_est


if __name__ == "__main__":
    if len(sys.argv) != 2:
        witness = "thecrazygm"
    else:
        witness = sys.argv[1]
    hv = Hive()
    witness = Witness(witness, blockchain_instance=hv)

    witness_schedule = hv.get_witness_schedule()
    config = hv.get_config()
    if "VIRTUAL_SCHEDULE_LAP_LENGTH2" in config:
        lap_length = int(config["VIRTUAL_SCHEDULE_LAP_LENGTH2"])
    else:
        lap_length = int(config["HIVE_VIRTUAL_SCHEDULE_LAP_LENGTH2"])
    witnesses = WitnessesRankedByVote(limit=250, blockchain_instance=hv)
    vote_sum = witnesses.get_votes_sum()

    virtual_time_to_block_num = int(witness_schedule["num_scheduled_witnesses"]) / (
        lap_length / (vote_sum + 1)
    )
    while True:
        witness.refresh()
        witness_schedule = hv.get_witness_schedule(use_stored_data=False)

        witness_json = witness.json()
        virtual_diff = int(witness_json["virtual_scheduled_time"]) - int(
            witness_schedule["current_virtual_time"]
        )
        block_diff_est = virtual_diff * virtual_time_to_block_num

        time_diff_est = convert_block_diff_to_time_string(block_diff_est)

        sys.stdout.write(f"\r Next block for {witness['owner']} in {time_diff_est}")
        sleep(30)
