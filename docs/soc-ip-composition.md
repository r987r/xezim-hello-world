# Typed SoC IP composition contracts (#166)

The default SoC now has a generated typed **declaration** manifest built from
the source-validated canonical SoC IR (#165) and the existing subsystem plugin
registry contract. It records a single type profile for compute, memory and
peripheral subsystems, separately from each installed instance.

Run source-only checks:

    python3 tools/soc_ip_compose.py --out .tools/soc-compose/manifest.json
    python3 tools/soc_ip_compose.py --out .tools/soc-compose/manifest.json --check
    python3 -m unittest tests.test_soc_ip_compose -v

Manifest includes original CPU/IP/controller and simulation backend choices,
typed logical AXI data and config master/target roles, instance address
apertures, clock-domain policy, source-derived connection identities, and
authoritative source-lock hashes. It reuses existing
tools/subsystem_plugin_contract.py Registry. An unsupported IP type, missing
physical topology boundary, inconsistent instance list, missing CPU/IP choice
or unqualified CDC fails closed.

These are *not* elaborated RTL port bindings or active PCIe/Ethernet engines.
The current generator still uses explicit full_chip_gen and regress.py
firmware_mode branches. The next #166 milestone makes individual generic
emitters consume this manifest and proves exact selected RTL equivalence with
#163. A second hardware instance is not considered supported until it
actually generates/compiles and passes routed traffic through its new NoCs.
Related: #162 #163 #165 #46 #152 #167.
