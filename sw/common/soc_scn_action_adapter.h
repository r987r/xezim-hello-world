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
#include <string.h>
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

static inline const soc_scn_driver_registration_t *
soc_scn_driver_for(const soc_scn_driver_registration_t *registry,
                   size_t count, const char *kind) {
  size_t n;
  for (n = 0; n < count; ++n) {
    if (strcmp(kind, registry[n].kind) == 0) return &registry[n];
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
      if (strcmp(registry[i].kind, registry[j].kind) == 0)
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
      const char *dep = soc_scn_dependency_at(a->first_dependency + (uint32_t)j);
      size_t k;
      int earlier = 0;
      if (dep == NULL) return SOC_SCN_ADAPTER_CONTRACT_ERROR;
      for (k = 0; k < i; ++k)
        if (strcmp(soc_scn_actions[k].action_instance_id, dep) == 0) {
          earlier = 1;
          break;
        }
      if (!earlier) return SOC_SCN_ADAPTER_CONTRACT_ERROR;
    }
  }
  return SOC_SCN_ADAPTER_OK;
}

/* Serial adapter for CPU firmware's existing action order. Host callbacks
 * perform ALL physical driving and explicit acknowledgement/timeout policy.
 * No event stage named "hardware_pass", "checked", or "protocol_accepted".
 */
static inline soc_scn_driver_result_t soc_scn_driver_run(
    const soc_scn_driver_registration_t *registry, size_t count,
    soc_scn_driver_event_fn record_event, void *user) {
  soc_scn_driver_result_t result = {
      SOC_SCN_ADAPTER_OK, 0u, 0u, UINT32_MAX, SOC_SCN_PLAN_SHA256
  };
  size_t i;
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
