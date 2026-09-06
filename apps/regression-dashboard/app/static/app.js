'use strict';

const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const esc = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const activeStatuses = new Set(['queued', 'running']);
const terminalStatuses = new Set(['draft', 'completed', 'failed', 'cancelled']);
const lifecycleLabels = {draft:'Черновик',queued:'В очереди',running:'Выполняется',cancelling:'Останавливается',cancelled:'Остановлен',completed:'Завершён',failed:'Прерван / ошибка'};
const state = {runs:[], run:null, selected:null, config:null, cases:null, view:'dashboard',
  poll:null, runRequest:0, listRequest:0, historyRequest:0, compareRequest:0,
  controller:null, history:[], historyOffset:0, historyMore:false, busy:null, detail:null};
const token = () => sessionStorage.getItem('adminToken') || '';
const pct = value => value == null ? 'Нет данных' : Number(value).toLocaleString('ru-RU') + '%';
const ms = value => value == null ? 'Нет данных' : value >= 1000 ? (value / 1000).toFixed(2) + ' с' : Math.round(value) + ' мс';
const date = value => value ? new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : value + 'Z').toLocaleString('ru-RU') : '—';
const technical = row => row.state === 'error' || Boolean(row.technical_error) || row.auto_evaluation?.technical_error === true;
const technicalKind = row => ({agent:'Agent', judge:'LLM judge', integration:'Integration', model:'Judge model'})[
  row.technical_error_kind || row.auto_evaluation?.technical_error_kind
] || 'Integration';
const llm = row => technical(row) ? null : row.auto_evaluation?.status || (!row.auto_evaluation?.algorithmic ? row.auto_status : null);
const algo = row => row.auto_evaluation?.algorithmic?.status;
const effective = row => row.effective_status || 'UNREVIEWED';
const reviewFlag = row => Boolean(row.auto_evaluation?.requires_manual_review || row.auto_evaluation?.algorithmic?.requires_manual_review);
const pendingReview = row => reviewFlag(row) && !row.manual_status;
const disagreement = row => Boolean(llm(row) && algo(row) && llm(row) !== algo(row));
const displayStatus = row => technical(row) ? 'TECHNICAL_ERROR' : effective(row);
const live = run => activeStatuses.has(run.status) && run.cancel_requested ? 'cancelling' : run.status;
const canStop = run => run.can_stop ?? (activeStatuses.has(run.status) && !run.cancel_requested);
const canDelete = run => run.can_delete ?? terminalStatuses.has(run.status);
const badge = (value, label) => '<span class="status status-' + esc(value || 'UNREVIEWED') + '">' + esc(label || ({UNREVIEWED:'Без оценки',TECHNICAL_ERROR:'Тех. ошибка'}[value]) || value || 'Нет оценки') + '</span>';
const runOption = run => '<option value="' + run.id + '">#' + run.id + ' · «' + esc(run.name) + '»</option>';
const promptLabel = run => !run.prompt_version || run.provenance?.prompt_source === 'unknown' ? 'Версия неизвестна' : run.prompt_version + ' (метка пользователя)';
const attemptLabel = row => esc(row.case_id) + (row.attempt > 1 ? ' · повтор ' + row.attempt : '');
const textBlock = text => '<div class="text-block">' + esc(text || 'Нет данных') + '</div>';

