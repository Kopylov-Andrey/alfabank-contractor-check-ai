const state={runs:[],run:null,cases:null,config:null,poll:null};
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const esc=v=>String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const token=()=>sessionStorage.getItem('adminToken')||'';
const fmtPct=v=>v==null?'—':`${Number(v).toFixed(1).replace('.0','')}%`;
const fmtMs=v=>v==null?'—':v>=1000?`${(v/1000).toFixed(2)} с`:`${Math.round(v)} мс`;
const statusClass=s=>`status status-${s||'UNREVIEWED'}`;
const effective=r=>r.effective_status||'UNREVIEWED';

async function api(path,options={}){
  const headers={'Content-Type':'application/json',...(options.headers||{})};
  if(options.admin)headers['X-Admin-Token']=token();
  const res=await fetch(path,{...options,headers});
  if(!res.ok){let msg=`HTTP ${res.status}`;try{msg=(await res.json()).detail||msg}catch{}throw new Error(msg)}
  return res.json();
}
function toast(message,error=false){const el=$('#toast');el.textContent=message;el.style.borderColor=error?'#ff5f7077':'#50e3c255';el.classList.remove('hidden');setTimeout(()=>el.classList.add('hidden'),3500)}
function openRunModal(){$('#runModal').classList.remove('hidden');$('#runName').value=`Regression · ${new Date().toLocaleString('ru-RU',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})}`}
function closeModal(id){$('#'+id).classList.add('hidden')}
window.openRunModal=openRunModal;window.closeModal=closeModal;

function switchView(name){
  $$('.view').forEach(v=>v.classList.remove('active'));$('#'+name+'View').classList.add('active');
  $$('.nav-item').forEach(v=>v.classList.toggle('active',v.dataset.view===name));
  $('#pageTitle').textContent={dashboard:'Обзор качества',results:'Результаты проверки',compare:'Сравнение версий',cases:'Замороженный набор'}[name];
  if(name==='results')renderResults();if(name==='compare')renderCompareSelectors();if(name==='cases')renderCases();
}
window.switchView=switchView;

async function loadHealth(){
  try{const h=await api('/api/health');$('#healthDot').className=h.agent_configured&&h.judge_configured?'ok':'bad';$('#healthText').textContent=h.agent_configured&&h.judge_configured?'Контур готов':'Нужна настройка';$('#healthMeta').textContent=`${h.database} · agent ${h.agent_configured?'on':'off'} · judge ${h.judge_configured?'on':'off'}`}
  catch{$('#healthDot').className='bad';$('#healthText').textContent='Backend недоступен'}
}
async function loadRuns(preferred){
  state.runs=await api('/api/runs');
  const picker=$('#runPicker');picker.innerHTML=state.runs.length?state.runs.map(r=>`<option value="${r.id}">${esc(r.name)} · ${r.status}</option>`).join(''):'<option>Прогонов пока нет</option>';
  const id=preferred||state.run?.id||state.runs[0]?.id;
  if(id){picker.value=String(id);await loadRun(id)}else{state.run=null;renderDashboard()}
}
async function loadRun(id){
  state.run=await api(`/api/runs/${id}`);renderDashboard();
  if(['queued','running'].includes(state.run.status)){if(!state.poll)state.poll=setInterval(()=>refreshCurrent(),2500)}else if(state.poll){clearInterval(state.poll);state.poll=null}
}
async function refreshCurrent(){if(!state.run)return;await loadRun(state.run.id);await loadRunsLight()}
async function loadRunsLight(){state.runs=await api('/api/runs')}

