#include "idma_irq_state.h"

void soc_idma_irq_init(soc_idma_irq_state_t *state, uint32_t expected_mask) {
    if (!state) return;
    state->expected_mask = expected_mask;
    state->observed_mask = 0;
    state->acknowledged_mask = 0;
    state->invalid_ack_mask = 0;
}
void soc_idma_irq_sample(soc_idma_irq_state_t *state, uint32_t pending_mask) {
    if (!state) return;
    state->observed_mask |= pending_mask & state->expected_mask;
}
void soc_idma_irq_ack(soc_idma_irq_state_t *state, uint32_t ack_mask) {
    if (!state) return;
    state->invalid_ack_mask |= ack_mask & ~state->observed_mask;
    state->acknowledged_mask |= ack_mask & state->observed_mask;
}
int soc_idma_irq_complete(const soc_idma_irq_state_t *state) {
    return state && state->expected_mask != 0u &&
           state->invalid_ack_mask == 0u &&
           state->observed_mask == state->expected_mask &&
           state->acknowledged_mask == state->expected_mask;
}
