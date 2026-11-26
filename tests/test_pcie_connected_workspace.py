import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import pcie_connected_compile as connected


class ConnectedWorkspaceTest(unittest.TestCase):
    def test_new_workspace_consumes_snapshot_without_changing_compiler_selection(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(connected, 'ROOT', Path(temp)):
            root = Path(temp)
            for path in ('config/soc.yaml', 'config/interface_contracts.yaml', 'config/ip.lock.yaml',
                         'Bender.yml', 'Bender.lock'):
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text((ROOT / path).read_text())
            sim = root / '.tools/pcie-connected-fusesoc/fusesoc_pcie_phy_core_1.0.0/sim'
            sim.mkdir(parents=True)
            relative = sim.relative_to(root)
            endpoint = [f'src/original/{i}.sv' for i in range(35)]
            (sim / 'fusesoc_pcie_phy_core_1.0.0.vc').write_text(
                '\n'.join(['+incdir+src', *endpoint, 'src/example/pcie_top.v']))
            with patch.object(connected, 'sources', return_value=(
                    ['noc.sv'], ['noc-include'], ['NOC_OPTION'])), patch.object(
                    connected, 'checkout', return_value=('a'*40, False)):
                self.assertEqual(connected.sim_directory(relative), sim)
                with self.assertRaises(ValueError):
                    connected.sim_directory(Path('build') / relative)
                inputs = connected.selection(sim)
                self.assertEqual(inputs[0][:35], endpoint)
                self.assertIn('noc.sv', inputs[0])
                self.assertTrue(inputs[0][-1].endswith('/tb_pcie_cross_link.sv'))
                raw = ('\n'.join(inputs[0])+'\n').encode()
                out = connected.reserve(sim, raw)
                self.assertEqual(out.parent.name, 'host-to-sram-roundtrip')
                (out / 'sources.f').write_text('not what will compile\n')
                with self.assertRaisesRegex(ValueError, 'source list differs'):
                    connected.compile_connected(sim, out, inputs)
                (out / 'sources.f').write_bytes(raw)

                def executable(args, *, cwd, check):
                    self.assertEqual(cwd, sim)
                    self.assertTrue(check)
                    start = args.index(endpoint[0])
                    self.assertEqual(args[start:start+len(inputs[0])], inputs[0])
                    receipt = json.loads((out / 'compiler-argv.json').read_text())
                    self.assertEqual(receipt['argv'], args)
                    self.assertEqual(receipt['cwd'], str(cwd))
                    private = Path(args[args.index('--Mdir')+1])
                    self.assertEqual(private.parent, root/'.tools/pcie-connected-obj')
                    self.assertEqual(private.name, out.name)
                    (private/'Vtop').touch()
                    return subprocess.CompletedProcess(args, 0)

                with patch.object(connected.subprocess, 'run', side_effect=executable):
                    connected.compile_connected(sim, out, inputs)


if __name__ == '__main__':
    unittest.main()
