/* SCN-2 real PicoRV32 selected action driver over the existing PULP iDMA.
 *
 * Both this CPU and reset-isolated Cocotb BFM consume the same canonical
 * scenario-plan.json. Hardware actions here run through the EXISTING SCN-C
 * typed callback ABI; neither a parallel test scheduler nor fake AXI engine.
 * Driver events below are real CPU AXI stores, not proof of device completion:
 * the original passive NoC AXI/byte scoreboards are still mandatory.
 */
#include "../dma.h"
#include "../../common/memory_pool.h"
#include "../../common/memory_pattern.h"
#include "../../common/test_flow.h"
#include "../../common/soc_scn_action_args.h"
#include "../../common/soc_scn_compiled_runtime.h"
#include "scenario_dma_contract.h"
#include <stdint.h>

#ifndef SOC_CPU0_SRAM
#error "SoC SRAM base missing"
#endif
#ifndef SOC_DDR_BASE
#error "SoC DDR base missing"
#endif
#ifndef SOC_DMA0_CSR
#error "SoC DMA CSR missing"
#endif
#ifndef SOC_MODEL_BYTES
#error "SoC model bound missing"
#endif
#ifndef SOC_MAILBOX
#error "SoC mailbox missing"
#endif

#define DESC_OFF 0x1000u
#define STATUS_OFFSET 0x40u
#define FLOW_OFFSET 0x5cu
#define SCN_ACTION_TRACE_MAGIC 0xa7000000u

typedef struct {
    volatile uint32_t *evidence, *flow, *telemetry;
    volatile uint32_t *csr, *trace;
    soc_mem_region_t pool, ddr;
    soc_mem_allocation_t source, returned, dst;
    soc_dma_arena_t desc;
    uint32_t allocated, initialized, copies, checked, trace_count;
    uint32_t effective_seed;
} soc_scn_cpu_context_t;

static bool match_text(const soc_scn_action_t *action, const char *key,
                       const char *expected) {
    const char *actual = NULL;
    return soc_scn_arg_text(action, key, &actual) &&
           soc_scn_text_equal(actual, expected);
}

static bool match_uint(const soc_scn_action_t *action, const char *key,
                       uint64_t expected) {
    uint64_t actual;
    return soc_scn_arg_uint(action, key, &actual) && actual == expected;
}

static soc_mem_allocation_t *buffer_for(soc_scn_cpu_context_t *ctx,
                                        const char *name) {
    if (soc_scn_text_equal(name, "src")) return &ctx->source;
    if (soc_scn_text_equal(name, "return")) return &ctx->returned;
    if (soc_scn_text_equal(name, "ddr")) return &ctx->dst;
    return NULL;
}

static int on_allocate(const soc_scn_action_t *action, void *user) {
    soc_scn_cpu_context_t *ctx = (soc_scn_cpu_context_t *)user;
    const char *name = NULL, *region_name = NULL;
    uint64_t length, align, expected_phys;
    uint32_t bit;
    soc_mem_allocation_t *out;
    soc_mem_region_t *region;
    if (!soc_scn_arg_text(action, "buffer", &name) ||
        !soc_scn_arg_text(action, "region", &region_name) ||
        !soc_scn_arg_uint(action, "size", &length) ||
        !soc_scn_arg_uint(action, "alignment", &align) ||
        length != SOC_SCN_LENGTH || align != 64u) return -1;
    if (soc_scn_text_equal(name, "src")) {
        bit = 1u; expected_phys = SOC_SCN_SOURCE_PHYS;
        region = &ctx->pool;
        if (!soc_scn_text_equal(region_name, "compute0.sram.payload")) return -1;
    } else if (soc_scn_text_equal(name, "ddr")) {
        bit = 2u; expected_phys = SOC_SCN_DDR_PHYS;
        region = &ctx->ddr;
        if (!soc_scn_text_equal(region_name, "memory0.ddr0")) return -1;
    } else if (soc_scn_text_equal(name, "return")) {
        bit = 4u; expected_phys = SOC_SCN_RETURN_PHYS;
        region = &ctx->pool;
        if (!soc_scn_text_equal(region_name, "compute0.sram.payload")) return -1;
    } else return -1;
    out = buffer_for(ctx, name);
    if (out == NULL || (ctx->allocated & bit) ||
        !soc_mem_alloc(region, length, align, out) ||
        out->phys != expected_phys) return -1;
    ctx->allocated |= bit;
    if (ctx->allocated == 7u) {
        /* Actual CPU AXI address telemetry; original RTL observer decodes it.
         * No manufactured allocation result from the scenario metadata.
         */
        ctx->telemetry[0] = (uint32_t)ctx->source.phys;
        ctx->telemetry[1] = (uint32_t)ctx->returned.phys;
        ctx->telemetry[2] = (uint32_t)ctx->dst.phys;
        ctx->telemetry[3] = (uint32_t)(ctx->dst.phys >> 32);
        ctx->telemetry[4] = 0u;
        ctx->telemetry[5] = 0u;
        soc_flow_emit(ctx->flow, SOC_FLOW_RUN, SOC_FLOW_PASS, 1, 101);
    }
    return 0;
}

