export function systemOverviewFixture() {
  return {
    generated_at: '2026-09-16T15:00:00Z', status: 'OK',
    pipeline: {pipeline_version: 'core_v1', rules_config_version: 'research_v1', status: 'AVAILABLE'},
    components: [
      {name: 'bar_cache', status: 'OK', detail: 'Cache inventory measured from local files.'},
      {name: 'process_memory', status: 'OK', detail: 'Process memory measured locally.'},
    ],
    cache: {status: 'AVAILABLE', freshness_status: 'UNVERIFIED', total_files: 48, total_symbols: 24,
      total_size_mb: 18.4, periods: {'1y': 24, '2y': 24}, latest_modified_at: '2026-09-16T14:55:00Z'},
    run_history: {status: 'AVAILABLE', records: [
      {run_type: 'PIPELINE', run_id: 18, created_at: '2026-09-16T13:00:00Z', status: 'COMPLETED', summary: 'S&P 500 · 3 candidates · 0 data issues'},
      {run_type: 'WORKFLOW', run_id: 17, created_at: '2026-09-16T12:55:00Z', status: 'RECORDED', summary: 'Regime RANGE · risk NORMAL'},
    ]},
  };
}

export function systemJobFixture() {
  return {status: 'AVAILABLE', configured: true, task_name: 'SCANNER Overnight Workflow', scheduler_state: 'Ready',
    last_run_at: '2026-09-16T08:30:00Z', next_run_at: '2026-09-17T08:30:00Z', last_result: '0', last_result_label: 'Success'};
}

export function systemSchwabFixture() {
  return {configured: true, client_id_last4: '1234', redirect_uri: 'https://127.0.0.1', oauth_status: 'AUTHENTICATED',
    refresh_token_status: 'VALID', provider_health: 'HEALTHY', last_verified_at: '2026-09-16T14:59:00Z'};
}

