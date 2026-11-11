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

// Only the RC's actual receive callback can retire a host Config TLP.
// No TB BAR register peeking, no callback from the endpoint side.
static int pending_tag = -1;
static bool completion_seen = false;
static bool unexpected_completion = false;
static int completion_status = -1;
static unsigned completion_byte_count = 0;
static uint32_t completion_data = 0;
static unsigned completed_config_packets = 0;
static unsigned next_tag = 0;

static void on_packet(pPkt_t pkt, int, void*) {
    if (!pkt) return;
    if (pkt->seq != DLLP_SEQ_ID) {
        const int type = GET_TLP_TYPE(pkt->data);
        if (type == TL_CPL || type == TL_CPLD) {
            const int tag = GET_CPL_TAG(pkt->data);
            const int status = GET_CPL_STATUS(pkt->data);
            const unsigned bytes = pkt->ByteCount;
            std::printf("PCIE_RC_CFG_RX_CPL: tag=%d status=%d type=%02x bytes=%u timestamp=%u\\n",
                        tag, status, type, bytes, pkt->TimeStamp);
            std::fflush(stdout);
            if (pending_tag < 0 || tag != pending_tag || completion_seen) {
                unexpected_completion = true;
            } else {
                completion_seen = true;
                completion_status = status;
                completion_byte_count = bytes;
                completion_data = 0;
                if (type == TL_CPLD && bytes >= 4) {
                    const PktData_t *payload = GET_TLP_PAYLOAD_PTR(pkt->data);
                    for (int byte = 0; byte < 4; ++byte)
                        completion_data |= static_cast<uint32_t>(payload[byte] & 0xff) << (8*byte);
                }
                ++completed_config_packets;
            }
        }
    }
    DISCARD_PACKET(pkt);
}

static bool wait_config_completion(pcieModelClass *rc, int tag,
                                   bool data_expected, uint32_t *value) {
    // Bounded *host-local* idle-clock progress. Missing completion fails.
    for (int spins = 0; spins < 30000 && !completion_seen && !unexpected_completion; ++spins)
        rc->sendIdle(1);
    const bool ok = completion_seen && !unexpected_completion &&
                    completion_status == CPL_SUCCESS &&
                    (!data_expected || completion_byte_count >= 4);
    std::printf("PCIE_RC_CFG_RESULT: tag=%d seen=%d status=%d bytes=%u ok=%d\\n",
                tag, completion_seen, completion_status, completion_byte_count, ok);
    std::fflush(stdout);
    if (ok && value) *value = completion_data;
    pending_tag = -1;
    completion_seen = false;
    completion_status = -1;
    completion_byte_count = 0;
    return ok;
}

static bool start_config_request(int tag) {
    if (pending_tag >= 0 || completion_seen || unexpected_completion)
        return false;
    pending_tag = tag;
    completion_status = -1;
    completion_byte_count = 0;
    completion_data = 0;
    return true;
}

static bool config_read(pcieModelClass *rc, uint32_t off, int tag, uint32_t *value) {
    if (!start_config_request(tag)) return false;
    std::printf("PCIE_RC_CFG_TX: CfgRd0 addr=%03x tag=%d\\n", off, tag);
    std::fflush(stdout);
    rc->cfgRead(off, 4, tag, 1);
    return wait_config_completion(rc, tag, true, value);
}

static bool config_write(pcieModelClass *rc, uint32_t off, uint32_t word, int tag) {
    if (!start_config_request(tag)) return false;
    PktData_t bytes[4] = {
        static_cast<PktData_t>(word & 0xff),
        static_cast<PktData_t>((word >> 8) & 0xff),
        static_cast<PktData_t>((word >> 16) & 0xff),
        static_cast<PktData_t>((word >> 24) & 0xff),
    };
    std::printf("PCIE_RC_CFG_TX: CfgWr0 addr=%03x data=%08x tag=%d\\n", off, word, tag);
    std::fflush(stdout);
    rc->cfgWrite(off, bytes, 4, tag, 1);
    return wait_config_completion(rc, tag, false, nullptr);
}