function metricCard(label,m,threshold,invert=false){
  const value=m?.percent==null?(m?.value??'—'):fmtPct(m.percent);const ok=m?.pass;
  return `<article class="metric-card"><div class="label">${label}</div><strong>${value}</strong><small class="${ok?'pass-text':ok===false?'fail-text':''}">${ok?'PASS':ok===false?'НЕ ПРОЙДЕН':'ОЖИДАЕТ'} · ${threshold}</small></article>`
}
function renderDashboard(){
  const empty=!state.run;$('#emptyState').classList.toggle('hidden',!empty);$('#dashboardContent').classList.toggle('hidden',empty);if(empty)return;
  const r=state.run,m=r.metrics,p=m.progress;
  $('#runStatus').textContent=r.status.toUpperCase();$('#gateValue').textContent=m.release_gate;$('#gateValue').className=m.release_gate==='PASS'?'pass-text':m.release_gate==='FAIL'?'fail-text':'';
  $('#gateSubtitle').textContent=m.release_gate==='PASS'?'Все критерии выполнены':m.release_gate==='FAIL'?'Есть непройденные критерии':'Ожидает полного прогона';
  $('#progressBar').style.width=`${p.percent||0}%`;$('#progressLabel').textContent=`${p.completed} из ${p.total}`;$('#progressPercent').textContent=fmtPct(p.percent||0);
  $('#gtsrValue').textContent=m.gtsr.value;$('#criticalValue').textContent=m.critical.value;
  $('#metricGrid').innerHTML=[
    metricCard('Фактическая корректность',m.factual_correctness,'≥90%'),metricCard('Полнота фактов',m.completeness,'≥90%'),
    metricCard('Покрытие источниками',m.source_coverage,'≥95%'),metricCard('Полезность',m.usefulness,'≥80%'),
    metricCard('Boundary устойчивость',m.stable_boundary,'≥7/8')].join('');
  const colors={PASS:'#4ee28a',PARTIAL:'#ffbd59',FAIL:'#ff6c62',CRITICAL:'#ff3459',UNREVIEWED:'#64748b'};const total=Math.max(1,Object.values(m.statuses).reduce((a,b)=>a+b,0));
  $('#statusDistribution').innerHTML=Object.entries(m.statuses).map(([k,v])=>`<div class="dist-row"><span>${k}</span><div class="dist-track"><i style="width:${v/total*100}%;background:${colors[k]}"></i></div><b>${v}</b></div>`).join('');
  $('#latencyGrid').innerHTML=[['Mean',m.latency.mean_ms],['Median',m.latency.median_ms],['p95',m.latency.p95_ms],['Max',m.latency.max_ms]].map(x=>`<div class="latency-box"><span>${x[0]}</span><strong>${fmtMs(x[1])}</strong></div>`).join('');
  const order={CRITICAL:0,FAIL:1,PARTIAL:2,PASS:3,UNREVIEWED:4};
  const sorted=[...r.results].filter(x=>x.state!=='pending').sort((a,b)=>order[effective(a)]-order[effective(b)]).slice(0,6);
  $('#recentResults').innerHTML=sorted.length?sorted.map(resultRow).join(''):'<p class="threshold">Ответов пока нет.</p>';
}
function resultRow(r){return `<div class="result-row" onclick="openDetail(${r.id})"><span class="case-id">${esc(r.case_id)}</span><span class="${statusClass(effective(r))}">${effective(r)}</span><span class="result-question">${esc(r.question)}</span><span class="result-latency">${fmtMs(r.latency_ms)}</span><span>›</span></div>`}

