// Root-complex provider adapter to canonical SCN-C action ABI.
// The single canonical plan is resolved by tools/scenario_plan.py and compiled
// with tools/scenario_c.py. This code is a provider driver, NOT a test scheduler.
// GPL pcievhost remains pinned, fetched and simulation-only.
#include <cstdio>
#include <cstdlib>
#include <cstring>
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

struct LinkContext {
    pcieModelClass *host;
};

static int link_arg(const soc_scn_action_t *a, const char *key,
                    uint64_t *number, const char **text) {
    for (uint32_t k = a->first_argument;
         k < a->first_argument + a->argument_count; ++k) {
        const soc_scn_argument_t *v = soc_scn_argument_at(k);
        if (!v || std::strcmp(v->key, key)) continue;
        if (number) {
            if (v->is_text) return -1;
            *number = v->uint_value;
        }
        if (text) {
            if (!v->is_text) return -1;
            *text = v->text_value;
        }
        return 0;
    }
    return -1;
}

static int train_link(const soc_scn_action_t *a, void *opaque) {
    LinkContext *ctx = static_cast<LinkContext *>(opaque);
    const char *link = nullptr;
    uint64_t lanes = 0, gen = 0, width = 0;
    if (std::strcmp(a->kind, "pcie.link.train") ||
        link_arg(a, "link", nullptr, &link) ||
        link_arg(a, "lanes", &lanes, nullptr) ||
        link_arg(a, "generation", &gen, nullptr) ||
        link_arg(a, "data_width_bits", &width, nullptr) ||
        std::strcmp(link, "pcie0") || lanes != 1 || gen != 1 || width != 32) {
        std::fprintf(stderr, "FAIL: selected PCIe provider contract unsupported\n");
        return -1;
    }
    std::printf("PCIE_HOST_TRACE: original pcievhost InitLink(%llu)\n",
                static_cast<unsigned long long>(lanes));
    std::fflush(stdout);
    ctx->host->initLink(static_cast<int>(lanes));
    // Driver callback return does not prove endpoint L0 or link qualification.
    std::printf("PCIE_HOST_L0: original host LTSSM InitLink returned\n");
    std::fflush(stdout);
    return 0;
}

static int driver_event(const soc_scn_action_t *a, const char *stage, void*) {
    std::printf("PCIE_SCN_DRIVER|%s|%s|%s|%s\n",
                SOC_SCN_PLAN_SHA256, a->action_instance_id, a->kind, stage);
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

    const char *selected = std::getenv("SOC_SELECTED_PLAN_SHA");
    if (!selected) {
        std::fprintf(stderr, "FAIL: no independently selected scenario-plan SHA\n");
        VWrite(PVH_FATAL, 0, 0, node);
        return;
    }

    const soc_scn_driver_registration_t providers[] = {
        {"pcie.link.train", train_link},
    };
    LinkContext ctx{&rc};
    const soc_scn_driver_result_t result = soc_scn_driver_run(
        selected, providers, 1, driver_event, &ctx);
    if (result.status != SOC_SCN_ADAPTER_OK ||
        result.issued != 1 || result.driver_done != 1) {
        std::fprintf(stderr, "FAIL: PCIe selected SCN-C provider dispatch, status=%d\n",
                     result.status);
        VWrite(PVH_FATAL, 0, 0, node);
        return;
    }
    rc.sendIdle(100);
    VWrite(PVH_FINISH, 0, 0, node);
}
