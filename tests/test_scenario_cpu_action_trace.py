"""Fail-closed source-selected C action-stage evidence from accepted CPU AXI."""
import copy
import hashlib
import unittest

from tools.scenario_cpu_action_trace import verify, CpuActionTraceError
from tools.scenario_cpu_plan_witness import verify as verify_plan_sha

SHA = hashlib.sha256(b"selected SCN-C real CPU action plan").hexdigest()
WITNESS = 0x10003000
TRACE = WITNESS + 32
ACTIONS = [{"action_instance_id": name} for name in (
    "alloc_source", "alloc_ddr", "alloc_return", "init_source",
    "copy_out", "copy_back", "wait_idle", "check_return",
)]


def accepted(addr, value):
    lane = addr & 7
    return {
        "monitor": "compute0_local_data.cpu",
        "role": "initiator", "operation": "write",
        "status": "complete", "issues": [], "address": hex(addr),
        "expected_beats": 1, "request": {"size": "0x2", "len": "0x0"},
        "response": "0x0",
        "beats": [{"data": hex(value << (lane * 8)),
                   "strb": hex(0xf << lane), "last": "0x1"}],
    }


def trace():
    return [accepted(TRACE + i*8 + stage*4,
                     0xa7000000 | (i << 8) | (stage + 1))
            for i in range(len(ACTIONS)) for stage in range(2)]


def witness():
    raw = bytes.fromhex(SHA)
    return [accepted(WITNESS + i*4,
                     int.from_bytes(raw[i*4:i*4+4], "little")) for i in range(8)]


class CpuActionTraceTests(unittest.TestCase):
    def setUp(self):
        self.rows = trace()

    def test_all_16_real_cpu_issued_done_words_for_selected_eight_actions(self):
        proof = verify(SHA, TRACE, ACTIONS, self.rows)
        self.assertEqual(proof["accepted_writes"], 16)
        self.assertEqual(proof["checked_bytes"], 64)
        self.assertEqual(proof["action_ids"], [a["action_instance_id"] for a in ACTIONS])
        self.assertFalse(proof["hardware_completion_proven"])

    def test_sha_and_driver_trace_are_independent_adjacent_axi_windows(self):
        transactions = witness() + self.rows
        self.assertEqual(verify_plan_sha(SHA, WITNESS, transactions)["accepted_writes"], 8)
        self.assertEqual(verify(SHA, TRACE, ACTIONS, transactions)["accepted_writes"], 16)

    def test_missing_duplicate_failed_or_forged_driver_events_rejected(self):
        for name in ("missing", "duplicate", "failed_response", "wrong_bus",
                     "wrong_strobes", "bad_marker", "wrong_order", "wrong_actor",
                     "incomplete", "wrong_size", "bad_last", "failed_issue"):
            rows = copy.deepcopy(self.rows)
            if name == "missing":
                rows.pop()
            elif name == "duplicate":
                rows.append(rows[3])
            elif name == "failed_response":
                rows[1]["response"] = "0x2"
            elif name == "wrong_bus":
                rows[1]["monitor"] = "compute0_local_config.cpu"
            elif name == "wrong_strobes":
                rows[1]["beats"][0]["strb"] = "0xf"
            elif name == "bad_marker":
                rows[1]["beats"][0]["data"] = "0x0"
            elif name == "wrong_order":
                rows[2], rows[3] = rows[3], rows[2]
                # Order is defined by selected SRAM indices; swap the
                # actual data while keeping their physical store addresses.
                a = rows[2]["beats"][0]["data"]
                rows[2]["beats"][0]["data"] = rows[3]["beats"][0]["data"]
                rows[3]["beats"][0]["data"] = a
            elif name == "wrong_actor":
                rows[1]["role"] = "target"
            elif name == "incomplete":
                rows[1]["status"] = "incomplete"
            elif name == "wrong_size":
                rows[1]["request"]["size"] = "0x3"
            elif name == "bad_last":
                rows[1]["beats"][0]["last"] = "0x0"
            elif name == "failed_issue":
                rows[1]["issues"] = ["bus not retired"]
            with self.subTest(name=name), self.assertRaises(CpuActionTraceError):
                verify(SHA, TRACE, ACTIONS, rows)

    def test_rejects_missing_or_duplicate_selected_action_ids(self):
        with self.assertRaisesRegex(CpuActionTraceError, "duplicate"):
            verify(SHA, TRACE, [ACTIONS[0], ACTIONS[0]], self.rows)
        with self.assertRaises(CpuActionTraceError):
            verify("BAD", TRACE, ACTIONS, self.rows)
        with self.assertRaises(CpuActionTraceError):
            verify(SHA, TRACE + 1, ACTIONS, self.rows)


if __name__ == "__main__":
    unittest.main()
