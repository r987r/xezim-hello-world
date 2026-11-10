"""Negative bit-lane tests for independently accepted CPU selected-plan witness."""
import copy
import hashlib
import unittest

from tools.scenario_cpu_plan_witness import verify, PlanWitnessError

SHA = hashlib.sha256(b"one resolved SCN plan").hexdigest()
BASE = 0x10003000


def transaction(i):
    addr = BASE + 4 * i
    lane = addr & 7
    data_word = int.from_bytes(bytes.fromhex(SHA)[4*i:4*i+4], "little")
    return {
        "monitor": "compute0_local_data.cpu",
        "role": "initiator", "operation": "write",
        "status": "complete", "issues": [], "address": hex(addr),
        "expected_beats": 1, "request": {"size": "0x2", "len": "0x0"},
        "response": "0x0",
        "beats": [{"data": hex(data_word << (lane*8)),
                   "strb": hex(0xf << lane), "last": "0x1"}]
    }


class PlanWitnessTests(unittest.TestCase):
    def setUp(self):
        self.rows = [transaction(i) for i in range(8)]

    def test_all_eight_actual_32bit_writes_reconstruct_full_256_bit_sha(self):
        proof = verify(SHA, BASE, self.rows)
        self.assertEqual(proof["checked_bytes"], 32)
        self.assertEqual(proof["accepted_writes"], 8)
        self.assertFalse(proof["scenario_action_completion_proven"])

    def test_missing_duplicate_or_foreign_sha_rejected(self):
        for altered in (self.rows[:-1], self.rows+[self.rows[0]],
                        [*self.rows[:-1],dict(self.rows[-1],response="0x2")]):
            with self.subTest(count=len(altered)),self.assertRaises(PlanWitnessError):
                verify(SHA, BASE, altered)
        with self.assertRaisesRegex(PlanWitnessError, "does not match"):
            verify("0"*64, BASE, self.rows)

    def test_byte_data_strobe_b_response_and_completion_fail_closed(self):
        for index, change in (
                (3, {"beats":[{"data":"0x0","strb":"0xf0","last":"0x1"}]}),
                (2, {"beats":[{"data":"0x0","strb":"0xf","last":"0x1"}]}),
                (1, {"status":"incomplete"}),
                (0, {"expected_beats":2}),
                (7, {"issues":["unexpected response"]}),
                (6, {"role":"target"})):
            altered=copy.deepcopy(self.rows)
            altered[index].update(change)
            with self.subTest(index=index,change=change),self.assertRaises(PlanWitnessError):
                verify(SHA,BASE,altered)

    def test_other_monitor_does_not_count(self):
        rows = copy.deepcopy(self.rows)
        rows[0]["monitor"] = "compute1_local_data.cpu"
        with self.assertRaisesRegex(PlanWitnessError, "missing"):
            verify(SHA, BASE, rows)


if __name__ == "__main__":
    unittest.main()
