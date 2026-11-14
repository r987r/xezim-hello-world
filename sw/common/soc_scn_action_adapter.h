/*
 * SCN-C v1 C11 adapter to the ONE generated canonical scenario action table.
 * Deliberately not a second planner, scheduler, memory model or AXI BFM.
 *
 * The caller registers real hardware-specific implementations per action kind.
 * This module only enforces selected ID/dependency/handler ordering, then
 * emits DRIVER events. Never interpret driver_done as protocol accepted or
 * independently checked; passive AXI/TLP/GMII/DFI monitors are mandatory.
 */
#ifndef SOC_SCN_ACTION_ADAPTER_H
#define SOC_SCN_ACTION_ADAPTER_H
#include <stdint.h>
#include <stddef.h>
#include "soc_scenario_contract.h"

enum {
  SOC_SCN_ADAPTER_OK = 0,
  SOC_SCN_ADAPTER_CONTRACT_ERROR = -1,
  SOC_SCN_ADAPTER_UNSUPPORTED = -2,
  SOC_SCN_ADAPTER_DRIVER_FAILED = -3
};

typedef int (*soc_scn_driver_fn)(const soc_scn_action_t *action, void *user);
typedef int (*soc_scn_driver_event_fn)(
    const soc_scn_action_t *action, const char *stage, void *user);

typedef struct {
  const char *kind;
  soc_scn_driver_fn execute;
} soc_scn_driver_registration_t;

typedef struct {
  int status;
  uint32_t issued;
  uint32_t driver_done;
  uint32_t failure_index;
  const char *plan_sha256;
} soc_scn_driver_result_t;

/* Freestanding RV32I images link no libc. Use the same exact string
 * equality as the C11 host adapter, without an external strcmp symbol.
 */
static inline int soc_scn_text_equal(const char *lhs, const char *rhs) {
  if (lhs == NULL || rhs == NULL) return 0;
  while (*lhs && *rhs && *lhs == *rhs) { ++lhs; ++rhs; }
  return *lhs == *rhs;
}

/* Source-selected plan SHA is 64 lowercase hexadecimal bytes. A real
 * passive AXI monitor must STILL verify the CPU's full 256-bit witness.
 */
static inline int soc_scn_sha_equal(const char *selected) {
  size_t i;
  if (selected == NULL) return 0;
  for (i = 0; i < 64; ++i) {
    char c = selected[i];
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')) ||
        c != SOC_SCN_PLAN_SHA256[i]) return 0;
  }
  return selected[64] == 0 && SOC_SCN_PLAN_SHA256[64] == 0;
}

static inline const soc_scn_driver_registration_t *
soc_scn_driver_for(const soc_scn_driver_registration_t *registry,
                   size_t count, const char *kind) {
  size_t n;
  for (n = 0; n < count; ++n) {
    if (soc_scn_text_equal(kind, registry[n].kind)) return &registry[n];
  }
  return NULL;
}

static inline int soc_scn_driver_preflight(
    const soc_scn_driver_registration_t *registry, size_t count) {
  size_t i, j;
  if (registry == NULL || count == 0 || SOC_SCN_ACTION_COUNT == 0 ||
      SOC_SCN_ACTION_COUNT > 4096) return SOC_SCN_ADAPTER_CONTRACT_ERROR;
  for (i = 0; i < count; ++i) {
    if (registry[i].kind == NULL || registry[i].kind[0] == '\0' ||
        registry[i].execute == NULL) return SOC_SCN_ADAPTER_CONTRACT_ERROR;
    for (j = 0; j < i; ++j)
      if (soc_scn_text_equal(registry[i].kind, registry[j].kind))
        return SOC_SCN_ADAPTER_CONTRACT_ERROR;
  }
  for (i = 0; i < SOC_SCN_ACTION_COUNT; ++i) {
    const soc_scn_action_t *a = soc_scn_action_at((uint32_t)i);
    if (a == NULL || a->kind == NULL || a->actor == NULL ||
        a->action_instance_id == NULL || a->expected_result_id == NULL ||
        a->phase == NULL || a->first_dependency > SOC_SCN_DEPENDENCY_COUNT ||
        a->dependency_count > SOC_SCN_DEPENDENCY_COUNT - a->first_dependency ||
        a->first_argument > SOC_SCN_ARGUMENT_COUNT ||
        a->argument_count > SOC_SCN_ARGUMENT_COUNT - a->first_argument)
      return SOC_SCN_ADAPTER_CONTRACT_ERROR;
    if (!soc_scn_driver_for(registry, count, a->kind))
      return SOC_SCN_ADAPTER_UNSUPPORTED;
    for (j = 0; j < a->dependency_count; ++j) {
      const uint32_t slot = a->first_dependency + (uint32_t)j;
      const uint32_t prior = soc_scn_dependency_index_at(slot);
      const char *dep = soc_scn_dependency_at(slot);
      /* The exact source-plan resolver already establishes the dependency
       * order. Still verify the original dependency name and bounds at
       * runtime: the integer index is only a fast lookup, not authorization.
       * This avoids O(actions^2) string scans over AXI-backed flash.
       */
      if (dep == NULL || prior >= i ||
          !soc_scn_text_equal(soc_scn_actions[prior].action_instance_id, dep))
        return SOC_SCN_ADAPTER_CONTRACT_ERROR;
    }
  }
  return SOC_SCN_ADAPTER_OK;
}

/* The caller MUST supply the selected 64-hex SHA independently of this
 * generated header (e.g., via a CPU boot mailbox/config handshake). Merely
 * reading SOC_SCN_PLAN_SHA256 from the same header is not an independent
 * hardware selection proof, although it is sufficient for the C11 ABI smoke.
 * Mismatches fail before any callbacks, firmware events or device writes.
 * Host callbacks perform ALL physical driving and retirement policy.
 * No event stage named "hardware_pass", "checked" or "protocol_accepted".
 */
static inline soc_scn_driver_result_t soc_scn_driver_run(
    const char *selected_plan_sha,
    const soc_scn_driver_registration_t *registry, size_t count,
    soc_scn_driver_event_fn record_event, void *user) {
  soc_scn_driver_result_t result = {
      SOC_SCN_ADAPTER_OK, 0u, 0u, UINT32_MAX, SOC_SCN_PLAN_SHA256
  };
  size_t i;
  if (!soc_scn_sha_equal(selected_plan_sha)) {
    result.status = SOC_SCN_ADAPTER_CONTRACT_ERROR;
    return result;
  }
  result.status = soc_scn_driver_preflight(registry, count);
  if (result.status != SOC_SCN_ADAPTER_OK) return result;
  for (i = 0; i < SOC_SCN_ACTION_COUNT; ++i) {
    const soc_scn_action_t *a = soc_scn_action_at((uint32_t)i);
    const soc_scn_driver_registration_t *handler =
        soc_scn_driver_for(registry, count, a->kind);
    if (record_event && record_event(a, "issued", user) != 0) {
      result.status = SOC_SCN_ADAPTER_DRIVER_FAILED;
      result.failure_index = (uint32_t)i;
      return result;
    }
    result.issued++;
    if (handler->execute(a, user) != 0) {
      result.status = SOC_SCN_ADAPTER_DRIVER_FAILED;
      result.failure_index = (uint32_t)i;
      return result;
    }
    if (record_event && record_event(a, "driver_done", user) != 0) {
      result.status = SOC_SCN_ADAPTER_DRIVER_FAILED;
      result.failure_index = (uint32_t)i;
      return result;
    }
    result.driver_done++;
  }
  return result;
}
#endif /* SOC_SCN_ACTION_ADAPTER_H */
