#ifndef SOC_ETH_QUEUE_ABI_H
#define SOC_ETH_QUEUE_ABI_H
#include <stdint.h>
#include <stddef.h>

/* ABI version 1.0: all addresses in physical address space and 32-byte
 * ring descriptors. Register accesses are little-endian, word-aligned.
 * This is a software-visible contract; completion records and DMA are not
 * emitted by ethernet_queue_ctrl.sv. They are written by future engines.
 */
#define ETHQ_ABI_MAGIC            0x45544851u
#define ETHQ_ABI_VERSION          0x00010000u
#define ETHQ_DESC_BYTES           32u
#define ETHQ_CPL_BYTES            32u
#define ETHQ_DEFAULT_RING_LOG2    4u
#define ETHQ_DEFAULT_POLICIES     4u

#define ETHQ_REG_MAGIC            0x00u
#define ETHQ_REG_VERSION          0x04u
#define ETHQ_REG_ENABLE           0x08u
#define ETHQ_REG_CAPS             0x0cu
#define ETHQ_REG_QUEUE_SELECT     0x10u
#define ETHQ_REG_RX_DESC_LO       0x20u
#define ETHQ_REG_RX_DESC_HI       0x24u
#define ETHQ_REG_RX_PRODUCER      0x28u
#define ETHQ_REG_RX_CONSUMER      0x2cu
#define ETHQ_REG_RX_CQ_LO         0x30u
#define ETHQ_REG_RX_CQ_HI         0x34u
#define ETHQ_REG_RX_CQ_PRODUCER   0x38u
#define ETHQ_REG_RX_CQ_CONSUMER   0x3cu
#define ETHQ_REG_TX_DESC_LO       0x40u
#define ETHQ_REG_TX_DESC_HI       0x44u
#define ETHQ_REG_TX_PRODUCER      0x48u
#define ETHQ_REG_TX_CONSUMER      0x4cu
#define ETHQ_REG_TX_CQ_LO         0x50u
#define ETHQ_REG_TX_CQ_HI         0x54u
#define ETHQ_REG_TX_CQ_PRODUCER   0x58u
#define ETHQ_REG_TX_CQ_CONSUMER   0x5cu
#define ETHQ_REG_POLICY_SELECT    0x70u
#define ETHQ_REG_MATCH_ETHERTYPE  0x74u
#define ETHQ_REG_MASK_ETHERTYPE   0x78u
#define ETHQ_REG_MATCH_UDP_PORT   0x7cu
#define ETHQ_REG_MASK_UDP_PORT    0x80u
#define ETHQ_REG_POLICY_CONTROL   0x84u
#define ETHQ_REG_IRQ_STATUS       0x90u
#define ETHQ_REG_ERRORS           0x94u
#define ETHQ_REG_DROP_COUNT       0x98u
#define ETHQ_REG_MULTI_COUNT      0x9cu
#define ETHQ_REG_BUSY             0xa0u

#define ETHQ_ENABLE_RX            0x01u
#define ETHQ_ENABLE_TX            0x02u
#define ETHQ_POLICY_VALID         0x01u
#define ETHQ_POLICY_REQUIRE_UDP   0x02u
#define ETHQ_POLICY_DROP          0x04u
#define ETHQ_POLICY_QUEUE_SHIFT   8u

#define ETHQ_ERROR_MULTI_MATCH    0x01u
#define ETHQ_ERROR_NO_BUFFER      0x02u
#define ETHQ_ERROR_BAD_CONFIG     0x04u
#define ETHQ_ERROR_COMPLETION     0x08u
#define ETHQ_ERROR_NO_MATCH       0x10u
#define ETHQ_ERROR_CQ_FULL        0x20u
#define ETHQ_ERROR_BAD_QUEUE      0x40u

/* RX buffers are posted by software. The header never determines dst_addr.
 * Software's region allocator must authorize addr+capacity and retain this
 * allocation until the written completion is consumed.
 */
typedef struct {
    uint64_t dst_addr;
    uint32_t capacity;
    uint32_t cookie;
    uint32_t flags;
    uint32_t region_id;
    uint64_t reserved;
} ethq_rx_desc_t;

/* TX reads a preconstructed Ethernet frame, excluding preamble and FCS. */
typedef struct {
    uint64_t src_addr;
    uint32_t length;
    uint32_t cookie;
    uint32_t flags;
    uint32_t reserved0;
    uint64_t reserved1;
} ethq_tx_desc_t;

/* RX/TX completion records use the same layout. Final status requires both
 * DMA AXI completion and packet endpoint status as appropriate.
 */
typedef struct {
    uint64_t cookie;
    uint32_t length;
    uint32_t status;
    uint32_t policy_id;
    uint32_t queue_id;
    uint64_t reserved;
} ethq_completion_t;

_Static_assert(sizeof(ethq_rx_desc_t) == ETHQ_DESC_BYTES, "RX ABI size");
_Static_assert(sizeof(ethq_tx_desc_t) == ETHQ_DESC_BYTES, "TX ABI size");
_Static_assert(sizeof(ethq_completion_t) == ETHQ_CPL_BYTES, "CQ ABI size");
_Static_assert(offsetof(ethq_rx_desc_t, capacity) == 8, "RX ABI offset");
_Static_assert(offsetof(ethq_tx_desc_t, length) == 8, "TX ABI offset");

#endif
