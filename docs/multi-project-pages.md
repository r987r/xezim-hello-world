# Independent SoC projects and Pages routing

The root Pages index is now the **project picker**. Project identities come
only from \`config/projects/catalog.yaml\`, and each id must equal the
\`name\` in a distinct authored source configuration.

## Project entry points

- \`index.html\`: project picker, no implicit selection.
- \`projects/xezim_soc_dv/index.html\`: original SoC project dashboard.
- \`projects/xezim_ethernet_cpu_ddr_pcie/index.html\`: independent
  Ethernet/CPU+DDR/PCIe project dashboard.
- \`projects/<id>/architecture.html\`: project-local source topology and
  qualification information.
- \`projects/<id>/address-map.html\`: only that project's data/CSR windows.
- \`projects/<id>/runs.html\`: only project-attributed evidence.
- Original \`soc-overview.html\`, \`topology.html\`, \`explorer.html\`,
  \`fabric.html\`, \`address-map.html\`, \`runs.html\` and run-report
  deep links remain usable for the legacy project.

The new project does not inherit the original chip's generator artifacts,
mesh counts, CPU inventory, latency table or traffic captures. Its pages
show source-defined design intent and explicitly unavailable hardware data.
The project registry never claims its chip was emitted or simulated.

## True independence contract

The two projects own separate source YAMLs, logical CPU and memory
composition, address windows, topology declarations and qualification
identities. They share the same pinned IP lock, generator/RTL emitters,
scenario dispatcher, AXI/TLP/GMII/DFI monitors, evidence validator and
publisher. This is **logical project separation** within one repo, not
a duplicated framework or a claim that generic RTL composition is finished.

Current block for production-independent builds: project B's direct-data
FlooGen endpoints, full-chip composer and one-core CPU firmware integration
are not yet implemented. The project B run viewer is deliberately empty
until a real source-qualified B regression is created and runs.

No untagged historical test evidence may be attributed to project B.
Once new project test targets exist, project identity belongs in the
selected immutable run manifest and must be verified at collection time;
a target-name heuristic is not sufficient.

Verify with:

\`\`\`sh
python3 -m unittest tests.test_multi_project_site tests.test_three_region_project -v
python3 tools/project_catalog.py --out .tools/projects/catalog.json
python3 tools/publish_site.py
\`\`\`

Source-contract and publisher tests are not full-chip data-path verification.
