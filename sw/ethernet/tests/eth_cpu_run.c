/* Real PicoRV32 CPU0 Ethernet MVP: queues programmed over Config NoC.
 * No CPU0 AXI BFM, no backdoor SRAM preload, no synthetic completion.
 * The external testbench only supplies/sinks GMII line traffic.
 */
#include "../eth_queue_abi.h"
#include "../../common/test_flow.h"
#include <stdint.h>

#ifndef SOC_ETH_SRAM
#error "Ethernet physical SRAM base must come from config"
#endif
#ifndef SOC_ETH_CTRL
#error "Ethernet CSR physical base must come from config"
#endif
#ifndef SOC_MAILBOX
#error "CPU0 mailbox must come from shared boot layout"
#endif

#define ETH_RX_RING  (SOC_ETH_SRAM + 0x1000u)
#define ETH_RX_CQ    (SOC_ETH_SRAM + 0x1200u)
#define ETH_TX_RING  (SOC_ETH_SRAM + 0x1400u)
#define ETH_TX_CQ    (SOC_ETH_SRAM + 0x1600u)
#define ETH_RX_BUF   (SOC_ETH_SRAM + 0x2000u)
#define ETH_TX_BUF   (SOC_ETH_SRAM + 0x2100u)
#define LEN          85u
#define RX_COOKIE    0xc0febabeu
#define TX_COOKIE    0xfeedcafeu
#define WAIT_CYCLES  20000u

/* The same 85-byte frame used by the established GMII golden encoder.
 * Full IPv4/UDP Ethernet frame, no preamble, SFD or FCS (MAC owns FCS).
 */
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

static inline void reg_write(unsigned off, uint32_t data) {
    volatile uint32_t *r = (volatile uint32_t *)(uintptr_t)(SOC_ETH_CTRL+off);
    *r = data;
}
static inline uint32_t reg_read(unsigned off) {
    volatile uint32_t *r = (volatile uint32_t *)(uintptr_t)(SOC_ETH_CTRL+off);
    return *r;
}
static void descriptor(uint32_t base, uint32_t buffer, uint32_t len,
                       uint32_t cookie) {
    volatile uint32_t *d = (volatile uint32_t *)(uintptr_t)base;
    for (unsigned i=0;i<8;++i) d[i]=0u;
    d[0]=buffer; d[1]=0u; d[2]=len; d[3]=cookie;
}
static int cq_check(uint32_t address, uint32_t cookie) {
    volatile uint32_t *q = (volatile uint32_t *)(uintptr_t)address;
    return q[0]==cookie && q[1]==0 && q[2]==LEN && q[3]==0 &&
           q[4]==0 && q[6]==0 && q[7]==0;
}
static int wait_producer(uint32_t off) {
    for(unsigned n=0;n<WAIT_CYCLES;++n)
        if(reg_read(off)==1u) return 1;
    return 0;
}
static int fail(volatile uint32_t *evidence,volatile uint32_t *flow,
                unsigned code) {
    *evidence=0xe700f000u|code;
    soc_flow_emit(flow,SOC_FLOW_RUN,SOC_FLOW_FAIL,1,201);
    return (int)code;
}