static int on_initialize(const soc_scn_action_t *action, void *user) {
    soc_scn_cpu_context_t *ctx = (soc_scn_cpu_context_t *)user;
    uint64_t seed;
    if ((ctx->allocated & 1u) == 0u || ctx->initialized ||
        !match_text(action, "buffer", "src") ||
        !match_text(action, "policy", "strict") ||
        !match_text(action, "pattern.kind", "constant") ||
        !match_uint(action, "length", SOC_SCN_LENGTH) ||
        !soc_scn_arg_uint(action, "pattern.seed", &seed) ||
        seed != SOC_SCN_SEED || seed > UINT32_MAX ||
        ctx->source.cpu_ptr == NULL) return -1;
    ctx->effective_seed = (uint32_t)seed;
    soc_mem_fill_pattern(ctx->source.cpu_ptr, ctx->source.phys,
                         (size_t)SOC_SCN_LENGTH, ctx->effective_seed,
                         SOC_PATTERN_CONSTANT);
    ctx->initialized = 1u;
    return 0;
}

static bool writeback_ready(const soc_dma_chain_t *chain) {
    volatile const uint64_t *done =
        (volatile const uint64_t *)(const void *)&chain->cpu_descs[0];
    return *done == UINT64_MAX;
}

static bool acknowledge_ready(volatile uint32_t *csr) {
    soc_dma_mmio_ack_irq(csr);
    for (unsigned n = 0; n < 10000u; ++n) {
        if (!(csr[SOC_DMA_REG_STATUS / 4u] &
              (SOC_DMA_STATUS_IRQ | SOC_DMA_STATUS_APB_BUSY))) return true;
    }
    return false;
}

static int on_copy(const soc_scn_action_t *action, void *user) {
    soc_scn_cpu_context_t *ctx = (soc_scn_cpu_context_t *)user;
    const char *src_name = NULL, *dst_name = NULL;
    soc_mem_allocation_t *src, *dst;
    uint64_t length;
    uint32_t status = 0u;
    soc_dma_chain_t chain = {0};
    if (ctx->allocated != 7u || !ctx->initialized || ctx->copies >= 2u ||
        !match_text(action, "engine", "compute0.dma") ||
        !soc_scn_arg_text(action, "src", &src_name) ||
        !soc_scn_arg_text(action, "dst", &dst_name) ||
        !soc_scn_arg_uint(action, "length", &length) ||
        length != SOC_SCN_LENGTH) return -1;
    src = buffer_for(ctx, src_name);
    dst = buffer_for(ctx, dst_name);
    if (src == NULL || dst == NULL || src == dst ||
        src->bytes != length || dst->bytes != length) return -1;
    /* This existing qualified SCN-2 backend supports two chained real DMA
     * copies; it cannot silently reinterpret an unsupported source graph.
     */
    if (ctx->copies == 0u &&
        (!soc_scn_text_equal(src_name, "src") ||
         !soc_scn_text_equal(dst_name, "ddr"))) return -1;
    if (ctx->copies == 1u &&
        (!soc_scn_text_equal(src_name, "ddr") ||
         !soc_scn_text_equal(dst_name, "return"))) return -1;
    if (ctx->copies == 0u)
        soc_flow_emit(ctx->flow, SOC_FLOW_RUN, SOC_FLOW_START, 1, 102);
    soc_dma_copy_t op = {src->phys, dst->phys, (uint32_t)length};
    if (!soc_dma_chain_build(&ctx->desc, &op, 1u, true, &chain) ||
        !soc_dma_mmio_submit(ctx->csr, chain.head_phys) ||
        !soc_dma_mmio_wait_irq(ctx->csr, 200000u, &status) ||
        !writeback_ready(&chain) || !acknowledge_ready(ctx->csr))
        return -1;
    ++ctx->copies;
    return 0;
}

