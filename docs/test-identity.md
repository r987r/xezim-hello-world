# Canonical regression naming and execution identity

This is the naming layer added **after** the common #129 runner. It does not
introduce another test engine, an additional SoC topology registry, or a
second set of INIT/RUN/CHECK actions.

## Canonical identity

```
simulator/config_target/testname/run_id
verilator/soc-cpu-dma-scenario/dma-sram-ddr-roundtrip/ci-123456-a1-ea0f142d9f6b
xezim/boot-default/cpu-cold-boot/local-2c34a679e710
```

- **simulator** is normalized from the actual regression `engine`; for
  example `cocotb-verilator` and Verilator lint use `verilator`, while
  native Xezim and compile-only Xezim use `xezim`. The Cocotb harness is
  retained in the `engine` metadata, not treated as another simulator.
- **config_target** is derived from the resolved source scope, full-chip top,
  selected `firmware_mode`, boot relocation, synthesis define or alternate
  memory-config source. Its fingerprint includes the source-selected SoC,
  configuration fields and actual compiled filelist; changing the RTL/IP
  implementation changes source provenance even if its human-readable label
  stays the same. The configuration digest also fingerprints the authoritative
  `config/interface_contracts.yaml`, `config/ip.lock.yaml`, `Bender.yml`,
  `Bender.lock` and (when present) DDR controller toolchain lock. Thus a
  changed IP pin or configured AXI budget does not silently reuse the same
  configuration digest even when compiled filelist paths are unchanged. A configuration name does **not** independently assert
  selected RTL elaboration or real packet attachment.
- **testname** is declared once as `logical_test` on the original entry in
  `config/regression.yaml` and is checked against the source-owned
  catalog. It never contains simulator, IP vendor or random-seed names.
  In particular, CPU-C and BFM DDR roundtrips are one logical
  `dma-sram-ddr-roundtrip` test on two different selected configurations.
- **run_id** is unique per runner invocation, with `ci-<workflow_id>-a<attempt>`
  or `local` provenance plus a random execution suffix. The seed, source
  selection SHA, workflow run/attempt and logical target are independent
  fields. Never use `seed` as `run_id` or deduce PASS from a path.

All path components are validated lowercase slugs; duplicate
`(simulator,config_target,testname)` catalog registrations fail CI. The
`tools/test_identity.py` validator hashes both the configuration selection
and the complete run identity. The **original** run's `identity.json`,
`plan.json`, `selected-test-plan.json` and `result.json` must agree.
No later version of the YAML can relabel an archived test.

## Rollout and backward compatibility

- New published reports use exactly one primary path:
  `runs/<simulator>/<config_target>/<testname>/<run_id>/report.html`.
  The collector verifies the original saved identity, hash, runner binding
  and CI attempt before accepting that path. Raw AXI/GMII/PCIe/DFI capture,
  logs and filelists are stored alongside it only once; no `by-test`
  alias or duplicate current report is generated.
- Historical archives without immutable identities retain their **original**
  `runs/<workflow-id>-<attempt>/<old-target>/` paths for explicit comparison.
  They cannot be silently relabeled with the latest catalog or presented as
  current canonical test results.
- The on-runner `.tools/regression/<selection-key>` scratch directory is
  still a private temporary compatibility detail for workflows that resolve
  source filelists by selection key. This is **not** a second public naming
  scheme. Migrating this private scratch resolver and all upload scripts is
  tracked separately in [#139](https://github.com/r987r/xezim-hello-world/issues/139); do not delete historical build evidence. 
- The physical memory aperture, CSR bases, NoC configuration and IP
  version still come from `config/soc.yaml`, pinned manifests and
  the actual selected source closure. Renaming a test cannot swap an IP.

## Exclusive physical run-workspace foundation (#139)

`tools/run_workspace.py` reuses the **existing** immutable
`tools/test_identity.selected()` identity. `reserve_run(root, identity)`
atomically claims exactly one
`<simulator>/<config_target>/<testname>/<run_id>/` directory and writes the
validated original `identity.json`. A second writer, altered selected plan,
reused run ID, path traversal, external/symlink target or foreign identity
fails closed. `verify_run` checks the on-disk identity, and
`canonical_artifact` returns a safe, not-yet-existing path for a producer.

This is a *partial migration primitive*, **not** a changed default
`regress.py` root. All existing build/filelist caches and target-named scratch
directories remain intentionally unchanged until each producer and its CI
upload/postprocessor are migrated together. Never silently redirect a test
writer without moving its compiled source/verifier dependencies, and never
relabel previous Actions artifacts as canonical. The selected path conveys no
hardware PASS: real output still requires independent simulator/monitor
evidence. Test with `python3 -m unittest tests.test_run_workspace -v`.

## Adding tests

Add one regression YAML test entry with an explicit `logical_test`.
Select its existing simulator/source/firmware/scenario fields. The identity
resolver determines the canonical configuration and refuses any collision.
A new runtime stimulus target still needs a real typed action adapter or a
separately tracked #119 legacy exception; naming metadata can never waive
checker evidence, change the seed, or turn planned INIT/RUN/CHECK into
observed execution.

Dedicated verification: `tests/test_test_identity.py`; general CI runs
the source catalog and archive-provenance checks; Pages integrates the
same metadata without hand-authored per-test navigation.
