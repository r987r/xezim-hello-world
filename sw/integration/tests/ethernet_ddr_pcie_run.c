/* #34 one-run real CPU0 + GMII Ethernet + LiteDRAM + PULP iDMA + PCIe.
 * The RX queue descriptor, not the incoming Ethernet header, chooses DDR.
 * No testbench loads DDR/SRAM or drives CPU-side AXI; the modeled PCIe RC
 * BAR-pulls the DMA-produced staging buffer after the CPU has checked CQ.
 */
#include "../../ethernet/eth_queue_abi.h"
#include "../../dma/dma.h"
#include "../../common/test_flow.h"
#include <stdint.h>
#include <stddef.h>
#include <limits.h>

/* Standalone RV32I C uses -nostdlib. LLVM may lower descriptor/array
 * initialization to memcpy/memset despite -ffreestanding. Supply only the
 * ISO C byte primitives here, with volatile byte accesses to prevent
 * compiler loop-idiom reconstitution or recursive libcalls. Never linked
 * into non-composite firmware or substituted for hardware transfers. */
__attribute__((used, noinline))
void *memcpy(void *destination, const void *source, size_t size) {
    volatile unsigned char *d = (volatile unsigned char *)destination;
    const volatile unsigned char *s = (const volatile unsigned char *)source;
    for (size_t i = 0; i < size; ++i) d[i] = s[i];
    return destination;
}
__attribute__((used, noinline))
void *memset(void *destination, int value, size_t size) {
    volatile unsigned char *d = (volatile unsigned char *)destination;
    for (size_t i = 0; i < size; ++i) d[i] = (unsigned char)value;
    return destination;
}

#if !defined(SOC_ETH_SRAM) || !defined(SOC_ETH_CTRL) || !defined(SOC_DDR_BASE) || \
    !defined(SOC_DMA0_CSR) || !defined(SOC_CPU0_SRAM) || !defined(SOC_CPU1_SRAM) || \
    !defined(SOC_PCIE_SRAM) || !defined(SOC_MAILBOX)
#error "Missing configuration-derived combined SoC physical addresses"
#endif

#define LEN 85u
#define DDR_RX_PHYS ((uint64_t)SOC_DDR_BASE + 0x1000u)
#define RX_RING (SOC_ETH_SRAM + 0x1000u)
#define RX_CQ   (SOC_ETH_SRAM + 0x1200u)
#define TX_RING (SOC_ETH_SRAM + 0x1400u)
#define TX_CQ   (SOC_ETH_SRAM + 0x1600u)
#define TX_BUF  (SOC_ETH_SRAM + 0x2100u)
#define PCIE_STAGE (SOC_PCIE_SRAM + 0x600u)
#define CPU_READBACK (SOC_CPU1_SRAM + 0x2000u)
#define RX_COOKIE 0xc0febabeu
#define TX_COOKIE 0xfeedcafeu
#define ETH_TIMEOUT 50000u

static const uint8_t golden[LEN] = {
  0x02,0x50,0xb6,0x00,0x00,0x22,0x02,0x50,0xb6,0x00,0x00,0x11,
  0x08,0x00,0x45,0x00,0x00,0x47,0x00,0x00,0x00,0x00,0x40,0x11,
  0x2a,0x2e,0x0a,0x14,0x1e,0x28,0x0a,0x14,0x1e,0x29,0x30,0x39,
  0x17,0x70,0x00,0x33,0x00,0x00,0x09,0x10,0x17,0x1e,0x25,0x2c,
  0x33,0x3a,0x41,0x48,0x4f,0x56,0x5d,0x64,0x6b,0x72,0x79,
  0x80,0x87,0x8e,0x95,0x9c,0xa3,0xaa,0xb1,0xb8,0xbf,0xc6,
  0xcd,0xd4,0xdb,0xe2,0xe9,0xf0,0xf7,0xfe,0x05,0x0c,0x13,
  0x1a,0x21,0x28,0x2f
};

