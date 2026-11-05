#ifndef SOC_ETH_QUEUE_DRIVER_H
#define SOC_ETH_QUEUE_DRIVER_H
#include <stdbool.h>
#include <stdint.h>
#include "eth_queue_abi.h"

/* All MMIO side effects here are CPU/AXI-Lite 32-bit words. These routines
 * use the same already-initialized physical buffer allocations as
 * sw/common/memory_pool.[ch]; they never allocate or preload memory.
 */
typedef struct {
    volatile uint32_t *csr;
    uint32_t rx_queues, tx_queues;
    uint32_t ring_log2, policy_entries;
} ethq_device_t;

bool ethq_init(ethq_device_t *dev, volatile uint32_t *csr);
bool ethq_select_queue(ethq_device_t *dev, uint32_t queue);
bool ethq_configure_ring(ethq_device_t *dev, bool rx, uint64_t desc_base,
                         uint64_t completion_base);
bool ethq_set_policy(ethq_device_t *dev, uint32_t rule,
                     uint16_t ethertype, uint16_t ethertype_mask,
                     bool require_udp, uint16_t udp_port,
                     uint16_t udp_mask, uint32_t queue, bool drop);
bool ethq_enable(ethq_device_t *dev, bool rx, bool tx);
bool ethq_post_rx(ethq_device_t *dev, uint32_t producer);
bool ethq_post_tx(ethq_device_t *dev, uint32_t producer);
uint32_t ethq_rx_available(const ethq_device_t *dev);
uint32_t ethq_tx_available(const ethq_device_t *dev);
void ethq_ack_irq(ethq_device_t *dev, uint32_t flags);
#endif
