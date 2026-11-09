# SCN-C: canonical SoC scenario metadata for firmware (#152 M2 groundwork)

This **does not create another test planner or C sequence runner**. It converts
the *same* resolved canonical scenario-plan.json used by Python
ActionDispatcher and the existing SV generator into a standalone C11 header.

    python3 tools/scenario_plan.py --scenario config/scenarios/dma-roundtrip.json --out .tools/scenario-c/plan.json
    python3 tools/scenario_c.py --plan .tools/scenario-c/plan.json --out .tools/scenario-c/soc_scenario_contract.h

Header exports version, exact plan SHA-256, scenario ID, seed, and all selected
action records: action instance ID, phase, actor, kind, expected-result ID,
dependencies and typed flattened text/unsigned arguments. Source canonicality,
action DAG validity and representable C/SV arguments reuse existing Python/SV
validators; unknown, orphan, cyclic and fake-execution plans fail closed.

Actual C firmware driver adaptation is intentionally **not** inferred from
generating metadata. The target CPU cannot automatically execute new PCIe,
Ethernet or mailbox hardware actions merely because an action table exists.
M2 needs a hardware-transport/CSR/mailbox adapter, explicit selected-plan SHA
handshake and real RTL test proof; M3/M4 are still pending. Driver-only events
must remain separate from passive observed accepted AXI/TLP/GMII/DFI and
independent final byte checks.


## C11 selected-action callback adapter (partial M2)

\`sw/common/soc_scn_action_adapter.h\` consumes the generated canonical
\`soc_scenario_contract.h\` and dispatches exactly those source-selected
actions through registered callbacks. It does **not** parse another YAML,
re-plan memory, select a new seed, or create another phase scheduler. The
adapter fails before issuing anything on missing/duplicate driver registrations
or illegal dependencies, and stops on the first failed handler.

Its optional events are strictly **issued** and **driver_done**. Hardware
drivers for CPU MMIO, DDR, DMA, Ethernet, PCIe and event mailboxes must be
registered separately; returning from a driver is not proof of accepted AXI
traffic, a real IRQ, controller completion, independently checked bytes, or
SoC signoff. Actual firmware integration with a selected plan SHA handshake
and passive evidence remains open in #152. CI compiles this header with C11
and verifies a deliberately mocked callback smoke, including failure modes.
