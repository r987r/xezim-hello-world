import copy
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import bootgen
import regress
import sim_cocotb


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.config = regress.load_config(ROOT/'config/regression.yaml')

    def test_full_suite_covers_all_profiles_and_both_simulators(self):
        names = regress.expand(self.config, ['full'])
        self.assertEqual(set(names), {name for name, test in self.config['tests'].items()
                                      if not test.get('opt_in', False)})
        self.assertEqual(regress.expand(self.config, ['ddr-real']), ['chip-ddr4-real'])
        self.assertNotIn('chip-ddr4-real', names)
        self.assertTrue({'memory-full', 'memory-sparse', 'boot-relocated',
                         'supernoc', 'supernoc-negative', 'noc-xezim'} <= set(names))

    def test_opt_in_requires_explicit_suite_and_boolean(self):
        import tempfile
        for bad in ("boolean", "unlisted", "default"):
            cfg = copy.deepcopy(self.config)
            if bad == "boolean":
                cfg["tests"]["chip-ddr4-real"]["opt_in"] = "yes"
            elif bad == "unlisted":
                cfg["suites"]["ddr-real"] = []
            else:
                cfg["suites"]["full"].append("chip-ddr4-real")
            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / "regression.yaml"
                p.write_text(yaml.safe_dump(cfg))
                with self.assertRaises(ValueError):
                    regress.load_config(p)

    def test_suite_errors_fail_closed(self):
        self.config['suites']['loop'] = ['loop']
        with self.assertRaisesRegex(ValueError, 'cyclic'):
            regress.expand(self.config, ['loop'])
        with self.assertRaisesRegex(ValueError, 'unknown'):
            regress.expand(self.config, ['typo'])

    def test_schema_typos_and_uncovered_tests_rejected(self):
        for mutation in ('unknown-field', 'missing-test'):
            cfg = copy.deepcopy(self.config)
            if mutation == 'unknown-field':
                cfg['tests']['boot']['timout_s'] = 1
            else:
                cfg['suites']['diagnostics'].remove('cpu-fetch')
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp)/'regression.yaml'
                path.write_text(yaml.safe_dump(cfg))
                with self.assertRaises(ValueError):
                    regress.load_config(path)

    def test_scenario_source_is_explicit_and_matches_real_executor(self):
        self.assertEqual(self.config['tests']['chip-cpu-scenario']['flow_plan'],
                         'config/scenarios/cpu-bfm-ddr-roundtrip.json')
        self.assertEqual(self.config['tests']['chip-dma-scenario']['flow_plan'],
                         'config/scenarios/cpu-bfm-ddr-roundtrip.json')
        for mutation in ('missing','traversal','other','unregistered_mode'):
            cfg=copy.deepcopy(self.config)
            test=cfg['tests']['chip-cpu-scenario']
            if mutation=='missing':
                del test['flow_plan']
            elif mutation=='traversal':
                test['flow_plan']='../config/scenarios/cpu-bfm-ddr-roundtrip.json'
            elif mutation=='other':
                test['flow_plan']='config/scenarios/dma-roundtrip.json'
            else:
                test['firmware_mode']='ethernet_cpu'
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as temp:
                cfg_path=Path(temp)/'regression.yaml'
                cfg_path.write_text(yaml.safe_dump(cfg))
                with self.assertRaisesRegex(ValueError,
                    'scenario adapter requires explicit flow_plan'
                    if mutation=='missing' else
                    'unsupported or unsafe executable scenario path'):
                    regress.load_config(cfg_path)

    def test_report_configuration_fails_closed(self):
        for mutation in ('engine','clock','limit','field'):
            cfg=copy.deepcopy(self.config)
            test=cfg['tests']['supernoc']
            if mutation=='engine': test['engine']='xezim'
            elif mutation=='clock': del test['report']['axi']['clock']
            elif mutation=='limit': test['report']['axi']['max_events']=0
            else: test['report']['axi']['unknown']=True
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'regression.yaml';path.write_text(yaml.safe_dump(cfg))
                with self.assertRaisesRegex(ValueError, 'invalid protocol report' if mutation == 'engine' else 'invalid AXI report'):
                    regress.load_config(path)

    def test_negative_requires_named_failure_and_failed_process(self):
        test = self.config['tests']['memory-negative']
        marker = test['expect_failure']
        for code, log, timed_out in [(0, marker, False), (1, 'compile error', False),
                                     (-9, marker, False), (1, marker, True),
                                     (1, marker + test['pass'], False)]:
            with self.subTest(code=code, log=log):
                self.assertFalse(regress.check_outcome(code, log, test, timed_out)[0])
        self.assertTrue(regress.check_outcome(1, marker, test)[0])

    def test_simulation_zero_exit_without_pass_is_failure(self):
        test = self.config['tests']['boot']
        self.assertFalse(regress.check_outcome(0, 'maximum time reached', test)[0])
        self.assertTrue(regress.check_outcome(0, test['pass'], test)[0])

    def test_filelists_preserve_order_and_options_and_reject_missing_rtl(self):
        a, b = ROOT/'rtl/memory/local_sram.sv', ROOT/'dv/memory/local_sram_tb.sv'
        files, dirs, defines = regress.parse_filelist(f'+incdir+{ROOT}/rtl\n+define+CHECK=1\n{a}\n{b}\n')
        self.assertEqual(files, [str(a), str(b)])
        self.assertEqual(dirs, [str(ROOT/'rtl')])
        self.assertEqual(defines, ['CHECK=1'])
        with self.assertRaisesRegex(ValueError, 'missing RTL'):
            regress.parse_filelist('missing-source.sv\n')

    def test_relocated_boot_emits_matching_addresses_and_real_firmware(self):
        overrides = self.config['tests']['boot-relocated']['boot_relocate']
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            regress.boot_variant(overrides, out)
            manifest = json.loads((out/'manifest.json').read_text())
            package = (out/'boot_config_pkg.sv').read_text()
            for key, region in [('sram0', 'compute0.sram'), ('sram1', 'compute1.sram'),
                                ('flash', 'boot.flash'), ('reset_ctrl', 'boot.reset_ctrl')]:
                address = int(overrides[region], 0)
                self.assertEqual(manifest['addresses'][key], address)
                self.assertIn(f"{key.upper()}_BASE = 32'h{address:08x}", package)
            cfg = yaml.safe_load((out/'soc.yaml').read_text())
            firmware = bootgen.build(cfg)
            self.assertEqual(len(firmware['images']['compute1']), 4)
            self.assertIn('none: CPU0 copies', manifest['sram_initialization'])

    def test_bender_vendor_sources_match_locked_allowlist(self):
        lock = yaml.safe_load((ROOT/'config/ip.lock.yaml').read_text())['third_party']
        bender = yaml.safe_load((ROOT/'Bender.yml').read_text())
        for ip in ('serv', 'picorv32', 'verilog_axi', 'wb2axip'):
            prefix = f'.tools/{ip}/'
            actual = {f[len(prefix):] for group in bender['sources'] for f in group['files'] if f.startswith(prefix)}
            self.assertEqual(actual, set(lock[ip]['modules']))

    def test_build_fingerprint_detects_changed_headers_and_rtl(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rtl, header = root/'dut.sv', root/'defs.svh'
            rtl.write_text('module dut; endmodule\n')
            header.write_text('`define SIZE 4\n')
            plan = {'sources': [str(rtl)], 'includes': [str(root)], 'defines': [], 'top': 'dut'}
            with patch.object(sim_cocotb.shutil, 'which', return_value='/fake/verilator'), \
                 patch.object(sim_cocotb.subprocess, 'check_output', return_value=b'Verilator 5.020'), \
                 patch.dict(sys.modules, {'cocotb': types.SimpleNamespace(__version__='1.9.2')}):
                initial = sim_cocotb.build_fingerprint(plan)
                header.write_text('`define SIZE 8\n')
                self.assertNotEqual(initial, sim_cocotb.build_fingerprint(plan))
                header.write_text('`define SIZE 4\n')
                self.assertEqual(initial, sim_cocotb.build_fingerprint(plan))
                rtl.write_text('module dut; wire changed; endmodule\n')
                self.assertNotEqual(initial, sim_cocotb.build_fingerprint(plan))

    def test_new_cocotb_target_does_not_inherit_noc_wrapper(self):
        # An existing engine can be reused with a new Bender source target.
        # Only the NoC source provider is allowed to add NoC packages/wrapper.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rtl = root/'other_tb.sv'
            rtl.write_text('module other_tb; endmodule\n')
            resolver = types.SimpleNamespace(sources=lambda test: ([str(rtl)], [], []))
            options = types.SimpleNamespace(arg=[], memory_config=None, network=[], stage='files')
            test = {'engine': 'cocotb-verilator', 'sources': 'other', 'top': 'other_tb'}
            with patch.object(regress, 'ROOT', root):
                self.assertTrue(regress.run_target('other', test, resolver, options))
            plan = json.loads((root/'.tools/regression/other/plan.json').read_text())
            self.assertEqual(plan['sources'], [str(rtl)])


if __name__ == '__main__':
    unittest.main()