static int on_wait_idle(const soc_scn_action_t *action, void *user) {
    soc_scn_cpu_context_t *ctx = (soc_scn_cpu_context_t *)user;
    if (!match_text(action, "engine", "compute0.dma") || ctx->copies != 2u)
        return -1;
    uint32_t status = ctx->csr[SOC_DMA_REG_STATUS / 4u];
    return (status & (SOC_DMA_STATUS_IRQ | SOC_DMA_STATUS_APB_BUSY |
                      SOC_DMA_STATUS_APB_ERROR)) ? -1 : 0;
}

static int on_check(const soc_scn_action_t *action, void *user) {
    soc_scn_cpu_context_t *ctx = (soc_scn_cpu_context_t *)user;
    uint64_t seed;
    if (ctx->allocated != 7u || !ctx->initialized || ctx->copies != 2u ||
        ctx->checked || ctx->returned.cpu_ptr == NULL ||
        !match_text(action, "buffer", "return") ||
        !match_text(action, "expected_from", "src") ||
        !match_text(action, "policy", "strict") ||
        !match_text(action, "pattern.kind", "constant") ||
        !match_uint(action, "length", SOC_SCN_LENGTH) ||
        !soc_scn_arg_uint(action, "pattern.seed", &seed) ||
        seed != ctx->effective_seed) return -1;
    soc_flow_emit(ctx->flow, SOC_FLOW_RUN, SOC_FLOW_START, 1, 103);
    if (soc_mem_check_pattern(ctx->returned.cpu_ptr, ctx->source.phys,
                              (size_t)SOC_SCN_LENGTH, ctx->effective_seed,
                              SOC_PATTERN_CONSTANT) != SOC_SCN_LENGTH)
        return -1;
    ctx->checked = 1u;
    soc_flow_emit(ctx->flow, SOC_FLOW_RUN, SOC_FLOW_PASS, 1, 103);
    soc_flow_emit(ctx->flow, SOC_FLOW_RUN, SOC_FLOW_PASS, 1, 102);
    return 0;
}

/* Real CPU AXI records each selected action transition in scenario-only SRAM.
 * The independent passive AXI checker verifies exact indices/order/strobes/B;
 * these driver events NEVER replace iDMA AXI or byte-scoreboard evidence.
 */
static int record_action(const soc_scn_action_t *action, const char *stage,
                         void *user) {
    soc_scn_cpu_context_t *ctx = (soc_scn_cpu_context_t *)user;
    uint32_t i, event;
    if (ctx->trace_count >= SOC_SCN_ACTION_TRACE_BYTES / 4u)
        return -1;
    for (i = 0; i < SOC_SCN_ACTION_COUNT; ++i)
        if (soc_scn_action_at(i) == action) break;
    if (i >= SOC_SCN_ACTION_COUNT || i >= 4096u) return -1;
    if (soc_scn_text_equal(stage, "issued")) event = 1u;
    else if (soc_scn_text_equal(stage, "driver_done")) event = 2u;
    else return -1;
    ctx->trace[ctx->trace_count++] = SCN_ACTION_TRACE_MAGIC | (i << 8) | event;
    return 0;
}

