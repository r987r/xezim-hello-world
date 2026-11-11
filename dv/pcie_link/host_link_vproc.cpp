// Test-only provider adapter for the ONE canonical SCN-C action contract.
// No second parser, scheduler, action catalog, or independent RTL pass claim.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include "pcieModelClass.h"
#include "ltssm.h"
#include "soc_scn_action_adapter.h"

static bool reset_deasserted = false;

static int on_reset(int irq) {
    if (irq & 4) reset_deasserted = true;
    return 0;
}

static void on_packet(pPkt_t pkt, int, void*) {
    if (pkt) DISCARD_PACKET(pkt);
}

static int train_selected_link(const soc_scn_action_t *action, void *opaque) {
    if (!action || !opaque || std::strcmp(action->kind, "pcie.link.train"))
        return -1;
    int lanes = -1, gen = -1, width = -1;
    const char *link = nullptr;
    for (uint32_t i = 0; i < action->argument_count; ++i) {
        const soc_scn_argument_t *arg =
            soc_scn_argument_at(action->first_argument + i);
        if (!arg || !arg->key) return -1;
        if (!std::strcmp(arg->key, "link") && arg->is_text)
            link = arg->text_value;
        else if (!std::strcmp(arg->key, "lanes") && !arg->is_text)
            lanes = static_cast<int>(arg->uint_value);
        else if (!std::strcmp(arg->key, "generation") && !arg->is_text)
            gen = static_cast<int>(arg->uint_value);
        else if (!std::strcmp(arg->key, "data_width_bits") && !arg->is_text)
            width = static_cast<int>(arg->uint_value);
        else return -1;
    }
    // Never silently accept unsupported width/lane changes or a foreign host.
    if (!link || std::strcmp(link, "pcie0") || lanes != 1 ||
        gen != 1 || width != 32) return -1;
    auto *rc = static_cast<pcieModelClass *>(opaque);
    std::printf("PCIE_HOST_TRACE: selected action=%s kind=%s link=%s lanes=%d gen=%d width=%d plan=%s\n",
                action->action_instance_id, action->kind, link, lanes, gen,
                width, SOC_SCN_PLAN_SHA256);
    std::fflush(stdout);
    // Actual original pcievhost LTSSM; NOT a forced or invented LinkUp.
    rc->initLink(lanes);
    std::printf("PCIE_HOST_L0: original InitLink(%d) returned for action=%s\n",
                lanes, action->action_instance_id);
    std::fflush(stdout);
    return 0;
}

static int record_driver(const soc_scn_action_t *action, const char *stage, void*) {
    if (!action || !stage) return -1;
    std::printf("PCIE_SCN_DRIVER: plan=%s action=%s stage=%s\n",
                SOC_SCN_PLAN_SHA256, action->action_instance_id, stage);
    std::fflush(stdout);
    return 0;
}

extern "C" void VUserMain0(int node) {
    pcieModelClass rc(node);
    rc.initialisePcie(on_packet, nullptr);
    VWrite(LINK_STATE, 0, 0, node);
    rc.configurePcie(CONFIG_DISABLE_SCRAMBLING);
    rc.configurePcie(CONFIG_DISABLE_8B10B);
    VRegIrq(on_reset, node);
    while (!reset_deasserted) rc.sendOs(IDL);

    // Supplied independently from the selected runner plan at simulation
    // launch, not by copying the generated header's SHA as its own proof.
    const char *selected_sha = std::getenv("SOC_SELECTED_PLAN_SHA");
    const soc_scn_driver_registration_t handlers[] = {
        {"pcie.link.train", train_selected_link},
    };
    const soc_scn_driver_result_t result = soc_scn_driver_run(
        selected_sha, handlers, 1, record_driver, &rc);
    if (result.status != SOC_SCN_ADAPTER_OK ||
        result.issued != SOC_SCN_ACTION_COUNT ||
        result.driver_done != SOC_SCN_ACTION_COUNT) {
        std::fprintf(stderr, "PCIE_SCN_DRIVER_FAIL: status=%d issued=%u done=%u\n",
                     result.status, result.issued, result.driver_done);
        VWrite(PVH_FATAL, 0, 0, node);
        return;
    }
    rc.sendIdle(100);
    VWrite(PVH_FINISH, 0, 0, node);
}
