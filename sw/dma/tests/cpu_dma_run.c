/* CPU0 C application executed by the real PicoRV32 during RUN.
 * No BFM preload, no direct 32-bit CPU load from >4-GiB model windows.
 * Physical pools and CSRs come from config-derived compile definitions.
 */
#include "../dma.h"
#include "../../common/memory_pool.h"
#include "../../common/memory_pattern.h"
#include "../../common/test_flow.h"
#include <stdint.h>
#include <stddef.h>

#ifndef SOC_CPU0_SRAM
#error "config-derived SOC_CPU0_SRAM missing"
#endif
#ifndef SOC_CPU1_SRAM
#error "config-derived SOC_CPU1_SRAM missing"
#endif
#ifndef SOC_DMA0_CSR
#error "config-derived SOC_DMA0_CSR missing"
#endif
#ifndef SOC_DDR_BASE
#error "config-derived SOC_DDR_BASE missing"
#endif
#ifndef SOC_HBM_BASE
#error "config-derived SOC_HBM_BASE missing"
#endif
#ifndef SOC_MODEL_BYTES
#error "config-derived SOC_MODEL_BYTES missing"
#endif
#ifndef SOC_MAILBOX
#error "config-derived SOC_MAILBOX missing"
#endif

#define SOURCE_OFF 0x2000u
#define DESCRIPTOR_OFF 0x1000u
#define TARGET_RESERVE 0x100u
#define PAYLOAD_BYTES 64u
#define PAYLOAD_PATTERN_SEED 0x35u
#define STATUS_OFFSET 0x40u
#define TESTFLOW_OFFSET 0x5cu /* reserved final word of 2-CPU mailbox */

