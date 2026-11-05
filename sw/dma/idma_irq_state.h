#ifndef SOC_DV_IDMA_IRQ_STATE_H
#define SOC_DV_IDMA_IRQ_STATE_H
#include <stdint.h>

/* Portable IRQ bookkeeping for upcoming PicoRV32 RV32I ISR integration.
 * This does NOT install an ISR, define CSR addresses or assert hardware IRQ.
 * Integrator must prove real CPU entry/exit and sticky-IRQ acknowledge.
 */
typedef struct {
    uint32_t expected_mask;
    uint32_t observed_mask;
    uint32_t acknowledged_mask;
    uint32_t invalid_ack_mask;
} soc_idma_irq_state_t;

void soc_idma_irq_init(soc_idma_irq_state_t *state, uint32_t expected_mask);
void soc_idma_irq_sample(soc_idma_irq_state_t *state, uint32_t pending_mask);
void soc_idma_irq_ack(soc_idma_irq_state_t *state, uint32_t ack_mask);
int soc_idma_irq_complete(const soc_idma_irq_state_t *state);
#endif
