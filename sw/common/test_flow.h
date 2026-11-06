#ifndef SOC_TEST_FLOW_H_
#define SOC_TEST_FLOW_H_
#include <stdint.h>

/* Shared cross-language phase/step event ABI, NOT a new test runner.
 * The caller owns a verified memory-mapped trace sink. Writes must be
 * observed as accepted AXI transactions by the existing run monitor
 * before being reported as RTL evidence. A C 'PASS' marker alone never
 * satisfies the independent hardware/data scoreboard.
 *
 * 32-bit encoded word: [31:24]=0xf1, [23:22]=phase, [21:20]=status,
 * [19:12]=actor codebook ID, [11:0]=step codebook ID.
 * Names are resolved from the test's YAML/manifest codebook, not encoded
 * as arbitrary dynamic strings in firmware.
 */
enum soc_flow_phase {
    SOC_FLOW_INIT = 0,
    SOC_FLOW_RUN = 1,
    SOC_FLOW_CHECK = 2
};
enum soc_flow_status {
    SOC_FLOW_START = 0,
    SOC_FLOW_PASS = 1,
    SOC_FLOW_FAIL = 2
};
static inline uint32_t soc_flow_marker(unsigned phase, unsigned status,
                                       unsigned actor_id, unsigned step_id) {
    if (phase > SOC_FLOW_CHECK || status > SOC_FLOW_FAIL ||
        actor_id > 255u || step_id > 4095u) {
        return 0u; /* invalid marker: checker must reject, never pass */
    }
    return (0xf1u << 24) | (phase << 22) | (status << 20)
         | (actor_id << 12) | step_id;
}
static inline void soc_flow_emit(volatile uint32_t *sink, unsigned phase,
                                 unsigned status, unsigned actor_id,
                                 unsigned step_id) {
    uint32_t marker = soc_flow_marker(phase,status,actor_id,step_id);
    if (sink && marker) {
        *sink = marker;
    }
}
#endif