/* Called by existing cold-boot ROM's CPU0 C hook during RUN. */
__attribute__((used,noinline,section(".text.cpu_dma_run")))
int cpu_dma_run(void) {
    volatile uint32_t * const evidence =
        (volatile uint32_t *)(uintptr_t)(SOC_MAILBOX+0x40u);
    volatile uint32_t * const flow =
        (volatile uint32_t *)(uintptr_t)(SOC_MAILBOX+0x5cu);
    *evidence=0xe7000000u;
    soc_flow_emit(flow,SOC_FLOW_RUN,SOC_FLOW_START,1,201);

    /* CPU0 prepares physical memory only through its own real stores. */
    descriptor(ETH_RX_RING,ETH_RX_BUF,2048u,RX_COOKIE);
    descriptor(ETH_TX_RING,ETH_TX_BUF,LEN,TX_COOKIE);
    volatile uint8_t * const dst=(volatile uint8_t *)(uintptr_t)ETH_TX_BUF;
    for(unsigned i=0;i<LEN;++i) dst[i]=golden[i];

    if(reg_read(ETHQ_REG_MAGIC)!=ETHQ_ABI_MAGIC ||
       reg_read(ETHQ_REG_VERSION)!=ETHQ_ABI_VERSION)
        return fail(evidence,flow,1);
    reg_write(ETHQ_REG_QUEUE_SELECT,0);
    reg_write(ETHQ_REG_RX_DESC_LO,ETH_RX_RING);
    reg_write(ETHQ_REG_RX_DESC_HI,0);
    reg_write(ETHQ_REG_RX_CQ_LO,ETH_RX_CQ);
    reg_write(ETHQ_REG_RX_CQ_HI,0);
    reg_write(ETHQ_REG_TX_DESC_LO,ETH_TX_RING);
    reg_write(ETHQ_REG_TX_DESC_HI,0);
    reg_write(ETHQ_REG_TX_CQ_LO,ETH_TX_CQ);
    reg_write(ETHQ_REG_TX_CQ_HI,0);
    reg_write(ETHQ_REG_POLICY_SELECT,0);
    reg_write(ETHQ_REG_MATCH_ETHERTYPE,0x0800u);
    reg_write(ETHQ_REG_MASK_ETHERTYPE,0xffffu);
    reg_write(ETHQ_REG_MATCH_UDP_PORT,6000u);
    reg_write(ETHQ_REG_MASK_UDP_PORT,0xffffu);
    reg_write(ETHQ_REG_POLICY_CONTROL,ETHQ_POLICY_VALID|ETHQ_POLICY_REQUIRE_UDP);
    reg_write(ETHQ_REG_ENABLE,ETHQ_ENABLE_RX|ETHQ_ENABLE_TX);
    reg_write(ETHQ_REG_RX_PRODUCER,1);
    if(reg_read(ETHQ_REG_RX_PRODUCER)!=1u)
        return fail(evidence,flow,2);
    /* Testbench waits for accepted physical mailbox write, not guessed time. */
    *evidence=0xe7000001u;
    soc_flow_emit(flow,SOC_FLOW_RUN,SOC_FLOW_PASS,1,201);
    soc_flow_emit(flow,SOC_FLOW_RUN,SOC_FLOW_START,1,202);
    if(!wait_producer(ETHQ_REG_RX_CQ_PRODUCER))
        return fail(evidence,flow,3);
    if(!(reg_read(ETHQ_REG_IRQ_STATUS)&1u) ||
       reg_read(ETHQ_REG_RX_CONSUMER)!=1u ||
       !cq_check(ETH_RX_CQ,RX_COOKIE))
        return fail(evidence,flow,4);
    volatile const uint8_t * const received =
        (volatile const uint8_t *)(uintptr_t)ETH_RX_BUF;
    for(unsigned i=0;i<LEN;++i)
        if(received[i]!=golden[i]) return fail(evidence,flow,5);
    reg_write(ETHQ_REG_RX_CQ_CONSUMER,1);
    reg_write(ETHQ_REG_IRQ_STATUS,1);
    if(reg_read(ETHQ_REG_IRQ_STATUS)&1u)
        return fail(evidence,flow,6);
    *evidence=0xe7000002u;
    soc_flow_emit(flow,SOC_FLOW_RUN,SOC_FLOW_PASS,1,202);
    soc_flow_emit(flow,SOC_FLOW_RUN,SOC_FLOW_START,1,203);
    reg_write(ETHQ_REG_TX_PRODUCER,1);
    if(!wait_producer(ETHQ_REG_TX_CQ_PRODUCER))
        return fail(evidence,flow,7);
    if(!(reg_read(ETHQ_REG_IRQ_STATUS)&2u) ||
       reg_read(ETHQ_REG_TX_CONSUMER)!=1u ||
       !cq_check(ETH_TX_CQ,TX_COOKIE))
        return fail(evidence,flow,8);
    reg_write(ETHQ_REG_TX_CQ_CONSUMER,1);
    reg_write(ETHQ_REG_IRQ_STATUS,2);
    if(reg_read(ETHQ_REG_IRQ_STATUS)!=0u ||
       reg_read(ETHQ_REG_ERRORS)!=0u ||
       reg_read(ETHQ_REG_RX_CQ_CONSUMER)!=1u ||
       reg_read(ETHQ_REG_TX_CQ_CONSUMER)!=1u)
        return fail(evidence,flow,9);
    soc_flow_emit(flow,SOC_FLOW_RUN,SOC_FLOW_PASS,1,203);
    *evidence=0xe700600du;
    return 0;
}