async function api(path, options = {}) {
  const headers = {'Content-Type':'application/json', ...options.headers};
  if (options.admin) headers['X-Admin-Token'] = token();
  const response = await fetch(path, {...options, headers});
  if (!response.ok) {
    let message = 'HTTP ' + response.status;
    try { const body = await response.json(); message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail); } catch {}
    const error = new Error(message); error.status = response.status; throw error;
  }
  return response.json();
}
let toastTimer;
function toast(message) {
  $('#toast').textContent = message; $('#toast').classList.remove('hidden');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').classList.add('hidden'), 6000);
}
function showError(error) {
  if (error.name === 'AbortError') return;
  $('#loading').classList.add('hidden');
  $('#loadErrorText').textContent = error.message;
  $('#loadError').classList.remove('hidden');
}
function handled(fn) { return (...args) => Promise.resolve().then(() => fn(...args)).catch(showError); }
function hideError() { $('#loadError').classList.add('hidden'); }
function showDialog(id) {
  const dialog = $('#' + id);
  dialog.returnFocus = document.activeElement;
  if (!dialog.open) dialog.showModal();
}
function closeDialog(id) { $('#' + id).close(); }
function askConfirmation(title, message, action) {
  $('#confirmTitle').textContent = title; $('#confirmText').textContent = message;
  $('#confirmAction').textContent = title;
  $('#confirmAction').onclick = handled(async () => { closeDialog('confirmModal'); await action(); });
  showDialog('confirmModal');
}
function requireToken() {
  if (token()) return true;
  $('#adminToken').value = ''; showDialog('tokenModal'); toast('Сначала сохраните токен управления.');
  return false;
}
function openRunModal() {
  if (!state.config) return;
  $('#runName').value = 'Regression · ' + new Date().toLocaleString('ru-RU', {day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'});
  showDialog('runModal');
}
function switchView(view) {
  state.view = view;
  $$('.view').forEach(element => element.classList.toggle('active', element.id === view + 'View'));
  $$('.nav-item').forEach(button => {
    const selected = button.dataset.view === view;
    button.classList.toggle('active', selected);
    if (selected) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
  });
  $('#pageTitle').textContent = {dashboard:'Обзор',results:'Результаты',history:'История и сравнение',cases:'Набор тестов'}[view];
  if (view === 'results') renderResults();
  if (view === 'history') { renderCompareSelectors(); handled(loadHistory)(); }
  schedulePoll();
}
function mergeRuns(runs) {
  const byId = new Map(state.runs.map(run => [run.id, run]));
  runs.forEach(run => byId.set(run.id, run));
  state.runs = [...byId.values()].sort((a,b) => b.id - a.id);
}
function renderRunPicker() {
  const picker = $('#runPicker');
  picker.disabled = !state.runs.length;
  picker.innerHTML = state.runs.length ? state.runs.map(runOption).join('') : '<option>Прогонов пока нет</option>';
  if (state.selected != null) picker.value = String(state.selected);
}
function stopPoll() { clearTimeout(state.poll); state.poll = null; }
function schedulePoll() {
  stopPoll();
  if (state.busy) return;
  const needsPoll = (state.run && activeStatuses.has(state.run.status)) ||
    (state.view === 'history' && state.history.some(run => activeStatuses.has(run.status)));
  if (needsPoll) state.poll = setTimeout(handled(async () => {
    try {
      if (state.run && activeStatuses.has(state.run.status)) await loadRun(state.run.id, {quiet:true});
      if (state.view === 'history') await loadHistory();
    } finally { schedulePoll(); }
  }), 2000);
}
async function loadRuns(preferred) {
  const request = ++state.listRequest;
  const runs = await api('/api/runs');
  if (request !== state.listRequest) return;
  mergeRuns(runs);
  const requested = preferred ?? state.selected;
  const selected = state.runs.find(run => run.id === Number(requested)) || runs[0];
  if (selected) await loadRun(selected.id);
  else clearCurrent();
  renderCompareSelectors();
}
function clearCurrent() {
  stopPoll(); state.controller?.abort(); ++state.runRequest;
  $('#loading').classList.add('hidden');
  state.run = null; state.selected = null; state.detail = null;
  if ($('#detailDrawer').open) closeDialog('detailDrawer');
  renderRunPicker(); renderCurrent();
}
function removeRun(id) {
  state.runs = state.runs.filter(run => run.id !== id);
  state.history = state.history.filter(run => run.id !== id);
  ++state.compareRequest;
  $('#comparisonContent').innerHTML = '<p class="muted">Список изменился. Выберите два доступных прогона.</p>';
  if (state.selected === id) clearCurrent();
  renderRunPicker(); renderCompareSelectors(); renderHistory();
}
async function loadRun(id, {quiet = false} = {}) {
  id = Number(id);
  const request = ++state.runRequest;
  state.controller?.abort(); state.controller = new AbortController();
  const switching = state.selected !== id;
  state.selected = id; stopPoll();
  if (switching) {
    state.run = null; state.detail = null;
    if ($('#detailDrawer').open) closeDialog('detailDrawer');
    renderCurrent();
  }
  if (!quiet) $('#loading').classList.remove('hidden');
  try {
    const run = await api('/api/runs/' + id, {signal:state.controller.signal});
    if (request !== state.runRequest || state.selected !== id) return;
    state.run = run; mergeRuns([run]); renderRunPicker(); renderCurrent(); hideError();
  } catch (error) {
    if (request !== state.runRequest || error.name === 'AbortError') return;
    if (error.status === 404) {
      removeRun(id); toast('Прогон #' + id + ' больше недоступен.');
      await loadRuns();
    } else throw error;
  } finally {
    if (request === state.runRequest) { $('#loading').classList.add('hidden'); schedulePoll(); }
  }
}
function renderControls() {
  const run = state.run;
  $('#runMenu').classList.toggle('hidden', !run);
  $('#cancelRunButton').classList.toggle('hidden', !run || !activeStatuses.has(run.status));
  $('#startDraftButton').classList.toggle('hidden', !run || run.status !== 'draft');
  $('#startDraftButton').disabled = Boolean(state.busy);
  $('#cancelRunButton').disabled = Boolean(state.busy || !run || !canStop(run));
  $('#cancelRunButton').textContent = run?.cancel_requested ? 'Останавливается…' : 'Остановить';
  $('#deleteRunButton').disabled = Boolean(state.busy || !run || !canDelete(run));
  $('#deleteRunButton').title = run && !canDelete(run) ? 'Дождитесь завершения worker' : '';
  $('#runActionStatus').textContent = state.busy ? 'Выполняем действие…' : run && live(run) === 'cancelling' ?
    'Остановка запрошена. Текущий запрос может завершиться; удаление будет доступно после остановки worker.' : '';
  if (!run) { $('#runIdentity').textContent = 'Выберите прогон в истории или создайте новый.'; return; }
  $('#runIdentity').innerHTML = badge(live(run), lifecycleLabels[live(run)] || run.status) +
    '<b>Прогон #' + run.id + '</b><p>Судья: ' + esc(run.judge_model) + '</p><p>' +
    esc(promptLabel(run)) + ' · ' + esc(date(run.created_at)) + '</p>';
  $('#exportCsvButton').href = '/api/runs/' + run.id + '/export/csv';
  $('#exportPdfButton').href = '/api/runs/' + run.id + '/export/pdf';
}
function renderCurrent() {
  renderControls(); renderDashboard();
  if (state.view === 'results') renderResults();
}
function metric(label, value, detail, warning = false) {
  return '<article class="metric"><h2>' + esc(label) + '</h2><strong class="' + (warning ? 'danger-text' : '') + '">' +
    esc(value) + '</strong><small>' + esc(detail) + '</small></article>';
}
function renderDashboard() {
  const run = state.run;
  $('#emptyState').classList.toggle('hidden', Boolean(run) || state.selected != null);
  $('#dashboardContent').classList.toggle('hidden', !run);
  if (!run) return;
  const m = run.metrics, x = run.execution;
  const critical = run.results.filter(row => effective(row) === 'CRITICAL').length;
  $('#primaryMetrics').innerHTML = [
    metric('Успешность основных · GTSR', x.evaluated ? pct(m.gtsr.percent) : 'Нет данных', m.gtsr.value + ' / 40 · порог ≥34'),
    metric('Критические нарушения · итог', critical || x.evaluated ? critical : 'Нет данных', 'Из ' + x.total + ' кейсов · допустимо 0', critical > 0),
    metric('Технические ошибки', x.errors, 'Обработано ' + x.processed + ' / ' + x.total, x.errors > 0),
    metric('Требуют ручной проверки', x.review_pending, 'Флаги: ' + x.review_flags + ' · ручных оценок: ' + x.manual_reviews)
  ].join('');
  $('#gateValue').className = 'status status-' + m.release_gate;
  $('#gateValue').textContent = m.release_gate;
  $('#gateSubtitle').textContent = run.gate.preliminary ? 'Результат предварительный. Итоговая оценка недоступна.' :
    m.release_gate === 'PASS' ? 'Все критерии выполнены.' : 'Есть непройденные критерии.';
  $('#progressLabel').textContent = 'Обработано ' + x.processed + ' / ' + x.total + ' · оценено ' + x.evaluated + ' / ' + x.total + ' · без оценки ' + x.unscored;
  $('#runProgress').value = m.progress.percent || 0;
  $('#gateReasons').innerHTML = run.gate.reasons.length ? run.gate.reasons.map(reason => '<li>' + esc(reason) + '</li>').join('') : '<li>Все критерии выполнены.</li>';
  const legacy = run.provenance.metrics_version === 'legacy-v1';
  $('#legacyNotice').classList.toggle('hidden', !legacy);
  $('#legacyNotice').textContent = 'Исторический расчёт legacy-v1 сохранён. Технические ошибки с полученным ответом могли входить в метрики качества. Выполнение и ошибки показаны отдельно.';
  const rows = run.results.filter(row => technical(row) || ['CRITICAL','FAIL','PARTIAL'].includes(effective(row)) || pendingReview(row));
  const rank = row => technical(row) ? 0 : effective(row) === 'CRITICAL' ? 1 : effective(row) === 'FAIL' ? 2 : pendingReview(row) ? 3 : 4;
  rows.sort((a,b) => rank(a) - rank(b));
  $('#problemList').innerHTML = rows.length ? rows.slice(0,8).map(row => '<div class="problem"><button class="link-button" data-detail="' + row.id + '">' +
    esc(row.case_id) + '</button>' + badge(displayStatus(row)) + '<p>' + esc(problemReason(row)) + '</p><button class="link-button" data-detail="' +
    row.id + '" aria-label="Открыть ' + esc(row.case_id) + '">Открыть →</button></div>').join('') +
    (rows.length > 8 ? '<p class="muted">Ещё ' + (rows.length - 8) + ' в результатах.</p>' : '') :
    '<p class="muted">' + (x.evaluated ? 'Среди полученных оценок проблем не найдено.' : 'Оценок ещё нет.') + '</p>';
  const metricRows = [
    ['Фактическая корректность','factual_correctness','≥29 ответов (полный набор: ≥90%)'],
    ['Полнота фактов','completeness','≥90%'],['Покрытие источниками','source_coverage','≥95%'],
    ['Полезность','usefulness','≥26 ответов (полный набор: ≥80%)'],['Ложные отказы','false_refusals','≤3'],
    ['Устойчивость boundary','stable_boundary','≥7/8'],['Маркировка Web Search','web_labeling','100% при использовании']
  ];
  $('#qualityMetrics').innerHTML = '<table><thead><tr><th>Показатель</th><th>Результат</th><th>Порог</th><th>Проверка</th></tr></thead><tbody>' +
    metricRows.map(([label,key,threshold]) => '<tr><td>' + label + '</td><td>' + pct(m[key].percent) + '<small>' +
      m[key].value + ' / ' + m[key].total + '</small></td><td>' + threshold + '</td><td>' +
      (m[key].percent == null ? 'Нет данных' : badge(m[key].pass ? 'PASS' : 'FAIL')) + '</td></tr>').join('') + '</tbody></table>';
  const alg = m.algorithmic;
  $('#algorithmMetrics').innerHTML = '<p>Обязательные факты: <b>' + pct(alg.required_fact_coverage.percent) + '</b> · ' +
    alg.required_fact_coverage.value + ' / ' + alg.required_fact_coverage.total + '. Проверено алгоритмом: ' + alg.evaluated + '.</p>' +
    '<p>Запрещённые утверждения: ' + alg.forbidden_matches.value + '. Алгоритмических CRITICAL: ' + x.algorithmic_critical +
    ' (включая сохранённые при сбое судьи).</p><div class="table-wrap"><table><thead><tr><th>Статус</th><th>LLM + ручная</th><th>Алгоритм</th><th>Combined + ручная</th></tr></thead><tbody>' +
    ['PASS','PARTIAL','FAIL','CRITICAL','UNREVIEWED'].map(status => '<tr><td>' + badge(status) + '</td><td>' + m.statuses[status] +
      '</td><td>' + (alg.statuses[status] ?? '—') + '</td><td>' + m.combined.statuses[status] + '</td></tr>').join('') + '</tbody></table></div>';
  $('#latencyMetrics').innerHTML = Object.entries(m.latency).map(([key,value]) => '<div><small class="muted">' +
    esc(key.replace('_ms','').toUpperCase()) + '</small><strong>' + ms(value) + '</strong></div>').join('');
  $('#versionDetails').innerHTML = [
    ['Метка промпта агента',promptLabel(run)],['Промпт судьи',run.provenance.judge_prompt_version],
    ['Оценщик SHA-256',run.provenance.evaluator_sha256],['Набор SHA-256',run.provenance.suite_sha256],
    ['Метрики',run.provenance.metrics_version],['Версия снимка отчётов',run.provenance.report_data_version]
  ].map(([label,value]) => '<dt>' + label + '</dt><dd>' + esc(value || 'Версия неизвестна') + '</dd>').join('');
}
function problemReason(row) {
  if (technical(row)) return technicalKind(row) + ': ' + (row.technical_error || 'Техническая ошибка выполнения');
  const evaluation = row.auto_evaluation || {};
  if (effective(row) === 'CRITICAL') return evaluation.algorithmic?.status === 'CRITICAL' ? evaluation.algorithmic.reason : evaluation.reason;
  return (pendingReview(row) ? 'Ручная проверка: ' : '') + (evaluation.reason || evaluation.algorithmic?.reason || row.question);
}
function renderResults() {
  const selected = $('#categoryFilter').value;
  const categories = [...new Set((state.run?.results || []).map(row => row.category))].sort();
  $('#categoryFilter').innerHTML = '<option value="">Все категории</option>' + categories.map(category => '<option>' + esc(category) + '</option>').join('');
  if (categories.includes(selected)) $('#categoryFilter').value = selected;
  filterResults();
}
function filterResults() {
  if (!state.run) { $('#resultsTable').innerHTML = '<div class="empty">Нет открытого прогона.</div>'; $('#resultCount').textContent = ''; return; }
  const query = $('#resultSearch').value.toLowerCase(), status = $('#statusFilter').value, category = $('#categoryFilter').value;
  const rows = state.run.results.filter(row =>
    (!query || [row.case_id,row.question,row.answer,row.technical_error].join(' ').toLowerCase().includes(query)) &&
    (!status || (!technical(row) && effective(row) === status)) && (!category || row.category === category) &&
    (!$('#technicalFilter').checked || technical(row)) && (!$('#reviewFilter').checked || pendingReview(row)) &&
    (!$('#disagreementFilter').checked || disagreement(row)));
  $('#resultCount').textContent = rows.length + ' / ' + state.run.results.length + ' результатов';
  $('#resultsTable').innerHTML = rows.length ? '<table class="results-table"><thead><tr><th>Кейс</th><th>Вопрос и ответ</th><th>LLM</th><th>Алгоритм</th><th>Итог</th><th>Проверка</th><th>Время</th></tr></thead><tbody>' +
    rows.map(row => '<tr><td><button class="link-button" data-detail="' + row.id + '">' + attemptLabel(row) +
      '</button><small>' + esc(row.category) + '</small></td><td class="question-cell"><button class="link-button" data-detail="' +
      row.id + '">' + esc(row.question) + '</button><p class="result-preview">' +
      esc(technical(row) ? technicalKind(row) + ': ' + (row.technical_error || 'Техническая ошибка') : row.answer || ({pending:'Ожидает',running:'Выполняется',cancelled:'Остановлен',interrupted:'Прерван'}[row.state] || row.state)) +
      '</p></td><td>' + badge(llm(row)) + '</td><td>' + badge(algo(row)) + '</td><td>' +
      badge(displayStatus(row)) + (row.manual_status ? '<small>Ручная: ' + esc(row.manual_status) + '</small>' : '') +
      '</td><td>' + (pendingReview(row) ? 'Нужна проверка' : row.manual_status ? 'Проверено вручную' : '—') +
      (disagreement(row) ? '<small>LLM ≠ алгоритм</small>' : '') + '</td><td>' + ms(row.latency_ms) + '</td></tr>').join('') +
    '</tbody></table>' : '<div class="empty">По этим фильтрам ничего не найдено.</div>';
}
function listItems(title, items) {
  return items?.length ? '<h4>' + title + '</h4><ul class="evaluation-lists">' + items.map(item => '<li>' + esc(typeof item === 'object' ? JSON.stringify(item) : item) + '</li>').join('') + '</ul>' : '';
}
function evaluationSummary(evaluation) {
  const bool = value => value == null ? 'Нет оценки' : value ? 'Да' : 'Нет';
  return '<div class="compact-grid">' + [
    ['Факты корректны',bool(evaluation.factual_correct)],['Полезный ответ',bool(evaluation.useful)],
    ['Ложный отказ',bool(evaluation.false_refusal)],['Вердикт по сделке',bool(evaluation.verdict_given)],
    ['Web Search',bool(evaluation.web_search_used)],['Маркировка Web',evaluation.web_search_used ? bool(evaluation.web_search_labeled_correctly) : 'Не применимо'],
    ['Обязательные факты',(evaluation.required_facts_matched ?? '—') + ' / ' + (evaluation.required_facts_total ?? '—')],
    ['Тезисы с источником',(evaluation.claims_with_source ?? '—') + ' / ' + (evaluation.claims_total ?? '—')]
  ].map(([label,value]) => '<div><small class="muted">' + label + '</small><strong>' + esc(value) + '</strong></div>').join('') + '</div>';
}
function safeUrl(url) {
  try { const parsed = new URL(url); return ['http:','https:'].includes(parsed.protocol) ? parsed.href : null; } catch { return null; }
}
function openDetail(id) {
  const row = state.run?.results.find(item => item.id === Number(id));
  if (!row) return;
  state.detail = {runId:state.run.id, id:row.id};
  const evaluation = row.auto_evaluation || {}, algorithm = evaluation.algorithmic;
  const checks = (algorithm?.checks || []).filter(check => ['FAIL','SKIP'].includes(check.status));
  const sources = (row.citations || []).map(source => {
    const url = safeUrl(source.url);
    return '<li>' + (url ? '<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">' + esc(source.title || url) + '</a>' :
      esc(source.title || source.url || JSON.stringify(source))) + '</li>';
  }).join('');
  $('#drawerContent').innerHTML = '<p class="eyebrow">ПРОГОН #' + state.run.id + ' · ' + attemptLabel(row) + '</p><h2 id="detailTitle">' + esc(row.question) + '</h2>' +
    (technical(row) ? '<p class="notice error">' + esc(technicalKind(row)) + ': ' + esc(row.technical_error || 'Сбой выполнения') + '. Оценка качества LLM недоступна; полученный ответ и алгоритмические данные сохранены.</p>' : '') +
    (pendingReview(row) ? '<p class="notice">Требуется ручная проверка: ' + esc((evaluation.uncertainty_reasons || []).join('; ') || 'флаг судьи, расхождение оценок или неполная алгоритмическая проверка') + '</p>' : '') +
    '<div class="verdict-grid">' + [['LLM',llm(row)],['Алгоритм',algo(row)],['Combined',row.auto_status],['Ручная',row.manual_status]].map(([label,value]) =>
      '<div><small>' + label + '</small>' + badge(value) + '</div>').join('') + '</div>' +
    '<section class="drawer-section"><h3>Ответ агента</h3>' + textBlock(row.answer || 'Ответ ещё не получен') + '</section>' +
    '<section class="drawer-section"><h3>Причина оценки LLM</h3>' + textBlock(technical(row) ? 'Оценка не получена из-за технической ошибки' : evaluation.reason || 'Оценка ещё не получена') +
    (technical(row) ? '' : evaluationSummary(evaluation)) +
    listItems('Критические нарушения',evaluation.critical_violations?.length ? evaluation.critical_violations : evaluation.critical_flags) +
    listItems('Неверные факты',evaluation.incorrect_facts) + listItems('Пропущенные факты',evaluation.missing_facts) +
    listItems('Проблемы источников',evaluation.source_issues) + listItems('Недостаток контекста',evaluation.uncertainty_reasons) +
    listItems('Неподтверждённые тезисы',evaluation.unsupported_claims) + '</section>' +
    '<section class="drawer-section"><h3>Алгоритмическая проверка</h3>' + textBlock(algorithm?.reason || 'Алгоритмической оценки нет') +
    listItems('Критические флаги',algorithm?.critical_flags) + listItems('Не пройдено / не определено',checks.map(check => check.status + ': ' + check.label + ' — ' + check.details)) + '</section>' +
    '<section class="drawer-section"><h3>Ожидаемое поведение</h3>' + textBlock(row.expected) + '<h4>Основания</h4>' + textBlock(row.evidence) +
    '<h4>Запрещено и критическое условие</h4>' + textBlock(row.forbidden + '\n' + row.critical_if) + '</section>' +
    '<section class="drawer-section"><h3>Источники ответа</h3>' + (sources ? '<ul>' + sources + '</ul>' : '<p class="muted">Отдельные citations не переданы. Указания на разделы отчёта смотрите в тексте ответа.</p>') + '</section>' +
    '<section class="drawer-section"><h3>Ручная оценка</h3><form id="reviewForm"><label>Статус<select id="manualStatus"><option value="">Использовать автооценку</option>' +
    ['PASS','PARTIAL','FAIL','CRITICAL'].map(status => '<option' + (row.manual_status === status ? ' selected' : '') + '>' + status + '</option>').join('') +
    '</select></label><label>Комментарий<textarea id="manualComment" maxlength="4000">' + esc(row.manual_comment) +
    '</textarea></label><button class="primary" id="saveReviewButton" type="submit">Сохранить оценку</button></form></section>' +
    '<details><summary>Технические детали</summary><pre>' + esc(JSON.stringify({state:row.state,response_id:row.response_id,latency_ms:row.latency_ms,usage:row.usage,tool_calls:row.tool_calls,auto_evaluation:evaluation},null,2)) +
    '</pre><button class="secondary" id="loadRawButton">Загрузить сырой ответ</button><pre id="rawResponse"></pre></details>';
  $('#reviewForm').onsubmit = event => { event.preventDefault(); handled(saveReview)(event); };
  $('#loadRawButton').onclick = handled(loadRaw);
  showDialog('detailDrawer');
}
async function saveReview(event) {
  event.preventDefault();
  if (!requireToken()) return;
  const detail = {...state.detail}, button = $('#saveReviewButton');
  button.disabled = true;
  try {
    await api('/api/results/' + detail.id, {method:'PATCH',admin:true,body:JSON.stringify({manual_status:$('#manualStatus').value || null,manual_comment:$('#manualComment').value || null})});
    closeDialog('detailDrawer'); toast('Ручная оценка сохранена.');
    ++state.compareRequest; $('#comparisonContent').innerHTML = '<p class="muted">Ручная оценка изменилась. Обновите сравнение.</p>';
    if (state.selected === detail.runId) await loadRun(detail.runId, {quiet:true});
    if (state.view === 'history') await loadHistory();
  } finally { button.disabled = false; }
}
async function loadRaw() {
  if (!requireToken()) return;
  const detail = {...state.detail};
  const run = await api('/api/runs/' + detail.runId + '?raw=true', {admin:true});
  if (state.detail?.id === detail.id && state.detail?.runId === detail.runId)
    $('#rawResponse').textContent = JSON.stringify(run.results.find(row => row.id === detail.id)?.raw_response ?? null, null, 2);
}
async function loadHistory(reset = false) {
  if (reset) state.historyOffset = 0;
  const request = ++state.historyRequest;
  const params = new URLSearchParams({q:$('#historySearch').value,status:$('#historyStatus').value,sort:$('#historySort').value,offset:state.historyOffset,limit:21});
  const runs = await api('/api/runs?' + params);
  if (request !== state.historyRequest) return;
  state.historyMore = runs.length > 20; state.history = runs.slice(0,20);
  if (!state.history.length && state.historyOffset > 0) { state.historyOffset = Math.max(0,state.historyOffset - 20); return loadHistory(); }
  mergeRuns(state.history); renderHistory(); renderCompareSelectors(); schedulePoll();
}
function renderHistory() {
  $('#historyCount').textContent = state.history.length + ' на странице';
  $('#historyPage').textContent = 'Страница ' + (state.historyOffset / 20 + 1);
  $('#historyPrev').disabled = state.historyOffset === 0; $('#historyNext').disabled = !state.historyMore;
  $('#historyTable').innerHTML = state.history.length ? '<table class="history-table"><thead><tr><th>Прогон</th><th>Версии</th><th>Состояние</th><th>Выполнение</th><th>GTSR / ошибки</th><th>Действия</th></tr></thead><tbody>' +
    state.history.map(run => '<tr><td class="name-cell"><button class="link-button" data-open="' + run.id + '">#' + run.id + ' · «' + esc(run.name) +
      '»</button><small>' + esc(date(run.created_at)) + '</small></td><td><p>' + esc(run.judge_model) + '</p><small>Агент: ' +
      esc(promptLabel(run)) + '</small><small>Судья: ' + esc(run.provenance?.judge_prompt_version || 'Версия неизвестна') +
      '</small></td><td>' + badge(live(run),lifecycleLabels[live(run)] || run.status) + '</td><td>' + run.execution.processed + ' / ' +
      run.execution.total + '<small>Оценено: ' + run.execution.evaluated + '</small></td><td>' + run.metrics.gtsr.value +
      ' / 40<small>Тех. ошибок: ' + run.execution.errors + '</small></td><td><div class="history-actions"><button class="link-button" data-open="' +
      run.id + '">Открыть</button><a href="/api/runs/' + run.id + '/export/csv" download>CSV</a><a href="/api/runs/' + run.id +
      '/export/pdf" download>Отчёт / PDF</a>' + (activeStatuses.has(run.status) ? '<button class="link-button" data-stop="' + run.id + '"' +
      (!canStop(run) || state.busy ? ' disabled' : '') + '>' + (run.cancel_requested ? 'Останавливается…' : 'Остановить') + '</button>' : '') +
      '<button class="link-button" data-delete="' + run.id + '"' + (!canDelete(run) || state.busy ? ' disabled title="Дождитесь остановки worker"' : '') +
      '>Удалить</button></div></td></tr>').join('') + '</tbody></table>' : '<div class="empty">Прогоны не найдены.</div>';
}
function renderCompareSelectors() {
  for (const id of ['compareA','compareB']) {
    const value = $('#' + id).value;
    $('#' + id).innerHTML = '<option value="">Выберите прогон</option>' + state.runs.map(runOption).join('');
    if (state.runs.some(run => String(run.id) === value)) $('#' + id).value = value;
  }
  $('#compareButton').disabled = state.runs.length < 2;
}
async function compareRuns() {
  const a = $('#compareA').value, b = $('#compareB').value;
  if (!a || !b || a === b) { toast('Выберите два разных прогона.'); return; }
  const request = ++state.compareRequest; $('#compareButton').disabled = true;
  $('#comparisonContent').textContent = 'Сравниваем…';
  try {
    const result = await api('/api/compare?baseline=' + a + '&candidate=' + b);
    if (request !== state.compareRequest) return;
    const labels = {improved:'Улучшение',regressed:'Ухудшение',unchanged:'Без изменений',unavailable:'Не сопоставимо'};
    $('#comparisonContent').innerHTML = '<p>' + Object.entries(labels).map(([key,label]) => label + ': <b>' + (result.counts[key] || 0) + '</b>').join(' · ') +
      '</p><div class="notice"><ul>' + result.warnings.map(warning => '<li>' + esc(warning) + '</li>').join('') +
      '</ul></div><details><summary>Сопоставимость моделей, версий и данных</summary><div class="table-wrap"><table><thead><tr><th>Параметр</th><th>Базовый #' + a + '</th><th>Новый #' +
      b + '</th></tr></thead><tbody>' + result.dimensions.map(dimension => '<tr><td>' + esc(dimension.label) + '</td><td class="version-cell">' +
      esc(dimension.baseline || 'Версия неизвестна') + '</td><td class="version-cell">' + esc(dimension.candidate || 'Версия неизвестна') + '</td></tr>').join('') +
      '</tbody></table></div></details><div class="table-wrap"><table class="comparison-table"><thead><tr><th>Кейс / повтор</th><th>Базовый #' + a + '</th><th>Новый #' + b +
      '</th><th>Изменение итога</th></tr></thead><tbody>' + result.rows.map(row => '<tr><td>' + attemptLabel(row) + '<small>' + esc(row.question) +
      '</small></td><td>' + comparisonCell(a,row.baseline) + '</td><td>' + comparisonCell(b,row.candidate) + '</td><td class="change-' +
      row.change + '">' + labels[row.change] + '<small>' + esc(row.reason || '') + '</small></td></tr>').join('') + '</tbody></table></div>';
  } catch (error) {
    if (request === state.compareRequest) $('#comparisonContent').textContent = 'Сравнение недоступно: ' + error.message;
    throw error;
  } finally { $('#compareButton').disabled = state.runs.length < 2; }
}
function comparisonCell(runId, row) {
  if (!row) return 'Кейс отсутствует';
  return '<button class="link-button" data-compare-detail="' + row.id + '" data-run="' + runId + '">' +
    (row.state === 'error' || row.technical_error ? 'Техническая ошибка' : esc(row.effective || 'Без оценки')) +
    '</button><small>LLM: ' + esc(row.llm || '—') + ' · алгоритм: ' + esc(row.algorithmic || '—') +
    '</small><small>Combined: ' + esc(row.combined || '—') + ' · ручная: ' + esc(row.manual || '—') + '</small>';
}
async function runAction(id, action) {
  if (!requireToken() || state.busy) return;
  id = Number(id);
  const run = state.runs.find(item => item.id === id);
  if (!run) return;
  const deleting = action === 'delete';
  if (deleting ? !canDelete(run) : !canStop(run)) return;
  askConfirmation(deleting ? 'Удалить прогон' : 'Остановить прогон',
    'Прогон #' + run.id + ' «' + run.name + '». ' +
    (deleting ? 'Все его результаты и ручные оценки будут удалены без возможности восстановления.' : 'Текущий запрос может завершиться. Новые этапы запускаться не будут.'),
    async () => {
      state.busy = action; stopPoll(); renderControls(); renderHistory();
      try {
        await api('/api/runs/' + run.id + (deleting ? '' : '/cancel'), {method:deleting ? 'DELETE' : 'POST',admin:true});
        if (deleting) {
          const wasCurrent = state.selected === run.id;
          removeRun(run.id);
          if (wasCurrent) await loadRuns();
        } else {
          run.cancel_requested = true;
          if (state.selected === run.id) await loadRun(run.id, {quiet:true});
        }
        if (state.view === 'history') await loadHistory();
        toast(deleting ? 'Прогон #' + run.id + ' удалён.' : 'Остановка запрошена.');
      } catch (error) {
        if (error.status === 404) removeRun(run.id);
        if (error.status === 409 && state.selected === run.id) await loadRun(run.id, {quiet:true});
        throw error;
      } finally { state.busy = null; renderControls(); renderHistory(); schedulePoll(); }
    });
}
async function startDraft() {
  if (!requireToken() || !state.run || state.busy) return;
  const id = state.run.id; state.busy = 'start'; renderControls();
  try { await api('/api/runs/' + id + '/start', {method:'POST',admin:true}); await loadRun(id); }
  finally { state.busy = null; renderControls(); schedulePoll(); }
}
async function createAndStart(event) {
  event.preventDefault(); if (!requireToken()) return;
  const button = $('#createRunButton'); button.disabled = true;
  let created = null;
  try {
    created = await api('/api/runs', {method:'POST',admin:true,body:JSON.stringify({name:$('#runName').value.trim(),prompt_version:$('#promptVersion').value.trim(),judge_model:$('#judgeModel').value,scope:$('#runScope').value})});
    await api('/api/runs/' + created.id + '/start', {method:'POST',admin:true});
    closeDialog('runModal'); await loadRuns(created.id); switchView('dashboard'); toast('Прогон запущен.');
  } catch (error) {
    if (created) { closeDialog('runModal'); await loadRuns(created.id); }
    throw error;
  } finally { button.disabled = false; }
}
function renderCases() {
  $('#caseGrid').innerHTML = (state.cases?.cases || []).map(row => '<article class="panel case-card"><span class="eyebrow">' +
    esc(row.id) + ' · ' + (row.is_web ? 'WEB' : row.is_boundary ? 'BOUNDARY' : 'MAIN') + '</span><h3>' + esc(row.category) +
    '</h3><p>' + esc(row.question) + '</p></article>').join('');
}
async function init() {
  $('#newRunButton').disabled = true;
  const [config,cases,health] = await Promise.all([api('/api/config'),api('/api/cases'),api('/api/health')]);
  state.config = config; state.cases = cases;
  const profiles = config.judge_profiles || config.judge_models.map(model => ({model_id:model,display_name:model,provider:'configured',tier:'standard',available:true}));
  $('#judgeModel').innerHTML = profiles.map(profile => '<option value="' + esc(profile.model_id) + '"' +
    (profile.model_id === config.default_judge_model ? ' selected' : '') + '>' +
    esc(profile.display_name) + ' · ' + esc(profile.provider) + '</option>').join('');
  const updateHint = () => { const profile = profiles.find(item => item.model_id === $('#judgeModel').value); $('#judgeModelHint').textContent =
    profile?.tier === 'fast' ? 'Быстрая модель для предварительной оценки.' :
    'Все модели работают через CAILA OpenAI adapter.'; };
  $('#judgeModel').onchange = updateHint; updateHint();
  $('#healthText').textContent = health.agent_configured && health.judge_configured ? 'Подключения настроены' : 'Для запуска нужна настройка';
  $('#newRunButton').disabled = false; renderCases(); await loadRuns();
  $('#loading').classList.add('hidden'); hideError();
}

// Native dialog gives Escape, focus trapping and inert background; restore focus even
// after a polling refresh has replaced the original trigger.
$$('dialog').forEach(dialog => dialog.addEventListener('close', () => {
  const target = dialog.returnFocus;
  if (target?.isConnected) target.focus(); else $('#newRunButton').focus();
}));
document.addEventListener('click', handled(async event => {
  const button = event.target.closest('button');
  if (!button || button.disabled) return;
  if (button.dataset.close) closeDialog(button.dataset.close);
  if (button.dataset.view) switchView(button.dataset.view);
  if (button.dataset.action === 'new') openRunModal();
  if (button.dataset.action === 'results') switchView('results');
  if (button.dataset.detail) openDetail(button.dataset.detail);
  if (button.dataset.open) { await loadRun(button.dataset.open); switchView('dashboard'); }
  if (button.dataset.stop) await runAction(button.dataset.stop,'cancel');
  if (button.dataset.delete) await runAction(button.dataset.delete,'delete');
  if (button.dataset.compareDetail) { await loadRun(button.dataset.run); openDetail(button.dataset.compareDetail); }
}));
$('#newRunButton').onclick = openRunModal;
$('#runPicker').onchange = handled(event => loadRun(event.target.value));
$('#runForm').onsubmit = event => { event.preventDefault(); handled(createAndStart)(event); };
$('#tokenButton').onclick = () => { $('#adminToken').value = token(); showDialog('tokenModal'); };
$('#tokenForm').onsubmit = event => { event.preventDefault(); sessionStorage.setItem('adminToken',$('#adminToken').value); closeDialog('tokenModal'); toast('Токен сохранён для этой вкладки.'); };
$('#cancelRunButton').onclick = handled(() => state.run && runAction(state.run.id,'cancel'));
$('#deleteRunButton').onclick = handled(() => state.run && runAction(state.run.id,'delete'));
$('#startDraftButton').onclick = handled(startDraft);
$('#retryButton').onclick = handled(async () => { hideError(); if (!state.config) await init(); else { await loadRuns(); if (state.view === 'history') await loadHistory(); } });
['resultSearch','statusFilter','categoryFilter','technicalFilter','reviewFilter','disagreementFilter'].forEach(id => $('#' + id).addEventListener('input',filterResults));
let searchTimer;
$('#historySearch').oninput = () => { clearTimeout(searchTimer); ++state.historyRequest; searchTimer = setTimeout(handled(() => loadHistory(true)),250); };
['historyStatus','historySort'].forEach(id => $('#' + id).onchange = handled(() => loadHistory(true)));
$('#historyPrev').onclick = handled(() => { state.historyOffset = Math.max(0,state.historyOffset - 20); return loadHistory(); });
$('#historyNext').onclick = handled(() => { state.historyOffset += 20; return loadHistory(); });
$('#compareButton').onclick = handled(compareRuns);
['compareA','compareB'].forEach(id => $('#' + id).onchange = () => {
  ++state.compareRequest; $('#comparisonContent').textContent = 'Выбор изменился. Нажмите «Сравнить».';
});
handled(init)();