__attribute__((used, noinline))
int cpu_dma_run(void) {
    volatile uint32_t * const evidence =
        (volatile uint32_t *)(uintptr_t)(SOC_MAILBOX + STATUS_OFFSET);
    volatile uint32_t * const flow =
        (volatile uint32_t *)(uintptr_t)(SOC_MAILBOX + FLOW_OFFSET);
    volatile uint32_t * const plan_witness =
        (volatile uint32_t *)(uintptr_t)SOC_SCN_PLAN_WITNESS_PHYS;
    const uint32_t sha_words[8] = {
        SOC_SCN_PLAN_SHA_WORD_0, SOC_SCN_PLAN_SHA_WORD_1,
        SOC_SCN_PLAN_SHA_WORD_2, SOC_SCN_PLAN_SHA_WORD_3,
        SOC_SCN_PLAN_SHA_WORD_4, SOC_SCN_PLAN_SHA_WORD_5,
        SOC_SCN_PLAN_SHA_WORD_6, SOC_SCN_PLAN_SHA_WORD_7
    };
    *evidence = 0xd0000000u;
    /* The passive AXI checker reconstructs these 32 bytes from real CPU0
     * accepted AW/W/B. The SCN-C driver preflight alone cannot prove SHA.
     */
    for (unsigned i = 0; i < 8u; ++i) plan_witness[i] = sha_words[i];

    soc_scn_cpu_context_t ctx = {0};
    ctx.evidence = evidence;
    ctx.flow = flow;
    ctx.telemetry = evidence + 1;
    ctx.csr = (volatile uint32_t *)(uintptr_t)SOC_DMA0_CSR;
    ctx.trace = (volatile uint32_t *)(uintptr_t)SOC_SCN_ACTION_TRACE_PHYS;
    soc_flow_emit(flow, SOC_FLOW_RUN, SOC_FLOW_START, 1, 101);

    if (SOC_SCN_ACTION_TRACE_BYTES != 8u * SOC_SCN_ACTION_COUNT ||
        SOC_SCN_ACTION_TRACE_PHYS != SOC_SCN_PLAN_WITNESS_PHYS + 32u ||
        !soc_mem_region_init(&ctx.pool, "compute0.sram.payload", SOC_MEM_SRAM,
             (uint64_t)SOC_SCN_SRC_POOL_PHYS, 0x2000u,
             (void *)(uintptr_t)SOC_SCN_SRC_POOL_PHYS) ||
        !soc_mem_region_init(&ctx.ddr, "memory0.ddr0", SOC_MEM_DDR,
             (uint64_t)SOC_SCN_DDR_POOL_PHYS, SOC_MODEL_BYTES - 0x100u, NULL) ||
        !soc_dma_arena_init(&ctx.desc,
             (void *)(uintptr_t)(SOC_CPU0_SRAM + DESC_OFF),
             (uint64_t)SOC_CPU0_SRAM + DESC_OFF, 4096u)) {
        *evidence = 0xd0000020u;
        return 32;
    }

    static const soc_scn_driver_registration_t handlers[] = {
        {"memory.allocate", on_allocate},
        {"memory.initialize", on_initialize},
        {"dma.copy", on_copy},
        {"dma.wait_idle", on_wait_idle},
        {"memory.check", on_check}
    };
    /* Source-selected SHA string is from the same immutable plan; only the
     * independent CPU AXI 256-bit witness checks hardware receipt.
     * The compiled variant resolves the same selected typed C callbacks
     * once, retaining exact dependency/argument and SHA checks.
     */
    soc_scn_driver_result_t result = soc_scn_driver_run_compiled(
        SOC_SCN_PLAN_SHA256, handlers,
        sizeof(handlers) / sizeof(handlers[0]), record_action, &ctx);
    if (result.status != SOC_SCN_ADAPTER_OK ||
        result.issued != SOC_SCN_ACTION_COUNT ||
        result.driver_done != SOC_SCN_ACTION_COUNT ||
        ctx.trace_count != 2u * SOC_SCN_ACTION_COUNT ||
        ctx.allocated != 7u || !ctx.initialized || ctx.copies != 2u ||
        !ctx.checked) {
        *evidence = 0xd0000025u;
        return 37;
    }
    /* Retain allocations until passive NoC monitors have observed quiescence.
     * A C driver_done or flow PASS cannot attest AXI completion by itself.
     */
    *evidence = 0x600dc0deu;
    return 0;
}
