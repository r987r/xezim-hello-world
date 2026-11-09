# Test-independent SoC hardware variant identities (#165)

The existing regression source YAML defines tests; it is not itself a hardware
variant directory. Run:

    python3 tools/hardware_variants.py --out .tools/variants/catalog.json

This derives project/variant names using the existing canonical
`test_identity.config_target` algorithm. Two directed/randomized tests may
share one build; hardware is not redefined just because a scenario changes.
Uncompiled variants are explicitly `declared_only_not_compiled`.

After preparing real source filelists with `regress.py --stage files`, run

    python3 tools/hardware_variants.py --out .tools/variants/verified.json --require-resolved

to verify every source/identity/archive hash and check that two tests claiming
one hardware variant actually select the same RTL `soc_top.sv` SHA. Missing,
tampered or conflicting sources fail closed. Does not infer RTL elaboration,
correct bytes or accepted traffic. The generator-owned checked-in default RTL is proposed in stacked [PR #178](https://github.com/r987r/xezim-hello-world/pull/178); it is not on `main` until the generator gate and its own checks pass. Opt-in generated snapshots require qualified separate backends and exact-source parity.