__attribute__((used, noinline))
int cpu_dma_run(void) {
    volatile uint32_t * const evidence =
        (volatile uint32_t *)(uintptr_t)(SOC_MAILBOX + STATUS_OFFSET);
    *evidence = 0xd0000000u;
    /* One writer, one physical MMIO trace word, separate from runtime
     * allocator telemetry and the CPU0 DONE state. Real AXI monitor is
     * authoritative; these markers alone do not prove DMA completion. */
    volatile uint32_t * const flow =
        (volatile uint32_t *)(uintptr_t)(SOC_MAILBOX + TESTFLOW_OFFSET);
    soc_flow_emit(flow,SOC_FLOW_RUN,SOC_FLOW_START,1,101); /* alloc_phys */
    soc_mem_region_t source, peer, ddr, hbm;
    soc_mem_allocation_t src={0}, peer_dst={0}, ddr_dst={0}, hbm_dst={0};
    soc_dma_arena_t desc;
    if (!soc_mem_region_init(&source, "cpu0.payload", SOC_MEM_SRAM,
            (uint64_t)SOC_CPU0_SRAM + SOURCE_OFF,
            0x2000u, (void *)(uintptr_t)(SOC_CPU0_SRAM + SOURCE_OFF)) ||
        !soc_mem_region_init(&peer, "cpu1.payload", SOC_MEM_SRAM,
            (uint64_t)SOC_CPU1_SRAM + SOURCE_OFF,
            0x2000u, (void *)(uintptr_t)(SOC_CPU1_SRAM + SOURCE_OFF)) ||
        !soc_mem_region_init(&ddr, "memory0.ddr0", SOC_MEM_DDR,
            (uint64_t)SOC_DDR_BASE + TARGET_RESERVE,
            SOC_MODEL_BYTES - TARGET_RESERVE, NULL) ||
        !soc_mem_region_init(&hbm, "memory0.hbm0", SOC_MEM_HBM,
            (uint64_t)SOC_HBM_BASE + TARGET_RESERVE,
            SOC_MODEL_BYTES - TARGET_RESERVE, NULL) ||
        !soc_dma_arena_init(&desc,
            (void *)(uintptr_t)(SOC_CPU0_SRAM + DESCRIPTOR_OFF),
            (uint64_t)SOC_CPU0_SRAM + DESCRIPTOR_OFF, 4096u)) {
        *evidence = 0xd0000001u; return 1;
    }
    if (!soc_mem_alloc(&source, PAYLOAD_BYTES, 64, &src) ||
        !soc_mem_alloc(&peer, PAYLOAD_BYTES, 64, &peer_dst) ||
        !soc_mem_alloc(&ddr, PAYLOAD_BYTES, 64, &ddr_dst) ||
        !soc_mem_alloc(&hbm, PAYLOAD_BYTES, 64, &hbm_dst)) {
        *evidence = 0xd0000002u; return 2;
    }
    /* Publish the CPU's ACTUAL runtime allocator results to reserved
     * mailbox telemetry. Python independently computes the same physical
     * addresses using configured model regions; this is not a preload.
     */
    volatile uint32_t * const allocation_report =
        (volatile uint32_t *)(uintptr_t)(SOC_MAILBOX + STATUS_OFFSET + 4u);
    allocation_report[0] = (uint32_t)src.phys;
    allocation_report[1] = (uint32_t)peer_dst.phys;
    allocation_report[2] = (uint32_t)ddr_dst.phys;
    allocation_report[3] = (uint32_t)(ddr_dst.phys >> 32);
    allocation_report[4] = (uint32_t)hbm_dst.phys;
    allocation_report[5] = (uint32_t)(hbm_dst.phys >> 32);
    soc_flow_emit(flow,SOC_FLOW_RUN,SOC_FLOW_PASS,1,101); /* alloc_phys */

#ifdef SOC_PCIE_SRAM
    /* Quick cross-subsystem proof only. Keep the complete HBM/DDR/peer
     * iDMA performance regression in the separate chip-cpu-dma test.
     * The two independent transfers per submission never depend on
     * ordering between in-flight DMA descriptors.
     */
    {
        soc_flow_emit(flow,SOC_FLOW_RUN,SOC_FLOW_START,1,104);
        soc_mem_fill_pattern(src.cpu_ptr,src.phys,PAYLOAD_BYTES,
                             PAYLOAD_PATTERN_SEED,SOC_PATTERN_COUNTER8);
        soc_mem_allocation_t from_host={0};
        if (!soc_mem_alloc(&peer,PAYLOAD_BYTES,64,&from_host)) {
            *evidence=0xd000000fu; return 15;
        }
        volatile uint8_t *readback=(volatile uint8_t *)(uintptr_t)from_host.phys;
        for(unsigned i=0;i<PAYLOAD_BYTES;++i) readback[i]=0;
        volatile uint32_t *csr=(volatile uint32_t *)(uintptr_t)SOC_DMA0_CSR;
        soc_dma_chain_t transfer={0};
        soc_dma_copy_t inbound[2]={
            {(uint64_t)SOC_PCIE_SRAM+0x500u,(uint64_t)SOC_DDR_BASE+0x800u,PAYLOAD_BYTES},
            {src.phys,ddr_dst.phys,PAYLOAD_BYTES}
        };
        if (!soc_dma_chain_build(&desc,inbound,2,true,&transfer) ||
            !soc_dma_mmio_submit(csr,transfer.head_phys)) {
            *evidence=0xd0000010u; return 16;
        }
        uint32_t status=0;
        if (!soc_dma_mmio_wait_irq(csr,200000u,&status)) {
            *evidence=0xd0000011u; return 17;
        }
        for(unsigned i=0;i<2;++i) {
            volatile const uint64_t *done=
                (volatile const uint64_t *)(const void *)&transfer.cpu_descs[i];
            if(*done!=UINT64_MAX) {*evidence=0xd0000012u;return 18;}
        }
        soc_dma_mmio_ack_irq(csr);
        uint32_t clear=0;
        unsigned attempts=0;
        for(;attempts<10000u;++attempts) {
            clear=csr[SOC_DMA_REG_STATUS/4u];
            if((clear & (SOC_DMA_STATUS_IRQ|SOC_DMA_STATUS_APB_BUSY))==0)break;
        }
        soc_dma_copy_t outbound[2]={
            {ddr_dst.phys,(uint64_t)SOC_PCIE_SRAM+0x600u,PAYLOAD_BYTES},
            {(uint64_t)SOC_DDR_BASE+0x800u,from_host.phys,PAYLOAD_BYTES}
        };
        if(attempts==10000u ||
            !soc_dma_chain_build(&desc,outbound,2,true,&transfer) ||
            !soc_dma_mmio_submit(csr,transfer.head_phys) ||
            !soc_dma_mmio_wait_irq(csr,200000u,&status)) {
            *evidence=0xd0000013u;return 19;
        }
        for(unsigned i=0;i<2;++i) {
            volatile const uint64_t *done=
                (volatile const uint64_t *)(const void *)&transfer.cpu_descs[i];
            if(*done!=UINT64_MAX) {*evidence=0xd0000014u;return 20;}
        }
        for(unsigned i=0;i<PAYLOAD_BYTES;++i) {
            if(readback[i]!=(uint8_t)(0x63u+13u*i)) {
                *evidence=0xd0000015u;return 21;
            }
        }
        soc_dma_mmio_ack_irq(csr);
        soc_flow_emit(flow,SOC_FLOW_RUN,SOC_FLOW_PASS,1,104);
        *evidence=0x600dc0deu;
        return 0;
    }
#endif
    volatile uint8_t * const dst =
        (volatile uint8_t *)(uintptr_t)peer_dst.phys;
    uint8_t * const src_bytes = (uint8_t *)src.cpu_ptr;
    /* Same byte recipe as BFM-side Python; fill CPU-addressable SRAM
     * through real stores. Remote DDR/HBM is only initialized by real DMA.
     */
    soc_mem_fill_pattern(src_bytes, src.phys, PAYLOAD_BYTES,
                         PAYLOAD_PATTERN_SEED, SOC_PATTERN_COUNTER8);
    for (unsigned i=0; i<PAYLOAD_BYTES; ++i) dst[i] = 0;
    soc_dma_copy_t ops[3] = {
        {src.phys, peer_dst.phys, PAYLOAD_BYTES},
        {src.phys, ddr_dst.phys, PAYLOAD_BYTES},
        {src.phys, hbm_dst.phys, PAYLOAD_BYTES}
    };
    soc_dma_chain_t chain={0};
    if (!soc_dma_chain_build(&desc, ops, 3, true, &chain)) {
        *evidence = 0xd0000003u; return 3;
    }
    volatile uint32_t *csr=(volatile uint32_t *)(uintptr_t)SOC_DMA0_CSR;
    *evidence = 0xd0000004u;
    soc_flow_emit(flow,SOC_FLOW_RUN,SOC_FLOW_START,1,102); /* dma_roundtrip */
    if (!soc_dma_mmio_submit(csr, chain.head_phys)) {
        *evidence = 0xd0000005u; return 5;
    }
    uint32_t status=0;
    if (!soc_dma_mmio_wait_irq(csr, 200000u, &status)) {
        *evidence = 0xd0000006u; return 6;
    }
    /* Check complete desc64 hardware writebacks, not just sticky IRQ. */
    for (unsigned i=0; i<3; ++i) {
        volatile const uint64_t *done =
            (volatile const uint64_t *)(const void *)&chain.cpu_descs[i];
        if (*done != UINT64_MAX) {
            *evidence = 0xd0000007u; return 7;
        }
    }
    soc_flow_emit(flow,SOC_FLOW_RUN,SOC_FLOW_START,1,103); /* verify_memory */
    if (soc_mem_check_pattern((const void *)(uintptr_t)peer_dst.phys,
                              src.phys, PAYLOAD_BYTES,
                              PAYLOAD_PATTERN_SEED, SOC_PATTERN_COUNTER8) !=
                              PAYLOAD_BYTES) {
        *evidence = 0xd0000008u; return 8;
    }
    soc_dma_mmio_ack_irq(csr);
    /* CPU cannot directly load data above 4 GiB. Do a second real DMA chain
     * back to separately allocated CPU-visible SRAM and check its contents.
     * This validates BOTH HBM and DDR model storage, not just AXI responses.
     */
    soc_mem_allocation_t from_ddr={0}, from_hbm={0};
    if (!soc_mem_alloc(&peer, PAYLOAD_BYTES, 64, &from_ddr) ||
        !soc_mem_alloc(&peer, PAYLOAD_BYTES, 64, &from_hbm)) {
        *evidence=0xd0000009u; return 9;
    }
    volatile uint8_t *ddr_copy=(volatile uint8_t *)(uintptr_t)from_ddr.phys;
    volatile uint8_t *hbm_copy=(volatile uint8_t *)(uintptr_t)from_hbm.phys;
    for(unsigned i=0; i<PAYLOAD_BYTES; ++i) {
        ddr_copy[i]=0; hbm_copy[i]=0;
    }
    soc_dma_copy_t reverse[2]={
        {ddr_dst.phys,from_ddr.phys,PAYLOAD_BYTES},
        {hbm_dst.phys,from_hbm.phys,PAYLOAD_BYTES}
    };
    if (!soc_dma_chain_build(&desc, reverse, 2, true, &chain)) {
        *evidence=0xd000000au; return 10;
    }
    /* IRQ_ACK CSR may take several cycles to reach the real APB bridge. */
    uint32_t clear=0;
    unsigned attempts=0;
    for(; attempts<10000u; ++attempts) {
        clear=csr[SOC_DMA_REG_STATUS/4u];
        if ((clear & (SOC_DMA_STATUS_IRQ | SOC_DMA_STATUS_APB_BUSY))==0) break;
    }
    if(attempts==10000u || !soc_dma_mmio_submit(csr,chain.head_phys)) {
        *evidence=0xd000000bu; return 11;
    }
    if(!soc_dma_mmio_wait_irq(csr,200000u,&status)) {
        *evidence=0xd000000cu; return 12;
    }
    for(unsigned i=0; i<2; ++i) {
        volatile const uint64_t *done=
            (volatile const uint64_t *)(const void *)&chain.cpu_descs[i];
        if(*done!=UINT64_MAX) {
            *evidence=0xd000000du; return 13;
        }
    }
    if (soc_mem_check_pattern((const void *)(uintptr_t)from_ddr.phys,
                              src.phys, PAYLOAD_BYTES,
                              PAYLOAD_PATTERN_SEED, SOC_PATTERN_COUNTER8) != PAYLOAD_BYTES ||
        soc_mem_check_pattern((const void *)(uintptr_t)from_hbm.phys,
                              src.phys, PAYLOAD_BYTES,
                              PAYLOAD_PATTERN_SEED, SOC_PATTERN_COUNTER8) != PAYLOAD_BYTES) {
        *evidence=0xd000000eu; return 14;
    }
    soc_dma_mmio_ack_irq(csr);

    /* Retain descriptors and all physical buffers to simulation end;
     * interrupt/writebacks alone do not prove backend globally idle.
     */
    soc_flow_emit(flow,SOC_FLOW_RUN,SOC_FLOW_PASS,1,103);
    soc_flow_emit(flow,SOC_FLOW_RUN,SOC_FLOW_PASS,1,102);
    *evidence = 0x600dc0deu;
    return 0;
}
