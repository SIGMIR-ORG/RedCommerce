/* Buildless saved-run explorer; all untrusted transcript text uses textContent. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const config = window.RED_COMMERCE_SITE || {};
  const source = new URL(config.trajectoryDataBase || 'trajectory-data/', location.href);
  const indexURL = config.trajectoryIndex || new URL('index.json', source).href;
  const studies = {main:'Main experiment',matched96:'Matched inputs','mechanism-repeats':'Repeated checks','authorization-comparison':'Authorization pairs'};
  const outcomes = {attack_succeeded:'Attack succeeded',no_scored_success:'No scored success',provider_filtered:'Provider filtered',unresolved:'Unresolved',deviation:'Scored deviation',no_deviation:'No scored deviation'};
  const evidence = {episode_and_requests:'Episode + requests',episode:'Episode only',metadata_only:'Outcome record only'};
  const cases = new Map((window.RED_COMMERCE_DATA?.cases || []).map(r => [r.id,r]));
  let rows=[], page=0, mode='trials', current=null, activeDetail=null, loadSerial=0;
  const pageSize=40;
  const filters=['study-filter','model-filter','outcome-filter','trace-stage','availability-filter'];
  function el(tag, cls, text) { const n=document.createElement(tag); if(cls)n.className=cls; if(text!==undefined)n.textContent=text; return n; }
  function json(value) { return JSON.stringify(value,null,2); }
  function badge(code) { return el('span','outcome-badge '+code,outcomes[code] || code); }
  function detailSection(title,value,open=false) {
    const box=el('details','trace-section');box.open=open;box.append(el('summary','',title));
    const pre=el('pre','trace-json',typeof value==='string'?value:json(value));box.append(pre);
    const button=el('button','expand-json','Expand / collapse height');button.type='button';button.onclick=()=>pre.classList.toggle('expanded');box.append(button);return box;
  }
  function option(select,value,text) {const n=el('option','',text);n.value=value;select.append(n);}
  function selectedRows() {
    const query=$('trace-search').value.trim().toLowerCase();
    return rows.filter(r=>(!query || [r.id,r.case_id,r.world_id,r.title].join(' ').toLowerCase().includes(query))
      && ($('study-filter').value==='all'||r.study===$('study-filter').value)
      && ($('model-filter').value==='all'||r.model===$('model-filter').value)
      && ($('outcome-filter').value==='all'||r.outcome===$('outcome-filter').value)
      && ($('trace-stage').value==='all'||String(r.stage)===$('trace-stage').value)
      && ($('availability-filter').value==='all'||r.availability===$('availability-filter').value));
  }
  function render() {
    const chosen=selectedRows();
    const taskGroups=new Map();chosen.forEach(r=>{if(!taskGroups.has(r.case_id))taskGroups.set(r.case_id,[]);taskGroups.get(r.case_id).push(r);});
    const items=mode==='tasks'?[...taskGroups.entries()].sort((a,b)=>a[0].localeCompare(b[0])):chosen;
    const pages=Math.max(1,Math.ceil(items.length/pageSize));page=Math.min(page,pages-1);
    $('trace-count').textContent=`${chosen.length.toLocaleString()} matching trials · ${taskGroups.size} Cases`;
    $('trials-tab').setAttribute('aria-pressed',String(mode==='trials'));$('tasks-tab').setAttribute('aria-pressed',String(mode==='tasks'));
    $('trial-list').hidden=mode!=='trials';$('trace-task-grid').hidden=mode!=='tasks';
    $('trial-rows').replaceChildren();$('trace-task-grid').replaceChildren();
    const visible=items.slice(page*pageSize,(page+1)*pageSize);
    if(mode==='trials') for(const r of visible) {
      const tr=el('tr');
      const model=el('td');model.append(el('span','table-model',r.model),el('span','subline',studies[r.study]+' · '+r.condition));
      const task=el('td');task.append(el('span','task-title',r.title),el('span','subline',r.case_id),el('span','subline',r.world_id||'World not recorded'));
      const result=el('td');result.append(badge(r.outcome),el('span','subline',r.terminal||'No resolved terminal'));
      const saved=el('td');saved.append(el('span','',evidence[r.availability]),el('span','subline',`${r.business_decisions} business decisions · ${r.requests} saved requests`));
      const action=el('td'), link=el('a','open-trial','View →');link.href='#trial='+encodeURIComponent(r.id);action.append(link);tr.append(model,task,result,saved,action);$('trial-rows').append(tr);
    } else for(const [id,group] of visible) {
      const card=el('article','trace-task-card'), first=group[0];
      card.append(el('p','eyebrow',first.stage_name),el('h3','',first.title),el('span','subline',id));
      const main=group.filter(r=>r.study==='main'), eligible=main.filter(r=>r.eligible), successes=eligible.filter(r=>r.outcome==='attack_succeeded');
      card.append(el('p','',`${group.length} matching trials${main.length ? ` · ${successes.length}/${eligible.length} successful/evaluable main episodes` : ''}`));
      const button=el('button','open-trial','Browse these trials →');button.type='button';button.onclick=()=>{$('trace-search').value=id;mode='trials';page=0;render();};card.append(button);$('trace-task-grid').append(card);
    }
    if(!visible.length){const tr=el('tr'),td=el('td','no-results-cell','No trials match these filters.');td.colSpan=5;tr.append(td);$('trial-rows').append(tr);}
    $('previous-page').disabled=page===0;$('next-page').disabled=page>=pages-1;$('page-status').textContent=`Page ${page+1} of ${pages} · ${items.length ? page*pageSize+1 : 0}–${Math.min((page+1)*pageSize,items.length)} of ${items.length.toLocaleString()}`;
  }
  function contextCard(title) {const c=el('section','context-card');c.append(el('h2','',title));return c;}
  function renderConversation(trace) {
    const panel=$('conversation-panel');panel.replaceChildren();
    if(trace.requests.length) trace.requests.forEach((r,i)=>{
      const type=r.role_kind==='counterparty'?'attacker':'business';
      const card=el('article','message-card '+type),head=el('header');
      head.append(el('span','',`REQUEST ${i+1}`),el('strong','',type==='attacker'?'Attacker agent':'Business agent'),el('span','',r.role||''));
      const body=el('div','message-body');
      if(!r.selected_episode_receipt_bound)body.append(el('p','score-notice','Interrupted-run evidence: this saved request has no matching settled episode receipt. It is shown as an associated attempt, not a confirmed executed continuation.'));
      if(r.decision?.parse_status)body.append(el('p','',`Recorded parse: ${r.decision.parse_status} · returned model: ${r.decision.model_id||'not recorded'}`));
      const request=el('details','trace-section');request.append(el('summary','','What the model received'));
      for(const message of r.request.messages||[]) {
        request.append(el('p','message-label',message.role),el('div','prompt-text',typeof message.content==='string'?message.content:json(message.content)));
      }
      request.append(detailSection('Declared action schema',r.request.response_contract));body.append(request);
      if(r.decision?.raw_response!==undefined)body.append(detailSection('Submitted actions',r.decision.raw_response,true));
      if(r.returned_answer)body.append(detailSection('Returned answer / tool content',r.returned_answer));
      if(r.provider_payload)body.append(detailSection('Provider request payload',r.provider_payload));
      card.append(head,body);panel.append(card);
    });
    else if(trace.episode) {
      panel.append(el('p','score-notice','Request-level transport records are not available in this export. The following entries come directly from the saved episode; missing inputs are not reconstructed.'));
      for(const [i,x] of (trace.episode.counterparty_exchanges||[]).entries())panel.append(detailSection(`Attacker submission ${i+1}`,x,true));
      for(const d of trace.episode.decisions||[]) {
        const card=el('article','message-card business');card.append(el('header','',`BUSINESS DECISION ${d.index} · ${d.kind||''}`));
        const b=el('div','message-body');b.append(detailSection('Observed world',d.observation),detailSection('Submitted actions',d.raw_response,true),detailSection('Executed effects',d.executed));card.append(b);panel.append(card);
      }
    } else panel.append(el('p','empty-trace','Only the frozen outcome record is available for this planned episode. No complete agent interaction is claimed; see Verifier & outcome for the recorded status.'));
  }
  function renderTrace(trace,meta) {
    const context=$('trace-context');context.replaceChildren();
    const result=contextCard('Recorded outcome');result.append(badge(meta.outcome),el('p','large-result',meta.terminal||'No resolved terminal'),el('p','',evidence[meta.availability]));context.append(result);
    const task=contextCard('Original task instruction');task.append(el('div','instruction-copy',trace.task.instruction));context.append(task);
    const scope=contextCard('Declared access and roles');scope.append(detailSection('Attacker-controlled surface',trace.task.attack_surface),detailSection('Business role',trace.task.role_description),detailSection('Arm objectives',trace.task.arms));context.append(scope);
    renderConversation(trace);
    $('state-panel').replaceChildren();$('score-panel').replaceChildren();
    if(trace.episode) {
      const e=trace.episode;
      $('state-panel').append(detailSection('Executed business actions',e.decisions?.map(d=>({index:d.index,kind:d.kind,submitted:d.raw_response,executed:d.executed})),true),detailSection('Attacker writes and allowlist proofs',e.counterparty_exchanges),detailSection('Final business state',e.final_state,true),detailSection('Saved world snapshots',e.world_snapshots),detailSection('Initial and final state files',e.saved_state_files),detailSection('Events',e.events),detailSection('Protocol failures',e.protocol_failures));
    } else $('state-panel').append(el('p','empty-trace','No complete saved episode state is available for this record.'));
    $('score-panel').append(el('p','score-notice','This is the frozen task outcome, not an LLM judge verdict. The published outcome controls eligibility; an original saved score can precede the recorded service-filter reconciliation.'),detailSection('Frozen published outcome',trace.outcome_record,true),detailSection('Original saved scorer checks',trace.saved_original_score),detailSection('Source evidence hashes',trace.provenance),detailSection('Publication disclosure',trace.disclosure));
    const integrity=contextCard('Evidence integrity');integrity.append(el('p','','Downloaded JSON verified against the release index SHA256.'),el('p','proof-hash',meta.sha256));context.append(integrity);
    $('trace-layout').hidden=false;$('detail-loading').textContent='';$('download-trial').disabled=false;
  }
  async function showTrial(id) {
    const serial=++loadSerial, meta=rows.find(r=>r.id===id);activeDetail=meta;current=null;
    $('catalog').hidden=true;$('trial-detail').hidden=false;$('trace-layout').hidden=true;$('download-trial').disabled=true;
    for(const b of $('detail-tabs').querySelectorAll('button'))b.setAttribute('aria-pressed',String(b.dataset.panel==='conversation'));
    for(const key of ['conversation','state','score'])$(key+'-panel').hidden=key!=='conversation';
    $('detail-heading').replaceChildren();
    if(!meta){$('detail-loading').textContent='This trial ID is not present in the release index.';return;}
    const h=el('div','detail-heading');h.append(el('p','eyebrow',studies[meta.study]),el('h1','',meta.title));
    const m=el('div','detail-meta');m.append(badge(meta.outcome),el('span','',meta.model),el('span','',meta.condition),el('span','',meta.stage_name));h.append(m,el('p','detail-id',meta.id));$('detail-heading').append(h);
    $('detail-loading').className='';$('detail-loading').textContent='Loading the saved trajectory…';
    try {
      const response=await fetch(new URL(meta.detail,source));if(!response.ok)throw Error(`HTTP ${response.status}`);
      const buffer=await response.arrayBuffer();
      const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',buffer))).map(n=>n.toString(16).padStart(2,'0')).join('');
      if(hash!==meta.sha256)throw Error('Evidence SHA256 mismatch; the detail file does not match this index.');
      const trace=JSON.parse(new TextDecoder().decode(buffer));if(trace.meta.id!==id)throw Error('Trial identity mismatch');
      if(serial!==loadSerial)return;current=trace;renderTrace(trace,meta);
    } catch(error) {
      if(serial!==loadSerial)return;
      $('detail-loading').className='notice-error';$('detail-loading').textContent=`The saved detail could not be loaded (${error.message}). The outcome has not been changed. If the dataset has not been published yet, configure trajectoryDataBase to its pinned Hugging Face release.`;
    }
  }
  function route() {
    const params=new URLSearchParams(location.hash.slice(1));const id=params.get('trial');
    if(id)showTrial(id);else{++loadSerial;$('catalog').hidden=false;$('trial-detail').hidden=true;}
  }
  $('back-to-trials').onclick=()=>{history.replaceState(null,'',location.pathname+location.search);route();};
  $('download-trial').onclick=()=>{if(!current)return;const a=el('a');a.href=URL.createObjectURL(new Blob([json(current)+'\n'],{type:'application/json'}));a.download=activeDetail.id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};
  $('copy-trial-link').onclick=async()=>{try{await navigator.clipboard.writeText(location.href);$('copy-trial-link').textContent='Copied';setTimeout(()=>$('copy-trial-link').textContent='Copy link',1500);}catch{$('detail-loading').textContent='Copy the address from your browser to share this trial.';}};
  $('detail-tabs').onclick=event=>{const button=event.target.closest('[data-panel]');if(!button)return;for(const b of $('detail-tabs').querySelectorAll('button'))b.setAttribute('aria-pressed',String(b===button));for(const key of ['conversation','state','score'])$(key+'-panel').hidden=key!==button.dataset.panel;};
  $('trace-controls').onsubmit=e=>e.preventDefault();
  for(const id of filters)$(id).onchange=()=>{page=0;render();};$('trace-search').oninput=()=>{page=0;render();};
  $('trials-tab').onclick=()=>{mode='trials';page=0;render();};$('tasks-tab').onclick=()=>{mode='tasks';page=0;render();};
  $('reset-filters').onclick=()=>{$('trace-search').value='';for(const id of filters)$(id).value=id==='study-filter'?'main':'all';page=0;render();};
  $('previous-page').onclick=()=>{page--;render();};$('next-page').onclick=()=>{page++;render();};
  window.addEventListener('hashchange',route);
  (async()=>{
    try {
      const response=await fetch(indexURL);if(!response.ok)throw Error(`HTTP ${response.status}`);const data=await response.json();rows=data.rows;
      if(data.schema!=='redcommerce-trajectory-index-v1'||rows.length!==data.total)throw Error('Invalid trajectory index');
      const stats=$('explorer-stats');stats.replaceChildren();for(const [n,label] of [[data.cases,'Cases'],[data.main,'main outcomes'],[data.companion,'companion runs'],[rows.filter(r=>r.availability!=='metadata_only').length,'saved episodes']]){const item=el('span');item.append(el('strong','',n.toLocaleString()),document.createTextNode(label));stats.append(item);}
      for(const model of [...new Set(rows.map(r=>r.model))])option($('model-filter'),model,model);
      for(const [i,name] of (window.RED_COMMERCE_DATA?.corpus.stages||[]).entries())option($('trace-stage'),String(i+1),name);
      $('trials-tab').textContent=`Trials (${data.total.toLocaleString()})`;$('tasks-tab').textContent=`Tasks (${data.cases})`;$('download-index').href=indexURL;
      render();route();
    } catch(error) {$('explorer-stats').textContent=`The trajectory dataset is not available here yet (${error.message}). Configure the data source after publishing the dataset.`;$('trace-count').textContent='No index loaded. No missing outcomes have been treated as failures.';}
  })();
})();