function renderResults(){
  if(!state.run){$('#resultsTable').innerHTML='<div class="empty"><p>Сначала создайте прогон.</p></div>';return}
  const categories=[...new Set(state.run.results.map(r=>r.category))].sort();$('#categoryFilter').innerHTML='<option value="">Все категории</option>'+categories.map(c=>`<option>${esc(c)}</option>`).join('');filterResults();
}
function filterResults(){
  if(!state.run)return;const q=$('#resultSearch').value.toLowerCase(),s=$('#statusFilter').value,c=$('#categoryFilter').value;
  const rows=state.run.results.filter(r=>(!q||`${r.case_id} ${r.question} ${r.answer||''} ${r.technical_error||''}`.toLowerCase().includes(q))&&(!s||effective(r)===s)&&(!c||r.category===c));
  $('#resultCount').textContent=`${rows.length} результатов`;$('#resultsTable').innerHTML=`<table class="data-table"><thead><tr><th>Кейс</th><th>Статус</th><th>Ответ</th><th>Категория</th><th>Время</th></tr></thead><tbody>${rows.map(r=>`<tr onclick="openDetail(${r.id})"><td class="case-id">${esc(r.case_id)}</td><td><span class="${statusClass(effective(r))}">${effective(r)}</span></td><td class="answer-preview">${esc(r.answer||r.technical_error||r.state)}</td><td>${esc(r.category)}</td><td>${fmtMs(r.latency_ms)}</td></tr>`).join('')}</tbody></table>`;
}
function boolLabel(v){return v==null?'—':v?'Да':'Нет'}
function openDetail(id){
  const r=state.run.results.find(x=>x.id===id);if(!r)return;const e=r.auto_evaluation||{};
  $('#drawerContent').innerHTML=`<p class="eyebrow">${esc(r.case_id)} · ${esc(r.category)}</p><h2>${esc(r.question)}</h2><span class="${statusClass(effective(r))}">${effective(r)}</span>
  <div class="drawer-section"><h3>Ответ агента</h3><div class="text-block">${esc(r.answer||r.technical_error||'Ответ ещё не получен')}</div></div>
  <div class="drawer-section"><h3>Вердикт LLM-судьи</h3><div class="text-block">${esc(e.reason||'Оценка ещё не выполнена')}</div><div class="eval-grid">
    ${[['Факты',boolLabel(e.factual_correct)],['Полезность',boolLabel(e.useful)],['Ложный отказ',boolLabel(e.false_refusal)],['Вердикт пользователю',boolLabel(e.verdict_given)],['Web Search',boolLabel(e.web_search_used)],['Маркировка Web',boolLabel(e.web_search_labeled_correctly)]].map(x=>`<div class="eval-item"><span>${x[0]}</span><b>${x[1]}</b></div>`).join('')}</div></div>
  <div class="drawer-section"><h3>Ожидаемое поведение</h3><div class="text-block">${esc(r.expected)}</div></div>
  <div class="drawer-section"><h3>Ручная проверка</h3><label><select id="manualStatus"><option value="">Использовать автооценку</option>${['PASS','PARTIAL','FAIL','CRITICAL'].map(s=>`<option ${r.manual_status===s?'selected':''}>${s}</option>`).join('')}</select></label><textarea id="manualComment" placeholder="Комментарий проверяющего">${esc(r.manual_comment||'')}</textarea><button class="primary wide" onclick="saveReview(${r.id})">Сохранить оценку</button></div>
  <details class="details"><summary>Технические детали</summary><pre>${esc(JSON.stringify({response_id:r.response_id,usage:r.usage,citations:r.citations,tool_calls:r.tool_calls,auto_evaluation:r.auto_evaluation},null,2))}</pre><button class="ghost" onclick="loadRaw(${r.id})">Загрузить сырой ответ</button><pre id="rawResponse"></pre></details>`;
  $('#detailDrawer').classList.remove('hidden')
}
window.openDetail=openDetail;
function closeDrawer(){$('#detailDrawer').classList.add('hidden')}window.closeDrawer=closeDrawer;
async function saveReview(id){try{await api(`/api/results/${id}`,{method:'PATCH',admin:true,body:JSON.stringify({manual_status:$('#manualStatus').value||null,manual_comment:$('#manualComment').value||null})});toast('Ручная оценка сохранена');closeDrawer();await loadRun(state.run.id)}catch(e){toast(e.message,true)}}window.saveReview=saveReview;
async function loadRaw(id){try{const run=await api(`/api/runs/${state.run.id}?raw=true`,{admin:true});const r=run.results.find(x=>x.id===id);$('#rawResponse').textContent=JSON.stringify(r.raw_response,null,2)}catch(e){toast(e.message,true)}}window.loadRaw=loadRaw;

