/* Source-COMPILED SCN-C dispatcher for freestanding RV32I.

   The original soc_scn_driver_run() remains the full dynamic C11 adapter.
   This smaller executor is exclusively for a header emitted by the
   canonical scenario parser, after generator-side dependency/name/type
   validation, exact-plan-SHA validation and required host C11 test gates.

   An on-chip C11 interpreter need not re-scan the same generated dependency
   strings over a slow, AXI-backed instruction flash on every run. Numeric
   dependency ordering/bounds, registration uniqueness, exact supported
   kind names, selected SHA, event ordering and every callback failure are
   STILL checked at runtime. An ID, callback or driver_done is not a real
   bus completion: passive AXI/bytes/TLP/GMII scoreboards remain mandatory.

   No new bus model, fake response, bypassed CPU instruction, RTL change or
   test timeout increase. This path is opt-in for source-compiled firmware.
*/
#ifndef SOC_SCN_COMPILED_RUNTIME_H
#define SOC_SCN_COMPILED_RUNTIME_H
#include "soc_scn_action_adapter.h"

#define SOC_SCN_COMPILED_MAX_ACTIONS 64u
#define SOC_SCN_COMPILED_MAX_DRIVERS 32u

static inline uint32_t soc_scn_compiled_kind_hash(const char *s) {
  uint32_t h = UINT32_C(5381);
  if (s == NULL) return 0u;
  while (*s) h = ((h << 5) + h) ^ (uint8_t)*s++;
  return h;
}

static inline soc_scn_driver_result_t soc_scn_driver_run_compiled(
    const char *selected_plan_sha,
    const soc_scn_driver_registration_t *registry, size_t count,
    soc_scn_driver_event_fn record_event, void *user) {
  soc_scn_driver_result_t result = {
      SOC_SCN_ADAPTER_OK, 0u, 0u, UINT32_MAX, SOC_SCN_PLAN_SHA256};
  size_t i, j;

  if (!soc_scn_sha_equal(selected_plan_sha) || registry == NULL ||
      count == 0u || count > SOC_SCN_COMPILED_MAX_DRIVERS ||
      SOC_SCN_ACTION_COUNT == 0u ||
      SOC_SCN_ACTION_COUNT > SOC_SCN_COMPILED_MAX_ACTIONS) {
    result.status = SOC_SCN_ADAPTER_CONTRACT_ERROR;
    return result;
  }

  /* Reject missing or ambiguous implementations before driving any action.
   * Hashes only filter candidates; full text always resolves collisions.
   */
  uint32_t hashes[SOC_SCN_COMPILED_MAX_DRIVERS];
  for (i = 0; i < count; ++i) {
    if (registry[i].kind == NULL || !registry[i].kind[0] ||
        registry[i].execute == NULL) {
      result.status = SOC_SCN_ADAPTER_CONTRACT_ERROR;
      return result;
    }
    hashes[i] = soc_scn_compiled_kind_hash(registry[i].kind);
    for (j = 0; j < i; ++j) {
      if (hashes[i] == hashes[j] &&
          soc_scn_text_equal(registry[i].kind, registry[j].kind)) {
        result.status = SOC_SCN_ADAPTER_CONTRACT_ERROR;
        return result;
      }
    }
  }

  /* The canonical Python generator has already verified exact dependency
   * names/positions and C argument types. Retain runtime numeric bounds and
   * order checks plus exact kind-to-driver matching. Resolve handlers once:
   * avoid repeated Flash/NoC string scans in the inner run loop.
   */
  soc_scn_driver_fn selected[SOC_SCN_ACTION_COUNT];
  for (i = 0; i < SOC_SCN_ACTION_COUNT; ++i) {
    const soc_scn_action_t *a = soc_scn_action_at((uint32_t)i);
    if (a == NULL || a->kind == NULL || a->action_instance_id == NULL ||
        a->actor == NULL || a->phase == NULL ||
        a->expected_result_id == NULL ||
        a->first_dependency > SOC_SCN_DEPENDENCY_COUNT ||
        a->dependency_count > SOC_SCN_DEPENDENCY_COUNT - a->first_dependency ||
        a->first_argument > SOC_SCN_ARGUMENT_COUNT ||
        a->argument_count > SOC_SCN_ARGUMENT_COUNT - a->first_argument) {
      result.status = SOC_SCN_ADAPTER_CONTRACT_ERROR;
      return result;
    }
    for (j = 0; j < a->dependency_count; ++j) {
      const uint32_t slot = a->first_dependency + (uint32_t)j;
      if (soc_scn_dependency_index_at(slot) >= i ||
          soc_scn_dependency_at(slot) == NULL) {
        result.status = SOC_SCN_ADAPTER_CONTRACT_ERROR;
        return result;
      }
    }
    const uint32_t hash = soc_scn_compiled_kind_hash(a->kind);
    selected[i] = NULL;
    for (j = 0; j < count; ++j) {
      if (hash == hashes[j] &&
          soc_scn_text_equal(a->kind, registry[j].kind)) {
        selected[i] = registry[j].execute;
        break;
      }
    }
    if (!selected[i]) {
      result.status = SOC_SCN_ADAPTER_UNSUPPORTED;
      return result;
    }
  }

  for (i = 0; i < SOC_SCN_ACTION_COUNT; ++i) {
    const soc_scn_action_t *a = soc_scn_action_at((uint32_t)i);
    if (record_event && record_event(a, "issued", user) != 0) {
      result.status = SOC_SCN_ADAPTER_DRIVER_FAILED;
      result.failure_index = (uint32_t)i;
      return result;
    }
    ++result.issued;
    if (selected[i](a, user) != 0) {
      result.status = SOC_SCN_ADAPTER_DRIVER_FAILED;
      result.failure_index = (uint32_t)i;
      return result;
    }
    if (record_event && record_event(a, "driver_done", user) != 0) {
      result.status = SOC_SCN_ADAPTER_DRIVER_FAILED;
      result.failure_index = (uint32_t)i;
      return result;
    }
    ++result.driver_done;
  }
  return result;
}
#endif /* SOC_SCN_COMPILED_RUNTIME_H */
