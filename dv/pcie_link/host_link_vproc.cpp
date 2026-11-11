// Original PCIe link-initialization API from pinned pcievhost.
// Testbench-only VProc driver; no model-owned endpoint or synthetic link-up.
#include <cstdio>
#include <cstdlib>
#include "pcieModelClass.h"
#include "ltssm.h"

static bool reset_deasserted = false;

static int on_reset(int irq) {
    if (irq & 4) reset_deasserted = true;
    return 0;
}

static void on_packet(pPkt_t pkt, int, void*) {
    if (pkt) DISCARD_PACKET(pkt);
}

extern "C" void VUserMain0(int node) {
    pcieModelClass rc(node);
    rc.initialisePcie(on_packet, nullptr);
    // Same PHY-mode settings as original testpipex1/usercode/VUserMain0.cpp.
    VWrite(LINK_STATE, 0, 0, node);
    rc.configurePcie(CONFIG_DISABLE_SCRAMBLING);
    rc.configurePcie(CONFIG_DISABLE_8B10B);
    VRegIrq(on_reset, node);
    while (!reset_deasserted) rc.sendOs(IDL);
    std::printf("PCIE_HOST_TRACE: start original InitLink(1)\n");
    std::fflush(stdout);
    // This is the *real* original host LTSSM algorithm, not forced status.
    rc.initLink(1);
    std::printf("PCIE_HOST_L0: InitLink(1) returned from original host LTSSM\n");
    std::fflush(stdout);
    // Original VProc termination; CI independently requires endpoint L0.
    rc.sendIdle(100);
    VWrite(PVH_FINISH, 0, 0, node);
}