function renderCompareSelectors(){const opts=state.runs.map(r=>`<option value="${r.id}">${esc(r.name)}</option>`).join('');$('#compareA').innerHTML=opts;$('#compareB').innerHTML=opts;if(state.runs[1])$('#compareB').value=state.runs[1].id}
async function compareRuns(){
  const [a,b]=await Promise.all([api(`/api/runs/${$('#compareA').value}`),api(`/api/runs/${$('#compareB').value}`)]);const keys=[['GTSR','gtsr'],['Фактическая корректность','factual_correctness'],['Полнота','completeness'],['Источники','source_coverage'],['Полезность','usefulness'],['Boundary','stable_boundary']];
  function card(run,other){return `<article class="comparison-card"><h3>${esc(run.name)} · ${esc(run.prompt_version)}</h3>${keys.map(([label,k])=>{const x=run.metrics[k].percent,y=other.metrics[k].percent,d=x!=null&&y!=null?x-y:null;return `<div class="compare-row"><span>${label}</span><b>${fmtPct(x)}</b><span class="${d>0?'delta-up':d<0?'delta-down':''}">${d==null?'—':`${d>0?'+':''}${d.toFixed(1)}`}</span></div>`}).join('')}<div class="compare-row"><span>p95 latency</span><b>${fmtMs(run.metrics.latency.p95_ms)}</b><span></span></div></article>`}$('#comparisonContent').innerHTML=card(a,b)+card(b,a)
}
function renderCases(){if(!state.cases)return;$('#caseGrid').innerHTML=state.cases.cases.map(c=>`<article class="case-card"><div class="case-top"><span class="case-id">${esc(c.id)}</span><span class="tag">${c.is_web?'WEB':c.is_boundary?'BOUNDARY':'MAIN'}</span></div><h3>${esc(c.category)}</h3><p>${esc(c.question)}</p></article>`).join('')}

async function createAndStart(){
  if(!token()){closeModal('runModal');$('#tokenModal').classList.remove('hidden');toast('Сначала укажите токен запуска',true);return}
  const btn=$('#createRunButton');btn.disabled=true;btn.textContent='Создаём…';try{const run=await api('/api/runs',{method:'POST',admin:true,body:JSON.stringify({name:$('#runName').value,prompt_version:$('#promptVersion').value,judge_model:$('#judgeModel').value,scope:$('#runScope').value})});await api(`/api/runs/${run.id}/start`,{method:'POST',admin:true});closeModal('runModal');toast('Прогон запущен');await loadRuns(run.id)}catch(e){toast(e.message,true)}finally{btn.disabled=false;btn.textContent='Создать и запустить'}
}

async function init(){
  $$('.nav-item').forEach(b=>b.onclick=()=>switchView(b.dataset.view));$('#newRunButton').onclick=openRunModal;$('#runPicker').onchange=e=>loadRun(e.target.value);$('#resultSearch').oninput=filterResults;$('#statusFilter').onchange=filterResults;$('#categoryFilter').onchange=filterResults;$('#compareButton').onclick=compareRuns;$('#createRunButton').onclick=createAndStart;
  $('#tokenButton').onclick=()=>{$('#adminToken').value=token();$('#tokenModal').classList.remove('hidden')};$('#saveTokenButton').onclick=()=>{sessionStorage.setItem('adminToken',$('#adminToken').value);closeModal('tokenModal');toast('Токен сохранён до закрытия вкладки')};
  $('#detailDrawer').onclick=e=>{if(e.target.id==='detailDrawer')closeDrawer()};
  try{const [config,cases]=await Promise.all([api('/api/config'),api('/api/cases')]);state.config=config;state.cases=cases;$('#judgeModel').innerHTML=config.judge_models.map(m=>`<option ${m===config.default_judge_model?'selected':''}>${esc(m)}</option>`).join('');await Promise.all([loadHealth(),loadRuns()])}catch(e){toast(e.message,true)}
}
init();
