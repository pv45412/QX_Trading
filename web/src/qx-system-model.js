const tabs = new Map([
  ['system_overview', 'overview'],
  ['system', 'overview'],
  ['schwab', 'providers'],
  ['data_cache', 'data'],
  ['jobs', 'jobs'],
  ['run_history', 'runs'],
  ['strategy_rules', 'rules'],
]);

export function systemTabForRoute(route) {
  return tabs.get(route) || 'overview';
}

export function buildSystemOverview(payload) {
  if (!payload || typeof payload !== 'object') return unavailableOverview();
  return {
    generatedAt: payload.generated_at ?? null,
    status: text(payload.status) || 'UNAVAILABLE',
    pipelineVersion: text(payload.pipeline?.pipeline_version),
    rulesConfigVersion: text(payload.pipeline?.rules_config_version),
    rulesStatus: text(payload.pipeline?.status) || 'UNAVAILABLE',
    components: Array.isArray(payload.components) ? payload.components.map(component => ({
      name: text(component?.name),
      status: text(component?.status) || 'UNAVAILABLE',
      detail: text(component?.detail),
    })).filter(component => component.name) : [],
    cache: {
      status: text(payload.cache?.status) || 'UNAVAILABLE',
      freshnessStatus: text(payload.cache?.freshness_status) || 'UNAVAILABLE',
      totalFiles: integerOrNull(payload.cache?.total_files),
      totalSymbols: integerOrNull(payload.cache?.total_symbols),
      totalSizeMb: finiteOrNull(payload.cache?.total_size_mb),
      periods: objectOrEmpty(payload.cache?.periods),
      latestModifiedAt: text(payload.cache?.latest_modified_at),
    },
    runHistoryStatus: text(payload.run_history?.status) || 'UNAVAILABLE',
    runs: Array.isArray(payload.run_history?.records) ? payload.run_history.records.map(run => ({
      runType: text(run?.run_type),
      runId: integerOrNull(run?.run_id),
      createdAt: text(run?.created_at),
      status: text(run?.status) || 'UNAVAILABLE',
      summary: text(run?.summary),
    })).filter(run => run.runType && run.runId != null) : [],
  };
}

export function buildSystemJobStatus(payload) {
  if (!payload || typeof payload !== 'object') return unavailableJob();
  return {
    status: text(payload.status) || 'UNAVAILABLE',
    configured: payload.configured === true,
    taskName: text(payload.task_name),
    schedulerState: text(payload.scheduler_state) || 'UNAVAILABLE',
    lastRunAt: text(payload.last_run_at),
    nextRunAt: text(payload.next_run_at),
    lastResult: text(payload.last_result),
    lastResultLabel: text(payload.last_result_label),
  };
}

function unavailableOverview() {
  return {generatedAt: null, status: 'UNAVAILABLE', pipelineVersion: null, rulesConfigVersion: null,
    rulesStatus: 'UNAVAILABLE', components: [], cache: {status: 'UNAVAILABLE', freshnessStatus: 'UNAVAILABLE',
      totalFiles: null, totalSymbols: null, totalSizeMb: null, periods: {}, latestModifiedAt: null},
    runHistoryStatus: 'UNAVAILABLE', runs: []};
}

function unavailableJob() {
  return {status: 'UNAVAILABLE', configured: false, taskName: null, schedulerState: 'UNAVAILABLE',
    lastRunAt: null, nextRunAt: null, lastResult: null, lastResultLabel: null};
}

function text(value) { return typeof value === 'string' && value.trim() ? value : null; }
function finiteOrNull(value) { return typeof value === 'number' && Number.isFinite(value) ? value : null; }
function integerOrNull(value) { return Number.isInteger(value) ? value : null; }
function objectOrEmpty(value) { return value && typeof value === 'object' && !Array.isArray(value) ? {...value} : {}; }

