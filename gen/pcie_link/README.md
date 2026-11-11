# Digital PCIe provider selection (generated)

Do not edit. `make gen` regenerates from [config/pcie_link.yaml](../../config/pcie_link.yaml) and [config/ip.lock.yaml](../../config/ip.lock.yaml).

Endpoint: `pcie_endpoint_openpcie` @ `4b4779c6c68048240c9a625b45156e864bf6105a`

Host testbench: `pcie_host_pcievhost` @ `b82b2ff3a047f742354c9607dea34b9b97bf108c` (GPL-3.0; not SoC RTL).

Digital adapter: `dv/pcie_link/pipe_x1_adapter.sv`.

The upstream PCIe configuration-space RDL is **source-owned by the endpoint IP**, separate from SoC Config-NoC requester CSR. Do not copy BAR0 into a second hand-maintained SoC register map.

**NOT QUALIFIED:** LTSSM L0, PHY-status responder, host enumeration, programmable BAR0 decode and silicon SerDes. The existing `chip-pcie-host` remains TLP-bridge-only. Use original pinned RTL CI evidence before changing these labels.
