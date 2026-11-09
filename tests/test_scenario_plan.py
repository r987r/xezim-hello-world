"""SCN-1 tests: scenario plans express intent, never observed RTL results."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

from dv.common.scenario import Scenario, ScenarioError, canonical_json, resolve_scenario

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'config/scenarios/dma-roundtrip.json'


class ScenarioPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = yaml.safe_load((ROOT / 'config/soc.yaml').read_text())

    def setUp(self):
        self.spec = json.loads(EXAMPLE.read_text())

    def action(self, name):
        return next(a for a in self.spec['actions'] if a['action_instance_id'] == name)

    def resolve(self):
        return resolve_scenario(self.spec, self.cfg, source_revision='a' * 40)


    def test_event_emit_wait_is_source_selected_and_causally_ordered(self):
        source = copy.deepcopy(self.spec)
        source["actions"].extend([
            {"action_instance_id": "queue_emit", "kind": "event.emit",
             "actor": "cpu0", "phase": "run",
             "args": {"queue": "accelerator_mailbox", "token": "dma_done"},
             "depends_on": ["copy_to_ddr"]},
            {"action_instance_id": "queue_wait", "kind": "event.wait",
             "actor": "cpu0", "phase": "run",
             "args": {"queue": "accelerator_mailbox", "token": "dma_done"},
             "depends_on": ["queue_emit"]},
        ])
        plan = resolve_scenario(source, self.cfg, source_revision='a' * 40)
        kinds = {a["action_instance_id"]: a for a in plan["actions"]}
        self.assertEqual(kinds["queue_emit"]["kind"], "event.emit")
        self.assertEqual(kinds["queue_wait"]["depends_on"], ["queue_emit"])
        self.assertIsNone(plan["execution_evidence"])

    def test_event_wait_without_producer_or_causal_dependency_fails_closed(self):
        base = {"action_instance_id": "queue_wait", "kind": "event.wait",
                "actor": "cpu0", "phase": "run",
                "args": {"queue": "mailbox", "token": "completion"},
                "depends_on": ["copy_to_ddr"]}
        self.spec["actions"].append(base)
        with self.assertRaisesRegex(ScenarioError, "causal emit"):
            self.resolve()
        self.spec["actions"].append({
            "action_instance_id": "queue_emit", "kind": "event.emit",
            "actor": "cpu0", "phase": "run",
            "args": {"queue": "mailbox", "token": "completion"},
            "depends_on": ["copy_to_ddr"],
        })
        with self.assertRaisesRegex(ScenarioError, "causal emit"):
            self.resolve()
        base["depends_on"].append("queue_emit")
        self.resolve()
        self.spec["actions"].append({
            "action_instance_id": "queue_duplicate", "kind": "event.emit",
            "actor": "cpu0", "phase": "run",
            "args": {"queue": "mailbox", "token": "completion"},
            "depends_on": ["copy_to_ddr"],
        })
        with self.assertRaisesRegex(ScenarioError, "duplicate event token"):
            self.resolve()

    def test_configured_physical_regions_and_intent_only(self):
        plan = self.resolve()
        memory = {a['buffer']: a for a in plan['allocations']}
        self.assertEqual(memory['source']['phys'], 0x10002000)
        self.assertEqual(memory['ddr']['phys'], 0x140000100)
        self.assertEqual(memory['return']['phys'] % 64, 0)
        self.assertTrue(all(a['state'] == 'planned_only' for a in memory.values()))
        self.assertEqual(plan['kind'], 'soc_scenario_intent_only')
        self.assertIsNone(plan['execution_evidence'])
        self.assertEqual(plan['provenance']['source_revision'], 'a' * 40)
        self.assertTrue(all(a['expected_result_id'] for a in plan['actions']))

    def test_byte_for_byte_replay_and_authoring_order_independence(self):
        original = self.resolve()
        self.assertEqual(canonical_json(original), canonical_json(self.resolve()))
        self.assertEqual(canonical_json(original),
                         canonical_json(json.loads(canonical_json(original))))
        shuffled = copy.deepcopy(self.spec)
        shuffled['actions'].reverse()
        alternate = resolve_scenario(shuffled, self.cfg, source_revision='a' * 40)
        self.assertEqual(original['actions'], alternate['actions'])
        self.assertEqual(original['allocations'], alternate['allocations'])
        self.assertNotEqual(original['provenance']['spec_sha256'],
                            alternate['provenance']['spec_sha256'])

    def test_seeded_choices_stable_and_changeable(self):
        lengths = set()
        for seed in range(12):
            self.spec['seed'] = seed
            p = self.resolve()
            self.assertEqual(p, self.resolve())
            size = next(a['args']['size'] for a in p['actions']
                        if a['action_instance_id'] == 'alloc_source')
            lengths.add(size)
        self.assertGreater(len(lengths), 1)
        self.assertTrue(lengths <= {64, 128, 256})

    def test_python_builder_produces_same_plan_as_json_authoring(self):
        model = Scenario('directed', ('cpu0',), 5)
        model.add('alloc', 'memory.allocate', 'cpu0', 'init',
                  {'buffer': 'src', 'region': 'compute0.sram.payload',
                   'size': 64, 'alignment': 64})
        model.add('init', 'memory.initialize', 'cpu0', 'init',
                  {'buffer': 'src', 'length': 64,
                   'pattern': {'kind': 'constant', 'seed': 17},
                   'policy': 'strict'}, depends_on=('alloc',))
        self.assertEqual(resolve_scenario(model, self.cfg),
                         resolve_scenario(model.as_dict(), self.cfg))

    def test_parallel_independent_regions_preserve_actor_instances(self):
        extra = copy.deepcopy(self.action('alloc_ddr'))
        extra['action_instance_id'] = 'alloc_hbm'
        extra['args'].update(buffer='hbm', region='memory0.hbm0')
        self.spec['actions'].append(extra)
        plan = self.resolve()
        self.assertEqual(len(plan['actions']),
                         len({a['action_instance_id'] for a in plan['actions']}))
        self.assertNotIn('alloc_ddr',
                         next(a['depends_on'] for a in plan['actions']
                              if a['action_instance_id'] == 'alloc_hbm'))

    def test_rejects_unknown_kind_actor_phase_and_duplicate_ids(self):
        for field, bad, message in (
                ('kind', 'unsupported', 'unsupported action kind'),
                ('actor', 'unknown_actor', 'undeclared actor'),
                ('phase', 'unknown', 'unknown phase')):
            with self.subTest(field=field):
                self.setUp()
                self.action('copy_to_ddr')[field] = bad
                with self.assertRaisesRegex(ScenarioError, message):
                    self.resolve()
        self.setUp()
        self.spec['actions'].append(copy.deepcopy(self.action('copy_to_ddr')))
        with self.assertRaisesRegex(ScenarioError, 'duplicate action_instance_id'):
            self.resolve()

    def test_dependency_cycles_missing_deps_and_invalid_phase_edges(self):
        self.action('alloc_source')['depends_on'] = ['nonexistent']
        with self.assertRaisesRegex(ScenarioError, 'missing dependency'):
            self.resolve()
        self.setUp()
        self.action('alloc_source')['depends_on'] = ['alloc_ddr']
        self.action('alloc_ddr')['depends_on'] = ['alloc_source']
        with self.assertRaisesRegex(ScenarioError, 'cyclic'):
            self.resolve()
        self.setUp()
        self.action('init_source')['depends_on'] = ['check_return']
        with self.assertRaisesRegex(ScenarioError, 'phase backwards'):
            self.resolve()

    def test_unsatisfiable_random_choice(self):
        for invalid in ({"choose": []},
                        {"randint": {"min": 19, "max": 5}},
                        {"randint": {"min": 1, "max": 10, "step": 4}},
                        {"choose": [64], "surprise": True}):
            with self.subTest(invalid=invalid):
                self.setUp()
                self.action('alloc_source')['args']['size'] = invalid
                with self.assertRaises(ScenarioError):
                    self.resolve()

    def test_rejects_invalid_memory_regions_sizes_and_physical_addresses(self):
        for region, size, phys, match in (
                ('unknown.region', 64, None, 'unknown region'),
                ('memory0.ddr0', 1 << 20, None, 'modeled capacity exceeded'),
                ('memory0.ddr0', 64, 0x140000000,
                 'physical address disagrees')):
            with self.subTest(region=region):
                self.setUp()
                args = self.action('alloc_ddr')['args']
                args.update(region=region, size=size)
                if phys is not None:
                    args['phys'] = phys
                with self.assertRaisesRegex(ScenarioError, match):
                    self.resolve()

    def test_rejects_unordered_allocations_and_non_lifo_release(self):
        self.action('alloc_return')['depends_on'] = []
        with self.assertRaisesRegex(ScenarioError, 'unordered allocations'):
            self.resolve()
        self.setUp()
        self.action('release_source')['depends_on'] = ['copy_to_ddr']
        with self.assertRaises(ScenarioError):
            self.resolve()

    def test_release_must_wait_for_all_consumers_and_quiescence(self):
        self.action('release_ddr')['args']['consumers_quiesced'] = False
        with self.assertRaisesRegex(ScenarioError, 'quiescence'):
            self.resolve()
        self.setUp()
        self.action('release_return')['depends_on'] = ['alloc_return']
        with self.assertRaises(ScenarioError):
            self.resolve()

    def test_rejects_uninitialized_reads_and_unordered_writers(self):
        self.action('copy_to_ddr')['depends_on'] = ['alloc_source', 'alloc_ddr']
        with self.assertRaisesRegex(ScenarioError, 'uninitialized'):
            self.resolve()
        self.setUp()
        other = copy.deepcopy(self.action('init_source'))
        other['action_instance_id'] = 'init_again'
        other['depends_on'] = ['alloc_source']
        self.spec['actions'].append(other)
        with self.assertRaisesRegex(ScenarioError, 'unordered'):
            self.resolve()

    def test_rejects_cpu_direct_ddr_access(self):
        extra = copy.deepcopy(self.action('check_return'))
        extra['action_instance_id'] = 'cpu_checks_ddr'
        extra['actor'] = 'cpu0'
        extra['depends_on'] = ['copy_to_ddr']
        extra['args']['buffer'] = 'ddr'
        self.spec['actions'].append(extra)
        with self.assertRaisesRegex(ScenarioError, 'cannot directly'):
            self.resolve()

    def test_rejects_unexpected_fields_and_incorrect_sha(self):
        with self.assertRaisesRegex(ScenarioError, 'source_revision'):
            resolve_scenario(self.spec, self.cfg, source_revision='HEAD')
        self.action('alloc_source')['args']['unknown_attribute'] = 1
        with self.assertRaises(ScenarioError):
            self.resolve()

    def test_cli_produces_identical_machine_readable_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'scenario-plan.json'
            cmd = [sys.executable, str(ROOT / 'tools/scenario_plan.py'),
                   '--scenario', str(EXAMPLE), '--soc', str(ROOT / 'config/soc.yaml'),
                   '--out', str(out), '--source-revision', 'a' * 40]
            subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True)
            first = out.read_bytes()
            subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True)
            self.assertEqual(first, out.read_bytes())
            self.assertIsNone(json.loads(first)['execution_evidence'])


if __name__ == '__main__':
    unittest.main()
