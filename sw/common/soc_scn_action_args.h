/* Typed, fail-closed access to the ONE generated source-selected C action table.
 * No runtime JSON parser, second allocator, bus driver or completion claim.
 * Shared by real RV32I action implementations and host-side C ABI tests.
 */
#ifndef SOC_SCN_ACTION_ARGS_H
#define SOC_SCN_ACTION_ARGS_H
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include "soc_scn_action_adapter.h"

/* A compact source-generated hash is only a negative filter. A collision
 * can never select another argument: matching keys still compare byte exact.
 * This is intentionally freestanding RV32I shift/add/xor, without libc.
 */
static inline uint32_t soc_scn_arg_key_hash(const char *key) {
  uint32_t hash = UINT32_C(5381);
  if (key == NULL) return 0;
  while (*key != 0) {
    hash = ((hash << 5) + hash) ^ (uint8_t)*key++;
  }
  return hash;
}

static inline const soc_scn_argument_t *
soc_scn_arg_find(const soc_scn_action_t *action, const char *key) {
  const soc_scn_argument_t *found = NULL;
  uint32_t i;
  if (action == NULL || key == NULL || key[0] == 0 ||
      action->first_argument > SOC_SCN_ARGUMENT_COUNT ||
      action->argument_count > SOC_SCN_ARGUMENT_COUNT - action->first_argument)
    return NULL;
  const uint32_t wanted = soc_scn_arg_key_hash(key);
  for (i = 0; i < action->argument_count; ++i) {
    const soc_scn_argument_t *item =
        soc_scn_argument_at(action->first_argument + i);
    if (item == NULL || item->key == NULL) return NULL;
    if (item->key_hash == wanted && soc_scn_text_equal(item->key, key)) {
      if (found != NULL) return NULL; /* ambiguous duplicate key */
      found = item;
    }
  }
  return found;
}

static inline bool soc_scn_arg_uint(const soc_scn_action_t *action,
                                   const char *key, uint64_t *out) {
  const soc_scn_argument_t *arg = soc_scn_arg_find(action, key);
  if (out == NULL || arg == NULL || arg->is_text != 0 ||
      arg->text_value != NULL) return false;
  *out = arg->uint_value;
  return true;
}

static inline bool soc_scn_arg_text(const soc_scn_action_t *action,
                                   const char *key, const char **out) {
  const soc_scn_argument_t *arg = soc_scn_arg_find(action, key);
  if (out == NULL || arg == NULL || arg->is_text != 1 ||
      arg->text_value == NULL || arg->text_value[0] == 0) return false;
  *out = arg->text_value;
  return true;
}
#endif /* SOC_SCN_ACTION_ARGS_H */
