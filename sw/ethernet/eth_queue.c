#include "eth_queue.h"

static uint32_t rd(const ethq_device_t *d, unsigned off) {
    return d->csr[off >> 2];
}
static void wr(const ethq_device_t *d, unsigned off, uint32_t value) {
    d->csr[off >> 2] = value;
}
static void publish(void) {
#if defined(__GNUC__) || defined(__clang__)
    __atomic_thread_fence(__ATOMIC_RELEASE);
#else
#error "Queue descriptor publication requires a CPU release fence"
#endif
}
bool ethq_init(ethq_device_t *d, volatile uint32_t *csr) {
    if (!d || !csr) return false;
    d->csr = csr;
    if (rd(d, ETHQ_REG_MAGIC) != ETHQ_ABI_MAGIC ||
        rd(d, ETHQ_REG_VERSION) != ETHQ_ABI_VERSION) return false;
    uint32_t caps = rd(d, ETHQ_REG_CAPS);
    d->rx_queues = caps & 255u;
    d->tx_queues = (caps >> 8) & 255u;
    d->ring_log2 = (caps >> 16) & 255u;
    d->policy_entries = (caps >> 24) & 255u;
    return d->rx_queues > 0 && d->tx_queues > 0 &&
           d->ring_log2 > 0 && d->ring_log2 < 16 &&
           d->policy_entries > 0;
}
bool ethq_select_queue(ethq_device_t *d, uint32_t q) {
    if (!d || !d->csr || q >= d->rx_queues || q >= d->tx_queues)
        return false;
    wr(d, ETHQ_REG_QUEUE_SELECT, q);
    return true;
}
bool ethq_configure_ring(ethq_device_t *d, bool rx, uint64_t ring,
                         uint64_t cpl) {
    if (!d || !d->csr || !ring || !cpl || (ring & 31u) || (cpl & 31u) ||
        rd(d, ETHQ_REG_ENABLE) != 0) return false;
    unsigned base = rx ? ETHQ_REG_RX_DESC_LO : ETHQ_REG_TX_DESC_LO;
    unsigned cq = rx ? ETHQ_REG_RX_CQ_LO : ETHQ_REG_TX_CQ_LO;
    wr(d, base, (uint32_t)ring);
    wr(d, base + 4, (uint32_t)(ring >> 32));
    wr(d, cq, (uint32_t)cpl);
    wr(d, cq + 4, (uint32_t)(cpl >> 32));
    return true;
}
bool ethq_set_policy(ethq_device_t *d, uint32_t rule,
                     uint16_t et, uint16_t mask, bool require_udp,
                     uint16_t port, uint16_t port_mask,
                     uint32_t queue, bool drop) {
    if (!d || !d->csr || rule >= d->policy_entries ||
        queue >= d->rx_queues || rd(d, ETHQ_REG_ENABLE)) return false;
    wr(d, ETHQ_REG_POLICY_SELECT, rule);
    wr(d, ETHQ_REG_MATCH_ETHERTYPE, et);
    wr(d, ETHQ_REG_MASK_ETHERTYPE, mask);
    wr(d, ETHQ_REG_MATCH_UDP_PORT, port);
    wr(d, ETHQ_REG_MASK_UDP_PORT, port_mask);
    wr(d, ETHQ_REG_POLICY_CONTROL,
       ETHQ_POLICY_VALID | (require_udp ? ETHQ_POLICY_REQUIRE_UDP : 0u) |
       (drop ? ETHQ_POLICY_DROP : 0u) | (queue << ETHQ_POLICY_QUEUE_SHIFT));
    return true;
}
bool ethq_enable(ethq_device_t *d, bool rx, bool tx) {
    if (!d || !d->csr) return false;
    wr(d, ETHQ_REG_ENABLE, (rx ? ETHQ_ENABLE_RX : 0u) |
                           (tx ? ETHQ_ENABLE_TX : 0u));
    return true;
}
bool ethq_post_rx(ethq_device_t *d, uint32_t producer) {
    if (!d || !d->csr) return false;
    uint32_t old = rd(d, ETHQ_REG_RX_PRODUCER);
    uint32_t consumer = rd(d, ETHQ_REG_RX_CONSUMER);
    uint32_t depth = 1u << d->ring_log2;
    if (producer - old > depth || producer - consumer > depth) return false;
    publish();
    wr(d, ETHQ_REG_RX_PRODUCER, producer);
    return true;
}
bool ethq_post_tx(ethq_device_t *d, uint32_t producer) {
    if (!d || !d->csr) return false;
    uint32_t old = rd(d, ETHQ_REG_TX_PRODUCER);
    uint32_t consumer = rd(d, ETHQ_REG_TX_CONSUMER);
    uint32_t depth = 1u << d->ring_log2;
    if (producer - old > depth || producer - consumer > depth) return false;
    publish();
    wr(d, ETHQ_REG_TX_PRODUCER, producer);
    return true;
}
uint32_t ethq_rx_available(const ethq_device_t *d) {
    return d ? rd(d, ETHQ_REG_RX_CQ_PRODUCER) -
               rd(d, ETHQ_REG_RX_CQ_CONSUMER) : 0;
}
uint32_t ethq_tx_available(const ethq_device_t *d) {
    return d ? rd(d, ETHQ_REG_TX_CQ_PRODUCER) -
               rd(d, ETHQ_REG_TX_CQ_CONSUMER) : 0;
}
void ethq_ack_irq(ethq_device_t *d, uint32_t flags) {
    if (d && d->csr) wr(d, ETHQ_REG_IRQ_STATUS, flags);
}