static int configure_selected_bar0(const soc_scn_action_t *action, void *opaque) {
    if (!action || !opaque || std::strcmp(action->kind, "pcie.config.bar0"))
        return -1;
    const char *link = nullptr;
    uint64_t base = UINT64_MAX, aperture = 0, bar_index = UINT64_MAX;
    for (uint32_t i = 0; i < action->argument_count; ++i) {
        const soc_scn_argument_t *arg = soc_scn_argument_at(action->first_argument + i);
        if (!arg || !arg->key) return -1;
        if (!std::strcmp(arg->key, "link") && arg->is_text)
            link = arg->text_value;
        else if (!std::strcmp(arg->key, "bar_index") && !arg->is_text)
            bar_index = arg->uint_value;
        else if (!std::strcmp(arg->key, "aperture_bytes") && !arg->is_text)
            aperture = arg->uint_value;
        else if (!std::strcmp(arg->key, "host_bus_base") && !arg->is_text)
            base = arg->uint_value;
        else return -1;
    }
    if (!link || std::strcmp(link,"pcie0") || bar_index != 0 ||
        aperture < 4096 || aperture > 1048576 || (aperture & (aperture-1)) ||
        base > 0xffffffffULL || (base & (aperture-1)) ||
        base + aperture > 0x100000000ULL)
        return -1;
    auto *rc = static_cast<pcieModelClass*>(opaque);
    std::printf("PCIE_RC_CFG_BEGIN: action=%s plan=%s bar=0 aperture=%llu base=%08x\\n",
                action->action_instance_id, SOC_SCN_PLAN_SHA256,
                static_cast<unsigned long long>(aperture),static_cast<unsigned>(base));
    std::fflush(stdout);
    // Real data link / credit exchange after separately completed link LTSSM.
    rc->initFc();
    uint32_t actual = 0;
    const uint32_t mask = static_cast<uint32_t>(~(aperture-1)) & 0xfffffff0U;
    auto tag = []() { return static_cast<int>((next_tag++) & 31u); };
    if (!config_write(rc, 0x10, 0xffffffffU, tag()) ||
        !config_read(rc, 0x10, tag(), &actual) || actual != mask) {
        std::fprintf(stderr,"PCIE_RC_CFG_FAIL: BAR0 sizing actual=%08x expected=%08x\\n",
                     actual,mask);
        return -1;
    }
    std::printf("PCIE_RC_CFG_PROBE_OK: BAR0 mask=%08x\\n",actual);
    if (!config_write(rc, 0x10, static_cast<uint32_t>(base), tag()) ||
        !config_read(rc, 0x10, tag(), &actual) || actual != base) {
        std::fprintf(stderr,"PCIE_RC_CFG_FAIL: BAR0 readback actual=%08x expected=%08x\\n",
                     actual,static_cast<unsigned>(base));
        return -1;
    }
    std::printf("PCIE_RC_CFG_BAR_ASSIGNED: BAR0 bus=%08x\\n",actual);
    if (!config_write(rc, 0x04, 0x00000002U, tag()) ||
        !config_read(rc, 0x04, tag(), &actual) || (actual & 2) != 2) {
        std::fprintf(stderr,"PCIE_RC_CFG_FAIL: COMMAND.MSE observed=%08x\\n",actual);
        return -1;
    }
    std::printf("PCIE_RC_CFG_MSE_ENABLED: command=%08x completions=%u\\n",
                actual,completed_config_packets);
    return 0;
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
        gen != 1 || width != 16) return -1;
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
        {"pcie.config.bar0", configure_selected_bar0},
    };
    const soc_scn_driver_result_t result = soc_scn_driver_run(
        selected_sha, handlers, 2, record_driver, &rc);
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