static inline void wr(uint32_t off, uint32_t v) {
    *(volatile uint32_t *)(uintptr_t)(SOC_ETH_CTRL + off) = v;
}
static inline uint32_t rd(uint32_t off) {
    return *(volatile uint32_t *)(uintptr_t)(SOC_ETH_CTRL + off);
}
static void descriptor(uint32_t base, uint64_t phys, uint32_t length,
                       uint32_t cookie) {
    volatile uint32_t *d = (volatile uint32_t *)(uintptr_t)base;
    for (unsigned i = 0; i < 8; ++i) d[i] = 0;
    d[0] = (uint32_t)phys;
    d[1] = (uint32_t)(phys >> 32);
    d[2] = length;
    d[3] = cookie;
}
static int completion(uint32_t address, uint32_t cookie) {
    volatile uint32_t *q = (volatile uint32_t *)(uintptr_t)address;
    return q[0] == cookie && q[1] == 0 && q[2] == LEN &&
           q[3] == 0 && q[4] == 0 && q[5] == 0 &&
           q[6] == 0 && q[7] == 0;
}
static int wait_cq(uint32_t off) {
    for (unsigned n = 0; n < ETH_TIMEOUT; ++n)
        if (rd(off) == 1u) return 1;
    return 0;
}
static int fail(volatile uint32_t *evidence, volatile uint32_t *flow,
                unsigned step, unsigned code) {
    *evidence = 0xe700f000u | code;
    soc_flow_emit(flow, SOC_FLOW_RUN, SOC_FLOW_FAIL, 1, step);
    return (int)code;
}
__attribute__((used, noinline, section(".text.cpu_dma_run")))
int cpu_dma_run(void) {
    volatile uint32_t *const evidence =
        (volatile uint32_t *)(uintptr_t)(SOC_MAILBOX + 0x40u);
    volatile uint32_t *const flow =
        (volatile uint32_t *)(uintptr_t)(SOC_MAILBOX + 0x5cu);
    *evidence = 0xe7000000u;
    soc_flow_emit(flow, SOC_FLOW_RUN, SOC_FLOW_START, 1, 201);

    if (rd(ETHQ_REG_MAGIC) != ETHQ_ABI_MAGIC ||
        rd(ETHQ_REG_VERSION) != ETHQ_ABI_VERSION)
        return fail(evidence, flow, 201, 1);
    /* Both 64-bit addresses are written by the real 32-bit CPU to SRAM. */
    descriptor(RX_RING, DDR_RX_PHYS, 2048u, RX_COOKIE);
    descriptor(TX_RING, (uint64_t)TX_BUF, LEN, TX_COOKIE);
    volatile uint8_t *tx = (volatile uint8_t *)(uintptr_t)TX_BUF;
    for (unsigned i = 0; i < LEN; ++i) tx[i] = 0; /* DMA must fill it */
    wr(ETHQ_REG_QUEUE_SELECT, 0);
    wr(ETHQ_REG_RX_DESC_LO, (uint32_t)RX_RING);
    wr(ETHQ_REG_RX_DESC_HI, 0);
    wr(ETHQ_REG_RX_CQ_LO, (uint32_t)RX_CQ);
    wr(ETHQ_REG_RX_CQ_HI, 0);
    wr(ETHQ_REG_TX_DESC_LO, (uint32_t)TX_RING);
    wr(ETHQ_REG_TX_DESC_HI, 0);
    wr(ETHQ_REG_TX_CQ_LO, (uint32_t)TX_CQ);
    wr(ETHQ_REG_TX_CQ_HI, 0);
    wr(ETHQ_REG_POLICY_SELECT, 0);
    wr(ETHQ_REG_MATCH_ETHERTYPE, 0x0800u);
    wr(ETHQ_REG_MASK_ETHERTYPE, 0xffffu);
    wr(ETHQ_REG_MATCH_UDP_PORT, 6000u);
    wr(ETHQ_REG_MASK_UDP_PORT, 0xffffu);
    wr(ETHQ_REG_POLICY_CONTROL, ETHQ_POLICY_VALID | ETHQ_POLICY_REQUIRE_UDP);
    wr(ETHQ_REG_ENABLE, ETHQ_ENABLE_RX | ETHQ_ENABLE_TX);
    wr(ETHQ_REG_RX_PRODUCER, 1);
    if (rd(ETHQ_REG_RX_PRODUCER) != 1u)
        return fail(evidence, flow, 201, 2);
    *evidence = 0xe7000001u; /* simulator only supplies GMII now */
    soc_flow_emit(flow, SOC_FLOW_RUN, SOC_FLOW_PASS, 1, 201);
    soc_flow_emit(flow, SOC_FLOW_RUN, SOC_FLOW_START, 1, 202);
    if (!wait_cq(ETHQ_REG_RX_CQ_PRODUCER))
        return fail(evidence, flow, 202, 3);
    if (!(rd(ETHQ_REG_IRQ_STATUS) & 1u) ||
        rd(ETHQ_REG_RX_CONSUMER) != 1u ||
        !completion(RX_CQ, RX_COOKIE))
        return fail(evidence, flow, 202, 4);
    wr(ETHQ_REG_RX_CQ_CONSUMER, 1);
    wr(ETHQ_REG_IRQ_STATUS, 1);
    if (rd(ETHQ_REG_IRQ_STATUS) & 1u)
        return fail(evidence, flow, 202, 5);
    soc_flow_emit(flow, SOC_FLOW_RUN, SOC_FLOW_PASS, 1, 202);

    /* Above-4GiB DDR can only be read by PULP iDMA, never by RV32I CPU.
     * Three independent destinations: host BAR staging, outbound GMII TX,
     * and CPU1 SRAM for real CPU byte-by-byte equality and CQ checks.
     */
    soc_flow_emit(flow, SOC_FLOW_RUN, SOC_FLOW_START, 1, 204);
    soc_dma_arena_t arena;
    if (!soc_dma_arena_init(&arena,
        (void *)(uintptr_t)(SOC_CPU0_SRAM + 0x1000u),
        (uint64_t)SOC_CPU0_SRAM + 0x1000u, 4096u))
        return fail(evidence, flow, 204, 6);
    volatile uint8_t *check = (volatile uint8_t *)(uintptr_t)CPU_READBACK;
    for (unsigned i = 0; i < LEN; ++i) check[i] = 0;
    soc_dma_copy_t ops[3] = {
        {DDR_RX_PHYS, (uint64_t)PCIE_STAGE, LEN},
        {DDR_RX_PHYS, (uint64_t)TX_BUF, LEN},
        {DDR_RX_PHYS, (uint64_t)CPU_READBACK, LEN}
    };
    soc_dma_chain_t chain = {0};
    volatile uint32_t *csr = (volatile uint32_t *)(uintptr_t)SOC_DMA0_CSR;
    if (!soc_dma_chain_build(&arena, ops, 3, true, &chain) ||
        !soc_dma_mmio_submit(csr, chain.head_phys))
        return fail(evidence, flow, 204, 7);
    uint32_t dma_status = 0;
    if (!soc_dma_mmio_wait_irq(csr, 200000u, &dma_status))
        return fail(evidence, flow, 204, 8);
    for (unsigned i = 0; i < 3; ++i) {
        volatile const uint64_t *done =
            (volatile const uint64_t *)(const void *)&chain.cpu_descs[i];
        if (*done != UINT64_MAX)
            return fail(evidence, flow, 204, 9);
    }
    for (unsigned i = 0; i < LEN; ++i) {
        if (check[i] != golden[i] || tx[i] != golden[i])
            return fail(evidence, flow, 204, 10);
    }
    soc_dma_mmio_ack_irq(csr);
    *evidence = 0xe7000002u;
    soc_flow_emit(flow, SOC_FLOW_RUN, SOC_FLOW_PASS, 1, 204);

    soc_flow_emit(flow, SOC_FLOW_RUN, SOC_FLOW_START, 1, 203);
    wr(ETHQ_REG_TX_PRODUCER, 1);
    if (!wait_cq(ETHQ_REG_TX_CQ_PRODUCER))
        return fail(evidence, flow, 203, 11);
    if (!(rd(ETHQ_REG_IRQ_STATUS) & 2u) ||
        rd(ETHQ_REG_TX_CONSUMER) != 1u ||
        !completion(TX_CQ, TX_COOKIE))
        return fail(evidence, flow, 203, 12);
    wr(ETHQ_REG_TX_CQ_CONSUMER, 1);
    wr(ETHQ_REG_IRQ_STATUS, 2);
    if (rd(ETHQ_REG_IRQ_STATUS) != 0 ||
        rd(ETHQ_REG_ERRORS) != 0 ||
        rd(ETHQ_REG_RX_CQ_CONSUMER) != 1 ||
        rd(ETHQ_REG_TX_CQ_CONSUMER) != 1)
        return fail(evidence, flow, 203, 13);
    soc_flow_emit(flow, SOC_FLOW_RUN, SOC_FLOW_PASS, 1, 203);
    *evidence = 0xe700600du; /* observed by real full_chip_tb */
    return 0;
}
