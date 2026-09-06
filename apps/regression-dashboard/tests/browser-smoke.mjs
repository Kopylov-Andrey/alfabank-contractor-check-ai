// Real Chrome smoke tests using CDP and Node built-ins; no npm dependency or paid API.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {existsSync, mkdirSync, mkdtempSync, writeFileSync} from 'node:fs';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import net from 'node:net';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const python = process.env.PYTHON_BIN || (process.platform === 'win32' ? join(root,'.venv','Scripts','python.exe') : 'python');
const chrome = process.env.CHROME_BIN || [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser'
].find(existsSync);
assert(chrome, 'Set CHROME_BIN to an installed Chrome/Chromium executable');
mkdirSync(join(root,'.pytest_cache'), {recursive:true});
const artifacts = mkdtempSync(join(root,'.pytest_cache','browser-'));
const delay = ms => new Promise(resolve => setTimeout(resolve,ms));
async function freePort() {
  const server = net.createServer();
  await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return port;
}
async function until(fn, message, timeout = 12000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    try { const result = await fn(); if (result) return result; } catch {}
    await delay(60);
  }
  throw new Error('Timeout: ' + message);
}
const port = await freePort(), debugPort = await freePort();
const base = 'http://127.0.0.1:' + port;
let serverLog = '', browserLog = '', browser, cdp;
const server = spawn(python,['-m','uvicorn','browser_server:app','--app-dir','tests','--host','127.0.0.1','--port',String(port)],{
  cwd:root, windowsHide:true, stdio:['ignore','pipe','pipe'],
  env:{...process.env,BROWSER_TEST_MODE:'1',BROWSER_TEST_DB:join(artifacts,'fixture.db'),
    YANDEX_API_KEY:'',JUDGE_API_KEY:'',ADMIN_TOKEN:'browser-test-only',PYTHONPATH:root}
});
server.stdout.on('data', data => {serverLog += data;});
server.stderr.on('data', data => {serverLog += data;});
class CDP {
  constructor(socket) {
    this.socket = socket; this.nextId = 0; this.pending = new Map(); this.events = [];
    socket.addEventListener('message', event => {
      const message = JSON.parse(event.data);
      if (message.id) {
        const pending = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) pending?.reject(new Error(JSON.stringify(message.error))); else pending?.resolve(message.result);
      } else this.events.push(message);
    });
  }
  send(method, params = {}) {
    const id = ++this.nextId;
    return new Promise((resolve,reject) => { this.pending.set(id,{resolve,reject}); this.socket.send(JSON.stringify({id,method,params})); });
  }
  async eval(expression) {
    const result = await this.send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    return result.result.value;
  }
}
try {
  await until(async () => (await fetch(base + '/api/health')).ok,'fixture server');
  browser = spawn(chrome,['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
    '--disable-background-networking','--disable-extensions','--disable-component-update',
    '--remote-debugging-port=' + debugPort,'--user-data-dir=' + join(artifacts,'chrome-profile'),'about:blank'],{
    windowsHide:true,stdio:['ignore','pipe','pipe']
  });
  browser.stderr.on('data',data => {browserLog += data;});
  const target = await until(async () => (await (await fetch('http://127.0.0.1:' + debugPort + '/json/list')).json()).find(page => page.type === 'page'),'Chrome debugger');
  const socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject) => {socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  cdp = new CDP(socket);
  await cdp.send('Page.enable'); await cdp.send('Runtime.enable'); await cdp.send('Network.enable');
  await cdp.send('Page.bringToFront');
  await cdp.send('Emulation.setFocusEmulationEnabled',{enabled:true});
  const evaluate = expression => cdp.eval(expression);
  const click = selector => evaluate('(async function(){document.querySelector(' + JSON.stringify(selector) + ').click();await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);})()');
  const value = (selector, val) => evaluate('(function(){const e=document.querySelector(' + JSON.stringify(selector) + ');e.value=' + JSON.stringify(val) + ';e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));})()');
  const wait = expression => until(() => evaluate(expression),expression);
  const key = async name => {
    const code = {Enter:13,Tab:9,Escape:27}[name];
    await cdp.send('Input.dispatchKeyEvent',{type:name==='Enter'?'keyDown':'rawKeyDown',key:name,code:name,windowsVirtualKeyCode:code,nativeVirtualKeyCode:code,...(name==='Enter'?{text:'\r',unmodifiedText:'\r'}:{})});
    await cdp.send('Input.dispatchKeyEvent',{type:'keyUp',key:name,code:name,windowsVirtualKeyCode:code,nativeVirtualKeyCode:code});
  };
  await cdp.send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await cdp.send('Page.navigate',{url:base});
  await wait('state.run?.id===3 && document.querySelector("#loading").classList.contains("hidden")');
  assert.equal(await evaluate('getComputedStyle(document.body).backgroundColor'),'rgb(244, 245, 247)');
  assert.equal(await evaluate('document.querySelectorAll("#primaryMetrics .metric").length'),4);
  assert.equal(await evaluate('window.unsafeRendered'),undefined);
  assert.equal(await evaluate('document.querySelector("#exportCsvButton").getAttribute("href")'),'/api/runs/3/export/csv');
  assert.match(await evaluate('document.querySelector("#runIdentity").textContent'),/offline-judge/);
  // Responsive layout is tested in every main view at each requested width.
  for (const width of [1440,1024,390]) {
    await cdp.send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
    for (const view of ['dashboard','results','history','cases']) {
      await click('[data-view="' + view + '"]');
      if (view === 'history') await wait('state.history.length===3');
      assert(await evaluate('document.documentElement.scrollWidth <= innerWidth'),view + ' page overflow at ' + width);
    }
    await click('[data-view="dashboard"]');
    await evaluate('window.scrollTo(0,0)');
    const screenshot = await cdp.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    writeFileSync(join(artifacts,'overview-' + width + '.png'),Buffer.from(screenshot.data,'base64'));
  }
  await cdp.send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  // Real keyboard focus and native dialog behavior.
  await evaluate('document.querySelector("#newRunButton").focus()'); await key('Enter');
  await wait('document.querySelector("#runModal").open');
  await key('Tab');
  assert(await evaluate('document.querySelector("#runModal").contains(document.activeElement)'));
  await key('Escape');
  assert.equal(await evaluate('document.activeElement.id'),'newRunButton');
  await click('#tokenButton'); await value('#adminToken','browser-test-only');
  await click('#tokenForm button[type="submit"]');
  await wait('sessionStorage.getItem("adminToken")==="browser-test-only"');
  // Filters, safe HTML, reasons, manual review and focus restoration.
  await click('[data-view="results"]');
  await click('#technicalFilter');
  assert.equal(await evaluate('document.querySelectorAll("#resultsTable tbody tr").length'),1);
  await click('#technicalFilter'); await click('#reviewFilter');
  assert.equal(await evaluate('document.querySelectorAll("#resultsTable tbody tr").length'),11);
  await click('#reviewFilter'); await click('#disagreementFilter');
  assert.equal(await evaluate('document.querySelectorAll("#resultsTable tbody tr").length'),11);
  await click('#disagreementFilter');
  await value('#resultSearch','A05');
  await click('#resultsTable [data-detail]');
  await wait('document.querySelector("#detailDrawer").open');
  assert.equal(await evaluate('window.unsafeRendered'),undefined);
  assert.match(await evaluate('document.querySelector("#drawerContent").textContent'),/<script>/);
  await value('#manualStatus','PASS'); await value('#manualComment','Проверено в браузере');
  await click('#saveReviewButton');
  await wait('!document.querySelector("#detailDrawer").open && state.run.results.find(r=>r.case_id==="A05").manual_status==="PASS"');
  await value('#resultSearch','');
  // History filtering, open by ID, comparison and preserved selections.
  await click('[data-view="history"]'); await wait('state.history.length===3');
  await value('#historyStatus','cancelled'); await wait('state.history.length===1');
  assert.equal(await evaluate('state.history[0].id'),2);
  await click('#historyTable [data-open="2"]'); await wait('state.run?.id===2 && state.view==="dashboard"');
  assert.match(await evaluate('document.querySelector("#runIdentity").textContent'),/Остановлен/);
  await click('[data-view="history"]'); await value('#historyStatus',''); await wait('state.history.length===3');
  await value('#historySearch','Базовый'); await wait('state.history.length===1 && state.history[0].id===1');
  await value('#historySearch',''); await wait('state.history.length===3');
  await value('#historySort','asc'); await wait('state.history[0].id===1');
  await value('#compareA','1'); await value('#compareB','3'); await click('#compareButton');
  await wait('document.querySelectorAll(".comparison-table tbody tr").length===59');
  assert.match(await evaluate('document.querySelector("#comparisonContent").textContent'),/Не сопоставимо/);
  await evaluate('loadHistory()');
  assert.equal(await evaluate('document.querySelector("#compareA").value'),'1');
  // Browser obtains exports from exactly the opened run, including Russian text.
  const exportRun = await evaluate('state.run.id');
  const csv = await fetch(base + '/api/runs/' + exportRun + '/export/csv');
  const csvBytes = new Uint8Array(await csv.arrayBuffer());
  assert.deepEqual([...csvBytes.slice(0,3)],[239,187,191]);
  const report = await (await fetch(base + '/api/runs/' + exportRun + '/export/pdf')).text();
  assert(report.includes('Regression Report · #' + exportRun));
  // Create/start with OFFLINE clients, stop in flight, wait for terminal, delete.
  await click('#newRunButton'); await value('#runName','Browser offline run');
  await click('#createRunButton');
  await wait('state.run?.name==="Browser offline run" && state.run.status==="running"');
  const createdId = await evaluate('state.run.id');
  await click('#cancelRunButton');
  await wait('document.querySelector("#confirmModal").open');
  assert.match(await evaluate('document.querySelector("#confirmText").textContent'),new RegExp('#' + createdId));
  await click('#confirmAction');
  await wait('state.run?.status==="cancelled"');
  assert.equal(await evaluate('state.poll'),null);
  await click('#runMenu summary'); await click('#deleteRunButton');
  assert.match(await evaluate('document.querySelector("#confirmText").textContent'),/без возможности восстановления/);
  await click('#confirmAction');
  await wait('state.run && state.run.id!=='+createdId+' && state.busy===null && !state.runs.some(r=>r.id==='+createdId+')');
  assert(!(await evaluate('document.querySelector("#compareA").innerHTML')).includes('Browser offline run'));
  // External deletion of a selected active run: a pending refresh must converge,
  // never repopulate deleted data or poll 404 indefinitely.
  const currentId = await evaluate('state.run.id');
  await evaluate('state.run.status="running";schedulePoll()');
  assert.equal((await fetch(base + '/api/runs/' + currentId,{method:'DELETE',headers:{'X-Admin-Token':'browser-test-only'}})).status,200);
  await wait('state.run && state.run.id!=='+currentId+' && !state.runs.some(r=>r.id==='+currentId+')');
  assert.equal(await evaluate('state.poll'),null);
  // Delete remaining fixtures through the UI, including the final run.
  for (let i=0;i<4 && await evaluate('Boolean(state.run)');i++) {
    await evaluate('document.querySelector("#runMenu").open=true');
    await click('#deleteRunButton'); await click('#confirmAction');
    await wait('state.busy===null');
    await delay(150);
  }
  assert.equal(await evaluate('state.run'),null);
  assert.equal(await evaluate('state.poll'),null);
  assert(await evaluate('!document.querySelector("#emptyState").classList.contains("hidden")'));
  assert.equal(await evaluate('document.querySelector("#compareA").options.length'),1);
  // Empty and non-404 error states.
  await cdp.send('Network.setBlockedURLs',{urls:['*/api/runs*']});
  await cdp.send('Page.reload'); await wait('!document.querySelector("#loadError").classList.contains("hidden")');
  await cdp.send('Network.setBlockedURLs',{urls:[]}); await click('#retryButton');
  await wait('document.querySelector("#loadError").classList.contains("hidden")');
  assert.equal(cdp.events.filter(event => event.method === 'Runtime.exceptionThrown').length,0);
  const result = {status:'PASS', widths:[1440,1024,390], browser:'Chrome CDP', cases:[
    'navigation and responsive overflow','native dialogs: keyboard/Escape/focus','safe answer rendering',
    'technical/review/disagreement filters','manual review saved','history search/status/sort',
    'per-case comparison and preserved selection','CSV/report identity','offline start/stop/delete',
    'external deletion/404 polling recovery','delete last run and empty state','error/retry states'],
    artifacts};
  writeFileSync(join(artifacts,'result.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify(result,null,2));
} catch (error) {
  writeFileSync(join(artifacts,'server.log'),serverLog);
  writeFileSync(join(artifacts,'browser.log'),browserLog);
  if (cdp) {
    try {
      const shot = await cdp.send('Page.captureScreenshot',{format:'png'});
      writeFileSync(join(artifacts,'failure.png'),Buffer.from(shot.data,'base64'));
      console.error(await cdp.eval('JSON.stringify({view:state.view,run:state.run?.id,active:document.activeElement.id,focus:document.hasFocus(),disabled:document.querySelector("#newRunButton").disabled,error:document.querySelector("#loadErrorText").textContent,dialogs:[...document.querySelectorAll("dialog[open]")].map(x=>x.id)})'));
    } catch {}
  }
  console.error('Artifacts: ' + artifacts); throw error;
} finally {
  if (cdp) { try { await cdp.send('Browser.close'); } catch {} cdp.socket.close(); }
  browser?.kill(); server.kill();
}
