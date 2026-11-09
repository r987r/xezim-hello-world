/* C11 smoke tests exercise DRIVER ABIs only; never hardware completion. */
#include <stdio.h>
#include <string.h>
#include "soc_scn_action_adapter.h"

static uint32_t callbacks, events_issued, events_done;
static uint32_t fail_at = UINT32_MAX;

static int mock_driver(const soc_scn_action_t *a, void *unused) {
  (void)unused;
  if (!a || !a->action_instance_id || !a->expected_result_id) return -1;
  if (callbacks++ == fail_at) return -1;
  return 0; /* ONLY a driver stand-in; no physical acceptance. */
}
static int capture(const soc_scn_action_t *a, const char *stage, void *unused) {
  (void)unused;
  if (a == NULL) return -1;
  if (strcmp(stage, "issued") == 0) events_issued++;
  else if (strcmp(stage, "driver_done") == 0) events_done++;
  else return -1; /* Cannot fabricate passive check events. */
  return 0;
}

int main(void) {
  size_t i, n=0;
  soc_scn_driver_registration_t registrations[SOC_SCN_ACTION_COUNT];
  soc_scn_driver_result_t r;
  if (strlen(SOC_SCN_PLAN_SHA256) != 64) return 1;
  for (i=0; i<SOC_SCN_ACTION_COUNT; ++i) {
    const char *kind = soc_scn_actions[i].kind;
    size_t j;
    int seen=0;
    for (j=0; j<n; ++j)
      if (strcmp(registrations[j].kind, kind)==0) seen=1;
    if (!seen) {
      registrations[n].kind=kind;
      registrations[n++].execute=mock_driver;
    }
  }
  r=soc_scn_driver_run(registrations, n-1, capture, NULL);
  if (r.status != SOC_SCN_ADAPTER_UNSUPPORTED || r.issued != 0) return 2;
  r=soc_scn_driver_run(registrations, n, capture, NULL);
  if (r.status != SOC_SCN_ADAPTER_OK || r.driver_done != SOC_SCN_ACTION_COUNT ||
      events_done != SOC_SCN_ACTION_COUNT || events_issued != SOC_SCN_ACTION_COUNT ||
      callbacks != SOC_SCN_ACTION_COUNT || r.failure_index != UINT32_MAX) return 3;
  registrations[0].execute=mock_driver;
  r=soc_scn_driver_run(registrations, n, NULL, NULL);
  if (r.status != SOC_SCN_ADAPTER_OK) return 4;
  /* Assert no missing/duplicated callbacks are accepted, then fail a
   * selected action without ever reporting driver_done for that action. */
  registrations[n-1].execute=NULL;
  r=soc_scn_driver_run(registrations, n, capture, NULL);
  if (r.status != SOC_SCN_ADAPTER_CONTRACT_ERROR || r.issued != 0) return 5;
  registrations[n-1].execute=mock_driver;
  callbacks=0; events_done=0; events_issued=0; fail_at=1;
  r=soc_scn_driver_run(registrations, n, capture, NULL);
  if (r.status != SOC_SCN_ADAPTER_DRIVER_FAILED || r.failure_index != 1 ||
      r.issued != 2 || r.driver_done != 1 || events_done != 1) return 6;
  puts("PASS SCN-C selected action driver adapter (driver-only, no RTL proof)");
  return 0;
}
