import {deviceCache} from './cache.js';
import {replica} from './replica.js';
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const paths = {
  inbox:'M3 4h18v15H3z M3 12h5l2 3h4l2-3h5', star:'m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3l-5.6 2.9 1.1-6.2L3 9.6l6.2-.9z',
  edit:'m16 3 5 5-12 12-6 1 1-6z M14 5l5 5', sent:'m3 3 18 9-18 9 3-9z M6 12h15', clock:'M12 8v5l3 2 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0',
  archive:'M3 3h18v5H3z M5 8v13h14V8 M9 12h6', settings:'m12 3 2 3 4-1 1 4 3 3-3 3-1 4-4-1-2 3-2-3-4 1-1-4-3-3 3-3 1-4 4 1z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
  plus:'M12 5v14 M5 12h14', search:'M17 17l4 4 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0', arrow:'m9 5 7 7-7 7',
  sparkle:'m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z M20 2v4 M18 4h4',
  reply:'M9 5 3 11l6 6 M3 11h11c4 0 7 3 7 7', forward:'M15 5 6 6-6 6 M21 11H10c-4 0-7 3-7 7',
  check:'m5 12 4 4 10-10', mail:'M3 5h18v14H3z m0 0 9 7 9-7', close:'m6 6 12 12 M6 18 18 6',
  refresh:'M20 7v5h-5 M4 17v-5h5 M19 8a8 8 0 0 0-14-3 M5 16a8 8 0 0 0 14 3',
  shield:'m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z m-4 9 3 3 5-5', paperclip:'m8 13 6-6a3 3 0 0 1 4 4l-8 8a5 5 0 0 1-7-7l9-9',
  people:'M16 21v-3a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v3 M12 6a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M17 3a4 4 0 0 1 0 8 M22 21v-3a4 4 0 0 0-3-4',
  filter:'M3 5h18 M6 12h12 M9 19h6', menu:'M4 6h16 M4 12h16 M4 18h16', back:'m14 5-7 7 7 7', trash:'M3 6h18 M5 6l1 15h12l1-15 M9 6V3h6v3 M10 10v7 M14 10v7',
  logout:'M10 3H4v18h6 M13 8l5 4-5 4 M8 12h13', help:'M9 8a3 3 0 1 1 5 2c-1 1-2 1-2 4 M12 17h.01 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0'
};
paths.pin='m8 3 8 0-1 6 4 4H5l4-4z M12 13v8';
Object.assign(paths,{sync:'M20 12a8 8 0 1 1-2.35-5.65 M20 4.5v4h-4',chat:'M4 5h16v11H9l-5 4z M8 9.5h8 M8 12.5h5',ban:'M5.6 5.6l12.8 12.8 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0',bell:'M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9 M10 21h4',
  crown:'m3 7 4.5 4L12 4l4.5 7L21 7l-2 12H5z',todo:'M4 4h16v16H4z M8 12l3 3 5-6',screener:'M15 19v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M12 6a3.5 3.5 0 1 1-7 0 3.5 3.5 0 0 1 7 0 M19 8v6 M16 11h6',
  ask:'M21 12a8 8 0 0 1-12 7l-5 1 1-4a8 8 0 1 1 16-4z M10 9a2 2 0 1 1 3 2c-1 .5-1 1-1 2 M12 16h.01',download:'M12 3v12 M7 10l5 5 5-5 M4 21h16',keyboard:'M2 6h20v12H2z M6 10h.01 M10 10h.01 M14 10h.01 M18 10h.01 M7 14h10'});
const icon = (name, extra = '') => `<svg class="icon ${extra}" viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[name] || paths.mail}"/></svg>`;
const googleIcon = () => '<svg class="google-mark" viewBox="0 0 48 48" aria-hidden="true"><path fill="#4285f4" d="M43.6 24.5c0-1.4-.1-2.8-.4-4.1H24v7.8h11a9.4 9.4 0 0 1-4.1 6.2v5.2h6.6c3.9-3.6 6.1-8.9 6.1-15.1z"/><path fill="#34a853" d="M24 44c5.5 0 10.1-1.8 13.5-4.9l-6.6-5.2c-1.8 1.2-4.1 1.9-6.9 1.9-5.3 0-9.8-3.6-11.4-8.4H5.8v5.3A20.4 20.4 0 0 0 24 44z"/><path fill="#fbbc05" d="M12.6 27.4a12.3 12.3 0 0 1 0-6.8v-5.3H5.8a20.4 20.4 0 0 0 0 17.4z"/><path fill="#ea4335" d="M24 12.2c3 0 5.7 1 7.8 3.1l5.9-5.9A19.8 19.8 0 0 0 24 4 20.4 20.4 0 0 0 5.8 15.3l6.8 5.3c1.6-4.8 6.1-8.4 11.4-8.4z"/></svg>';
const logo = () => '<div class="logo"><img src="/static/icon.svg" alt="">milo<small>MAIL</small></div>';
const S = {status:null, setupAuthorized:false, state:{accounts:[], counts:{}, ai:{}, sync:[]}, messages:[], selected:null, thread:[], threadSync:{}, readerAnchor:null, loadingMessage:false, loadingList:false, listVersion:0, readerVersion:0, optimistic:new Map(), view:'inbox', category:'', account:'', search:'', settingsTab:'accounts', menu:false, syncing:false, online:true, serverErrors:0, compose:null, theme:'system', images:true};
const MAX_SERVER_ERRORS=3;
function updateOnlineState(){const wasOnline=S.online;S.online=navigator.onLine&&S.serverErrors<MAX_SERVER_ERRORS;if(wasOnline&&!S.online)renderChrome();}
const categoryNames = {people:'Persone', updates:'Notifiche', newsletters:'Newsletter'};
const viewNames = {inbox:'Smart inbox', unread:'Da leggere', todo:'Da fare', screener:'Nuovi mittenti', starred:'Preferiti', drafts:'Bozze', sent:'Posta inviata', snoozed:'Per dopo', archive:'Archivio'};
let toastTimer, searchTimer, autosaveTimer, localDraftTimer;
S.pendingDrafts=new Map();S.draftWrites=new Map();S.discardedDrafts=new Set();
S.pendingSettings=new Map();S.queueErrors=new Map();S.remoteTicket=0;
S.multi=new Set();S.todoMulti=new Set();S.todos=null;S.screening=null;S.suggestions=new Map();
const UNDO_SECONDS=10;
try{for(const id of JSON.parse(localStorage.getItem('milo-discarded-drafts')||'[]'))S.discardedDrafts.add(id);}catch{}
try{for(const draft of JSON.parse(localStorage.getItem('milo-pending-drafts')||'[]'))if(draft.id&&typeof draft.body==='string')S.pendingDrafts.set(draft.id,draft);}catch{}
const systemTheme=matchMedia('(prefers-color-scheme: dark)');
function applyTheme(theme=S.theme) {
  S.theme=['system','light','dark'].includes(theme)?theme:'system';
  document.documentElement.dataset.theme=S.theme==='system'?(systemTheme.matches?'dark':'light'):S.theme;
  try { localStorage.setItem('milo-theme',S.theme); } catch {}
}
try { applyTheme(localStorage.getItem('milo-theme')||'system'); } catch { applyTheme(); }
systemTheme.addEventListener('change',()=>applyTheme());
const accountColor=id=>{const color=S.state.accounts.find(a=>a.id===id)?.color;return /^#[0-9a-f]{6}$/i.test(color||'')?color:'#2563eb';};
const threadKey=m=>m.account_id+':'+(m.thread_id||m.id);
function skeleton(lines=4,kind='block',label='Caricamento…') {
  return `<div class="skeleton-group ${kind}" role="status" aria-label="${esc(label)}"><span class="sr-only">${esc(label)}</span>${Array.from({length:lines},(_,i)=>`<div class="skeleton-line" style="--width:${i%3===2?62: i%3===1?88:100}%"></div>`).join('')}</div>`;
}
function syncWorking(){return S.syncing||(S.state.sync||[]).some(p=>['connecting','downloading','applying'].includes(p.phase));}
function syncMarkup() {
  const active=(S.state.sync||[]).filter(p=>['connecting','downloading','applying'].includes(p.phase));
  const count=active.reduce((n,p)=>n+(p.downloaded||0),0);
  const pending=(S.state.pending||[]).reduce((n,p)=>n+p.count,0)+S.optimistic.size+S.pendingSettings.size;
  const text=S.queueErrors.size?'Modifiche da controllare · riprova con Sincronizza':active.some(p=>p.phase==='downloading')?`Scarico messaggi · ${count} salvati`:active.some(p=>p.phase==='applying')?'Sincronizzo le modifiche':active.length||S.syncing?'Collegamento alla posta…':pending?`${pending} ${pending===1?"modifica":"modifiche"} in sincronizzazione`:S.online?'Posta aggiornata':'Connessione interrotta';
  return `<span class="sync-status ${active.length||S.syncing?'working':''}" role="status"><span>${esc(text)}</span></span>`;
}

const temporarilyUnavailable=error=>!error.status||error.status>=500||[408,429].includes(error.status);
let reachabilityProbe=null;
function recordServerError(){
  S.serverErrors++;
  if(S.serverErrors<MAX_SERVER_ERRORS||!navigator.onLine||reachabilityProbe)return updateOnlineState();
  // Slow responses during a large sync are not an outage: only call it offline when the service does not answer at all.
  reachabilityProbe=fetch('/api/status',{signal:AbortSignal.timeout(5000),credentials:'same-origin',cache:'no-store'})
    .then(response=>{if(response.ok)S.serverErrors=0;})
    .catch(()=>{})
    .finally(()=>{reachabilityProbe=null;updateOnlineState();});
}
function recordServerSuccess(){S.serverErrors=0;if(!S.online&&navigator.onLine){S.online=true;renderChrome();}}
async function api(path, method='GET', body) {
  const started=replica.revision;
  let response;
  try { response = await fetch('/api' + path, {method, signal:AbortSignal.timeout(method==='GET'?12000:60000), credentials:'same-origin', headers:body ? {'Content-Type':'application/json'} : {}, body:body ? JSON.stringify(body) : undefined}); }
  catch { recordServerError(); throw new Error('Connessione a Milo interrotta. I dati salvati restano sul servizio.'); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if ((response.status === 401 || response.status===404&&['/status','/state'].includes(path)) && S.status?.authenticated) { replica.clear();await deviceCache.clear();S.optimistic.clear();S.pendingSettings.clear();S.queueErrors.clear();S.readerVersion++;S.readerAnchor=null;S.selected=null;S.thread=[];S.status.authenticated=false;renderLogin(); }
    const message = Array.isArray(data.detail) ? data.detail.map(item => item.msg).join('; ') : data.detail;
    const error=new Error(message || 'Operazione non riuscita');error.status=response.status;if(temporarilyUnavailable(error))recordServerError();throw error;
  }
  recordServerSuccess();
  const immutable=/^\/messages\/[^/?]+(?:\?.*)?$/.test(path)||/^\/messages\/[^/]+\/recipients$/.test(path);
  if(method==='GET'&&(started===replica.revision||immutable&&S.status?.authenticated)&&(/^(?:\/status|\/state|\/recap|\/messages(?:[/?]|$)|\/drafts|\/todos|\/screener)/.test(path)))deviceCache.set('api:'+path,data).then(saved=>{if(!saved&&S.status?.authenticated&&!S.cacheWarning){S.cacheWarning=true;toast('Cache locale non disponibile. I messaggi restano sul server, ma non saranno disponibili offline su questo dispositivo.');}});
  return data;
}

function toast(message,action=null) {
  clearTimeout(toastTimer);const box=$('#toast');box.textContent=message;
  if(action){const button=document.createElement('button');button.className='toast-action';button.type='button';button.textContent=action.label;button.addEventListener('click',()=>{clearTimeout(toastTimer);box.classList.remove('visible');action.run();});box.append(button);}
  box.classList.add('visible');
  toastTimer=setTimeout(() => box.classList.remove('visible'), action?.duration||5500);
}
function initials(name) { return name.split(/[\s@.]+/).filter(Boolean).slice(0,2).map(word => word[0]).join('').toUpperCase(); }
function avatar(message) {
  let value = [...(message.sender || '')].reduce((sum, char) => sum+char.charCodeAt(0),0);
  return `<div class="avatar ${['lilac','peach','green','blue','brand'][value%5]}">${esc(initials(message.sender || '?'))}</div>`;
}
function dateLabel(timestamp, long=false) {
  return new Date(timestamp*1000).toLocaleString('it-IT', long ? {day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'} : {hour:'2-digit',minute:'2-digit'});
}
function isToday(timestamp) { return new Date(timestamp*1000).toDateString() === new Date().toDateString(); }
function showModal(title, content, wide=false) {
  S.recapOpen=false;
  if($('#overlay #compose-form'))closeCompose().catch(error=>toast(error.message));
  S.menu=false;$('.shell')?.classList.remove('menu-open');
  $('#overlay').innerHTML=`<div class="modal-backdrop"><section class="modal ${wide?'wide':''}" role="dialog" aria-modal="true" aria-label="${esc(title)}"><div class="modal-header"><h2>${esc(title)}</h2><button class="icon-button" data-action="close-modal" aria-label="Chiudi">${icon('close')}</button></div>${content}</section></div>`;
  setTimeout(() => $('#overlay input, #overlay select, #overlay button')?.focus(), 0);
}
function closeModal(){ S.recapOpen=false;if($('#overlay #compose-form')){closeCompose().catch(error=>toast(error.message));return;}$('#overlay').innerHTML='';}

function renderLogin() {
  closeModal();
  if(S.status?.access==='tailscale'){$('#app').innerHTML=emptyMarkup('shield','Accesso privato non disponibile.','Verifica che questo dispositivo sia autorizzato nella tua rete Tailscale.');return;}
  const setup = !S.status.initialized;
  const form = setup && !S.setupAuthorized
    ? `<section class="login-form"><h2>Milo aspetta il primo accesso.</h2><p>Apri l’app Milo sul dispositivo su cui è stata installata per scegliere la tua password. Poi potrai accedere anche da qui.</p><button class="primary" data-action="retry-login">Riprova ${icon('arrow')}</button></section>`
    : `<form class="login-form" id="login-form"><h2>${setup?'Benvenuto a casa.':'Bentornato.'}</h2><p>${setup?'Scegli una password per Milo. Ti servirà per accedere al tuo archivio da Linux e dagli altri dispositivi.':'Accedi al tuo archivio. Account, preferenze e bozze sono già qui, come li hai lasciati.'}</p><label class="field"><span>Password di Milo</span><input type="password" name="password" minlength="12" maxlength="256" required autocomplete="${setup?'new-password':'current-password'}" placeholder="Almeno 12 caratteri"></label><div class="form-error" id="login-error" role="alert"></div><button type="submit" class="primary">${setup?'Crea il tuo Milo':'Entra in Milo'}${icon('arrow')}</button><div class="fineprint">${setup?'Conservala in un posto sicuro: ti servirà per accedere anche dagli altri dispositivi.':'Lo stesso servizio, la stessa password. Nessun account da riconfigurare.'}</div></form>`;
  $('#app').innerHTML=`<main class="login-page"><section class="login-story">${logo()}<h1>La tua posta.<br>Un po’ più leggera.</h1><p>Meno rumore, più spazio per quello che conta. Un’unica casa per le tue email, su tutti i tuoi dispositivi.</p><div class="story-features"><span>${icon('inbox')}Tutti gli account, una sola inbox</span><span>${icon('sparkle')}Un assistente che mette ordine</span><span>${icon('shield')}Il tuo archivio, sotto il tuo controllo</span></div></section><section class="login-area">${form}</section></main>`;
  $('#login-form input')?.focus();
}

function accountMarkup() {
  return `<div class="nav-label">Account</div><button class="account-button all-accounts ${S.account?'':'active'}" data-account="" aria-pressed="${!S.account}">${icon('inbox')}Tutti gli account${!S.account?icon('check'):''}</button>${S.state.accounts.map(a=>`<button class="account-button ${S.account===a.id?'active':''}" data-account="${esc(a.id)}" aria-pressed="${S.account===a.id}"><span class="dot" style="background:${accountColor(a.id)};${a.enabled?'':'opacity:.4'}"></span>${esc(a.name)}${S.account===a.id?icon('check'):''}</button>`).join('')}<button class="account-button plus-account" data-action="add-account">${icon('plus')}Aggiungi account</button>`;
}
function renderChrome() {
  if($('#sync-status')) $('#sync-status').innerHTML=syncMarkup();
  $('.sync-button')?.classList.toggle('spinning',syncWorking());
  const section=$('.account-section');
  if(section && section.innerHTML!==accountMarkup()) section.innerHTML=accountMarkup();
  document.querySelectorAll('.nav-button[data-view]').forEach(button=>{
    const count=S.state.counts[button.dataset.view]||0;
    let badge=button.querySelector('.count');
    if(!count) { badge?.remove();return; }
    if(!badge) { badge=document.createElement('span');badge.className='count';button.append(badge); }
    badge.textContent=count;
  });
}

function renderShell() {
  const counts=S.state.counts;
  const folders=[['inbox','inbox'],['unread','mail'],['todo','todo'],...(S.state.screener?.enabled?[['screener','screener']]:[]),['starred','star'],['drafts','edit'],['sent','sent'],['snoozed','clock'],['archive','archive']];
  $('#app').innerHTML=`<main class="shell ${S.selected?'has-selection':''} ${S.menu?'menu-open':''}"><aside class="sidebar">${logo()}<button class="primary compose-button" data-action="compose">${icon('plus')}Nuovo messaggio</button><div class="nav-label">La tua posta</div><nav class="nav">${folders.map(([view,name])=>`<button class="nav-button ${S.view===view?'active':''}" data-view="${view}">${icon(name)}${viewNames[view]}${counts[view]?`<span class="count">${counts[view]}</span>`:''}</button>`).join('')}</nav><div class="account-section">${accountMarkup()}</div><div class="sidebar-bottom"><div class="sidebar-footer"><div class="user-avatar">${esc(initials(S.state.identity?.name || S.state.accounts[0]?.name || 'Tu'))}</div><span>${esc(S.state.identity?.name||'Il tuo spazio')}</span><button data-action="settings" aria-label="Impostazioni">${icon('settings')}</button></div>${S.status.demo?'<div class="demo-label">DEMO · messaggi fittizi</div>':''}</div></aside><header class="topbar"><button class="icon-button mobile-menu" data-action="menu" aria-label="Apri menu">${icon('menu')}</button><div class="breadcrumbs">Il tuo spazio ${icon('arrow')}<strong>${viewNames[S.view]}</strong></div><div class="top-tools"><div id="sync-status">${syncMarkup()}</div><label class="search">${icon('search')}<input id="search-input" placeholder="Cerca nella tua posta" value="${esc(S.search)}" aria-label="Cerca nella tua posta"><kbd>/</kbd></label><button class="icon-button sync-button ${syncWorking()?'spinning':''}" data-action="sync" aria-label="Scarica posta ora" title="Scarica posta ora">${icon('sync')}</button><span class="sync-indicator ${!S.online||S.state.accounts.some(a=>a.error)?'offline':''}" title="${S.online?'Servizio connesso':'Servizio non raggiungibile'}"></span></div></header><section class="list-panel" id="list-panel"></section><section class="reading-panel" id="reading-panel"></section><div id="ask-dock"></div><button class="ask-fab" data-action="ask" aria-label="Chiedi a Milo sulla tua posta" aria-expanded="false" title="Chiedi a Milo">${icon('chat')}</button></main>`;
  renderList(); renderReading();
}

function renderList() {
  if (!$('#list-panel')) return;
  const inbox = S.view==='inbox';
  const count = S.messages.length;
  const openTodos=S.view==='todo'?(S.todos||[]):[];
  const allTodosSelected=openTodos.length>0&&openTodos.every(todo=>S.todoMulti.has(todo.id));
  const todoTools=openTodos.length?`<button class="list-recap" data-action="select-todos" aria-pressed="${allTodosSelected}">${allTodosSelected?'Deseleziona':'Seleziona tutte'}</button>`:'';
  const bulkBar=S.view==='todo'&&S.todoMulti.size?`<div class="bulk-bar" role="toolbar" aria-label="Azioni sulle cose da fare selezionate"><strong>${S.todoMulti.size} ${S.todoMulti.size===1?'selezionata':'selezionate'}</strong><button class="bulk-label" data-action="complete-todos" title="Segna come fatte">${icon('check')}Fatte</button><button data-action="clear-todos" class="bulk-clear">Annulla</button></div>`:S.multi.size?`<div class="bulk-bar" role="toolbar" aria-label="Azioni sulle conversazioni selezionate"><strong>${S.multi.size} ${S.multi.size===1?'selezionata':'selezionate'}</strong><button data-bulk="archive" title="Archivia (E)">${icon('archive')}</button><button data-bulk="read" title="Segna come lette">${icon('mail')}</button><button data-bulk="star" title="Aggiungi ai preferiti">${icon('star')}</button><button data-bulk="trash" title="Elimina">${icon('trash')}</button><button data-bulk="clear" class="bulk-clear">Annulla</button></div>`:'';
  $('#list-panel').innerHTML=`<div class="list-heading"><div class="title-row"><h1>${viewNames[S.view]}</h1>${inbox?`<button class="list-recap" data-action="recap" aria-label="Apri il recap dell’inbox" title="Recap dell’inbox">${icon('sparkle')}Recap</button>`:''}${todoTools}</div></div>${bulkBar}${inbox?`<div class="tabs">${[['','Tutte'],['people','Persone'],['updates','Notifiche'],['newsletters','Newsletter']].map(([category,name])=>`<button class="tab ${S.category===category?'active':''}" data-category="${category}">${name}</button>`).join('')}</div>`:''}${inbox&&S.category==='newsletters'?`<div class="list-tools"><button class="secondary" data-action="newsletter-senders">${icon('filter')}Gestisci i mittenti</button></div>`:''}${!S.online?'<div class="offline-note">Sei offline. Mostro la posta salvata su questo dispositivo.</div>':''}${S.state.accounts.some(a=>a.error)?`<div class="error-banner">${esc(S.state.accounts.find(a=>a.error).error)} <button data-action="settings">Apri account</button></div>`:''}<div id="message-list"></div>`;
  const container=$('#message-list');
  if (S.loadingList) { container.innerHTML=skeleton(9,'list','Carico le conversazioni…');return; }
  if (S.view==='todo') {
    const items=S.todos||[];
    container.innerHTML=items.length?items.map(t=>`<div class="todo-row ${t.kind==='followup'?'followup':''} ${S.todoMulti.has(t.id)?'multi':''}"><button class="todo-check" data-todo-done="${esc(t.id)}" aria-label="Segna come fatto" title="Fatto">${icon('check')}</button><button class="todo-body" data-message="${esc(t.message_id)}"><span class="todo-text">${esc(t.text)}</span><span class="todo-meta">${t.kind==='followup'?'<span class="todo-tag">Da seguire</span>':t.priority==='high'?'<span class="todo-tag">Priorità alta</span>':''}${esc(t.sender||t.sender_email||'')} · ${esc(subjectCore(t.subject))} · ${dateLabel(t.date,true)}</span></button></div>`).join(''):emptyMarkup('todo','Niente in sospeso.','Le cose da fare che Milo trova nelle email, e quelle a cui aspetti una risposta, arrivano qui.');
    return;
  }
  if (S.view==='screener') {
    const items=S.screening||[];
    container.innerHTML=items.length?`<p class="screener-intro">Ti scrivono per la prima volta. Approva per vederli nella Smart inbox, blocca per archiviarli sempre.</p>`+items.map(s=>`<div class="screener-row"><button class="screener-open" data-message="${esc(s.sample_id)}">${avatar({sender:s.name||s.email})}<span><strong>${esc(s.name||s.email)}</strong><small>${esc(s.email)} · ${s.count} email</small></span></button><div class="screener-actions"><button class="secondary" data-sender-status="approved" data-sender="${esc(s.email)}">Approva</button><button class="secondary danger" data-sender-status="blocked" data-sender="${esc(s.email)}">Blocca</button></div></div>`).join(''):emptyMarkup('screener','Nessun nuovo mittente.','Chi ti scrive per la prima volta aspetta qui la tua approvazione.');
    return;
  }
  if (S.view==='drafts') {
    container.innerHTML=(S.drafts?.length?S.drafts.map(d=>`<button class="draft-row" data-draft="${esc(d.id)}"><small>${d.scheduled?.error?'<span class="draft-flag error">Invio non riuscito</span> ':d.scheduled?`<span class="draft-flag">Invio ${esc(dateLabel(d.scheduled.send_at,true))}</span> `:''}${d.pending?'Salvataggio in attesa · ':''}${esc(d.to||'Nessun destinatario')}</small><strong>${esc(d.subject||'Senza oggetto')}</strong><p>${esc(d.body.slice(0,100))}</p></button>`).join(''):emptyMarkup('edit','Un pensiero da scrivere.','Le bozze salvate appariranno qui, anche sugli altri dispositivi.'));
    return;
  }
  if (!count) {
    container.innerHTML=emptyMarkup('inbox',S.state.accounts.length?'Nessuna conversazione.':'Cominciamo dalla tua posta.',S.state.accounts.length?'Qui non ci sono messaggi. Le email arriveranno con la sincronizzazione.':'Collega il tuo primo account. Al resto pensiamo insieme.',!S.state.accounts.length);
    return;
  }
  let lastDay='';
  container.innerHTML=S.messages.map(m=>{
    const day=m.pinned?'In evidenza':isToday(m.date)?'Oggi':new Date(m.date*1000).toLocaleDateString('it-IT',{day:'numeric',month:'long'});
    const heading=day!==lastDay?`<div class="day-heading">${esc(day)}${S.search?'<span class="right">Risultati di ricerca</span>':''}</div>`:'';
    lastDay=day;
    return heading+`<button class="message-row ${m.read?'':'unread'} ${S.selected?.id===m.id?'selected':''} ${S.multi.has(threadKey(m))?'multi':''}" aria-pressed="${S.multi.has(threadKey(m))}" data-message="${esc(m.id)}" style="--account-color:${accountColor(m.account_id)}">${avatar(m)}<span class="message-content"><span class="sender-line"><strong>${esc(m.sender)}</strong>${m.message_count>1?`<span class="thread-count">${m.message_count}</span>`:''}${!m.read?'<span class="unread-dot"></span>':''}<span class="row-markers">${m.pinned?`<span class="row-pin" aria-label="Conversazione fissata" title="Fissata in alto">${icon('pin')}</span>`:''}${m.analyzed_count?`<span class="row-analysis" aria-label="${m.analyzed_count} messaggi analizzati" title="${m.analyzed_count} messaggi analizzati da Milo AI">${icon('sparkle')}</span>`:''}</span><time>${dateLabel(m.date)}</time></span><span class="row-subject">${esc(subjectCore(m.subject))}</span><span class="row-preview">${m.sent?'Tu: ':''}${esc(m.preview)}</span>${m.replied?`<span class="reply-badge">${icon('reply')}Hai risposto</span>`:''}</span>${m.starred?`<span class="row-star">${icon('star')}</span>`:''}</button>`;
  }).join('');
}
function emptyMarkup(symbol,title,description,add=false) {
  return `<div class="empty">${icon(symbol)}<h3>${esc(title)}</h3><p>${esc(description)}</p>${add?'<button class="primary" data-action="add-account">Collega un account</button>':''}</div>`;
}

function subjectCore(subject) {
  return String(subject||'').replace(/^\s*(?:(?:re|aw|sv|r|fw|fwd)(?:\[\d+\])?\s*:\s*)+/i,'').trim()||'Senza oggetto';
}
const LINK_PATTERN=/\bhttps?:\/\/[^\s<>"'()\[\]]+/gi;
function realLink(url){
  // Text copied out of Gmail carries google.com/url?q=… wrappers: open and show the real destination.
  try{const parsed=new URL(url);if(/(^|\.)google\.[a-z.]+$/i.test(parsed.hostname)&&parsed.pathname==='/url'){const target=parsed.searchParams.get('q')||parsed.searchParams.get('url');if(target&&/^https?:\/\//i.test(target))return target;}}catch{}
  return url;
}
function linkLabel(url){
  try{const parsed=new URL(url);for(const key of [...parsed.searchParams.keys()])if(/^utm_/i.test(key))parsed.searchParams.delete(key);return (parsed.host+parsed.pathname+parsed.search).replace(/\/$/,'');}catch{return url;}
}
function splitLinks(text){
  const parts=[];let last=0;
  for(const match of text.matchAll(LINK_PATTERN)){
    let url=match[0];const trailing=/[.,;:!?]+$/.exec(url)?.[0]||'';url=url.slice(0,url.length-trailing.length);
    parts.push(text.slice(last,match.index),{url});last=match.index+url.length;
  }
  parts.push(text.slice(last));return parts;
}
function linkifyText(text){return splitLinks(text).map(part=>typeof part==='string'?esc(part):`<a href="${esc(realLink(part.url))}" target="_blank" rel="noopener noreferrer">${esc(linkLabel(realLink(part.url)))}</a>`).join('');}
function linkifyDocument(doc){
  for(const anchor of doc.body.querySelectorAll('a[href]')){
    const href=anchor.getAttribute('href'),target=realLink(href);
    if(target!==href){anchor.setAttribute('href',target);if(anchor.textContent.trim()===href)anchor.textContent=linkLabel(target);}
  }
  const walker=doc.createTreeWalker(doc.body,NodeFilter.SHOW_TEXT),nodes=[];
  while(walker.nextNode()){const node=walker.currentNode;if(!node.parentElement?.closest('a,style,script')&&LINK_PATTERN.test(node.nodeValue))nodes.push(node);LINK_PATTERN.lastIndex=0;}
  for(const node of nodes){
    const fragment=doc.createDocumentFragment();
    for(const part of splitLinks(node.nodeValue)){
      if(typeof part==='string'){if(part)fragment.append(part);continue;}
      const anchor=doc.createElement('a'),target=realLink(part.url);
      anchor.href=target;anchor.target='_blank';anchor.rel='noopener noreferrer';anchor.textContent=linkLabel(target);fragment.append(anchor);
    }
    node.replaceWith(fragment);
  }
}
function quotedHTML(html) {
  const doc=new DOMParser().parseFromString(html,'text/html');
  linkifyDocument(doc);
  const selectors='.gmail_quote,.gmail_quote_container,.yahoo_quoted,.protonmail_quote,blockquote[type="cite"],blockquote';
  const roots=[...doc.body.querySelectorAll(selectors)].filter(node=>!node.parentElement?.closest(selectors));
  for(const node of roots){
    const details=doc.createElement('details'),summary=doc.createElement('summary');
    details.className='milo-quoted-history';summary.textContent='Mostra il testo citato';
    node.replaceWith(details);details.append(summary,node);
  }
  const outlook=doc.body.querySelector('#divRplyFwdMsg,#appendonsend');
  if(outlook&&!outlook.closest('.milo-quoted-history')){
    const details=doc.createElement('details'),summary=doc.createElement('summary');
    details.className='milo-quoted-history';summary.textContent='Mostra il testo citato';
    outlook.before(details);details.append(summary);
    while(details.nextSibling)details.append(details.nextSibling);
  }
  return doc.body.innerHTML;
}
function quotedText(body) {
  const text=String(body||'');
  const match=/^(?:On [^\n]{0,300}wrote:|Il giorno [^\n]{0,300}ha scritto:|Le [^\n]{0,300}[ée]crit\s*:|Am [^\n]{0,300}schrieb[^\n]*:|>\s)/mi.exec(text);
  if(!match||match.index===0)return `<div class="mail-body">${linkifyText(text)}</div>`;
  return `<div class="mail-body">${linkifyText(text.slice(0,match.index).trimEnd())}</div><details class="quoted-history"><summary>Mostra il testo citato</summary><div class="mail-body">${linkifyText(text.slice(match.index))}</div></details>`;
}
function htmlDocument(html) {
  const images=S.images?"'self' https:":"'self'";
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="referrer" content="no-referrer"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src ${images}; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><style>html{color-scheme:light}body{margin:0;min-height:100%;font:15px/1.6 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#172033;overflow-wrap:anywhere;-webkit-font-smoothing:antialiased}.milo-email-document{display:flow-root;padding:16px;box-sizing:border-box;contain:layout style}img,table{max-width:100%!important}img{height:auto}pre{white-space:pre-wrap}a{color:#2563eb}table{border-collapse:collapse}.milo-quoted-history{margin:16px 0;border-top:1px solid #dfe7f2;padding-top:10px}.milo-quoted-history>summary{cursor:pointer;color:#64748b;font:13px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}.milo-quoted-history blockquote{margin-left:12px!important;padding-left:12px!important;border-left:2px solid #dfe7f2}.milo-quoted-history:not([open])>*:not(summary){display:none!important}</style></head><body><div class="milo-email-document">${quotedHTML(html)}</div></body></html>`;
}
const frameHeights=new Map();
function frameKey(item){return [item.id,item.content_version||'',S.images?1:0].join('|');}
function fitFrames(root=document) {
  root.querySelectorAll('.email-html').forEach(frame=>{
    if(frame._fitted)return;frame._fitted=true;
    const start=()=>{
      if(!frame.isConnected)return;
      const doc=frame.contentDocument,content=doc?.URL==='about:srcdoc'&&doc.querySelector('.milo-email-document');
      if(!content){requestAnimationFrame(start);return;}
      const fit=()=>{
        if(!frame.isConnected||!frame.getClientRects().length)return;
        const height=Math.max(100,Math.ceil(content.scrollHeight));
        if(Math.abs(frame.offsetHeight-height)>1)frame.style.height=height+'px';
        frameHeights.set(frame.dataset.frameKey,height);
      };
      fit();
      new ResizeObserver(fit).observe(content);
      doc.addEventListener('keydown',handleKeydown);
    };
    start();
  });
}
function morph(from,to){
  if(from.nodeType!==to.nodeType||from.nodeName!==to.nodeName||(from.nodeType===1&&from.dataset.threadMessage!==to.dataset.threadMessage)){from.replaceWith(to.cloneNode(true));return;}
  if(from.nodeType!==1){if(from.nodeValue!==to.nodeValue)from.nodeValue=to.nodeValue;return;}
  if(from.tagName==='IFRAME'){if(from.getAttribute('srcdoc')!==to.getAttribute('srcdoc'))from.replaceWith(to.cloneNode(true));return;}
  for(const {name} of [...from.attributes])if(!to.hasAttribute(name))from.removeAttribute(name);
  for(const {name,value} of to.attributes)if(from.getAttribute(name)!==value)from.setAttribute(name,value);
  morphNodes(from,to);
  if(from.tagName==='SELECT')from.value=to.value;
}
function morphNodes(target,source){
  const current=[...target.childNodes],next=[...source.childNodes];
  next.forEach((node,index)=>{if(current[index])morph(current[index],node);else target.appendChild(node.cloneNode(true));});
  current.slice(next.length).forEach(node=>node.remove());
}
function morphChildren(target,markup){
  const template=document.createElement('template');template.innerHTML=markup;morphNodes(target,template.content);
}
function proposedActions(message){
  return [...new Set((message?.analysis?.action_items||[]).filter(item=>typeof item==='string'&&item.trim()&&!/^(nessuna azione|nessun'azione|no action|non è richiesta alcuna azione|non serve alcuna azione)/i.test(item.trim())).map(item=>item.trim().slice(0,500)))];
}
function actionProposals(message){
  const items=proposedActions(message);if(!items.length)return '';
  return `<div class="action-proposals"><h3>Da fare proposti</h3><ul>${items.map(item=>{
    const todo=message.todos?.find(todo=>todo.text===item),accepted=todo?.accepted!=null,done=todo?.done!=null;
    return `<li><span>${esc(item)}</span>${accepted||done?`<span class="proposal-status">${icon('check')}${done?'Fatto':'Nei da fare'}</span>`:`<button class="accept-todo" data-accept-todo="${esc(message.id)}" data-todo-text="${esc(item)}">${icon('plus')}Accetta da fare</button>`}</li>`;
  }).join('')}</ul></div>`;
}
function confirmationChip(m){
  const found=S.confirmation;
  if(!found||found.key!==threadKey(m))return '';
  return `<div class="confirmation-code">${icon('shield')}Codice di conferma <strong>${esc(found.code)}</strong><button data-copy-code="${esc(found.code)}">Copia</button></div>`;
}
function renderReading() {
  const panel=$('#reading-panel');if(!panel)return;
  const editor=$('#inline-composer #compose-form'),active=document.activeElement;
  const caret=active?.tagName==='TEXTAREA'?[active.selectionStart,active.selectionEnd]:null;
  if(editor)captureCompose();
  if(editor)editor.remove();
  const m=S.selected;
  if (!m) { panel.innerHTML=emptyMarkup('mail','Spazio per una conversazione.','Scegli un’email e prenditi il tempo per leggerla.');return; }
  const open=new Set([...panel.querySelectorAll('details[open]')].map(el=>el.dataset.threadMessage));
  const messages=S.thread.length?S.thread:[m];
  const analyzed=S.thread.findLast(message=>message.analysis)||m,analysis=analyzed.analysis;
  const downloading=S.loadingMessage||S.threadSync.phase==='downloading';
  const peer=S.thread.findLast(message=>!message.sent)||m,peerEmail=(peer.sender_email||'').toLowerCase(),vip=(S.state.vips||[]).includes(peerEmail);
  const suggestions=S.suggestions.get(peer.id);
  morphChildren(panel,`<div class="reading-toolbar"><button class="icon-button back-button" data-action="back" aria-label="Torna alla lista">${icon('back')}</button><button class="icon-button ${m.pinned?'is-active':''}" data-action="pin" aria-label="${m.pinned?'Rimuovi pin':'Fissa in alto'}" title="${m.pinned?'Rimuovi pin':'Fissa in alto'}">${icon('pin')}</button><button class="icon-button" data-action="archive" aria-label="${m.archived?'Sposta in inbox':'Archivia'}" title="Archivia">${icon('archive')}</button><button class="icon-button" data-action="trash" aria-label="Elimina conversazione" title="Sposta nel cestino (Backspace / Canc)" aria-keyshortcuts="Backspace Delete">${icon('trash')}</button><button class="icon-button" data-action="snooze" aria-label="Posticipa" title="Posticipa">${icon('clock')}</button><button class="icon-button" data-action="read" aria-label="${m.read?'Segna da leggere':'Segna come letta'}">${icon('mail')}</button><button class="icon-button ${m.starred?'is-active':''}" data-action="star" aria-label="${m.starred?'Rimuovi dai preferiti':'Aggiungi ai preferiti'}" title="${m.starred?'Rimuovi dai preferiti':'Aggiungi ai preferiti'} (P)" aria-keyshortcuts="P">${icon('star')}</button>${peerEmail&&!peer.sent?`<span class="separator"></span><button class="icon-button ${vip?'is-active':''}" data-action="vip" data-sender="${esc(peerEmail)}" aria-label="${vip?'Rimuovi il mittente dai VIP':'Segna il mittente come VIP'}" title="${vip?'Rimuovi dai VIP':'Mittente VIP: notifiche sempre'}">${icon('crown')}</button><button class="icon-button" data-action="block-sender" data-sender="${esc(peerEmail)}" aria-label="Blocca il mittente" title="Blocca il mittente">${icon('ban')}</button>`:''}<div class="right"><span class="dot" style="background:${accountColor(m.account_id)}"></span>${esc(S.state.accounts.find(a=>a.id===m.account_id)?.name||'Account')}</div></div>${confirmationChip(m)}<article class="mail-content"><select class="category-select" id="message-category" aria-label="Categoria della email">${Object.entries(categoryNames).map(([key,name])=>`<option value="${key}" ${key===m.category?'selected':''}>${name}</option>`).join('')}</select>${peer.unsubscribe?`<button class="unsubscribe-button" data-action="unsubscribe" data-message-id="${esc(peer.id)}">${icon('ban')}Disiscriviti</button>`:''}<h2>${esc(subjectCore(m.subject))}</h2>${downloading?`<div class="download-status" role="status">${icon('refresh','spinner')}Scarico la conversazione e le tue risposte…</div>`:''}${S.threadSync.error?`<div class="error-banner">${esc(S.threadSync.error)}</div>`:''}${S.loadingMessage?skeleton(7,'reader','Carico il messaggio…'):`<section class="ai-summary"><div class="ai-summary-title">${icon('sparkle')}${analysis?'Il punto, secondo Milo':'Milo AI'}<button data-action="analyze">${analysis?'Rianalizza':'Analizza'}${icon('arrow')}</button></div><div id="analysis-content">${S.analyzing?skeleton(3,'block','Analisi in corso…'):`<p>${analysis?esc(analysis.summary):'Sintesi, cose da fare e priorità della conversazione.'}</p>${actionProposals(analyzed)}`}</div></section><div class="thread-messages">${messages.map((item,index)=>`<details class="thread-message ${item.sent?'sent-message':''}" data-thread-message="${esc(item.id)}" ${index===messages.length-1||open.has(item.id)?'open':''}><summary><span class="sender-detail">${avatar(item)}<span><strong>${item.sent?'Tu':esc(item.sender)}</strong><span class="address">${esc(item.sender_email)}</span><small>${item.sent?'Risposta inviata':esc(item.preview.slice(0,90))}</small></span><time>${dateLabel(item.date,true)}</time></span></summary><div class="thread-message-body" data-body-for="${esc(item.id)}">${index===messages.length-1||open.has(item.id)?bodyMarkup(item):''}</div></details>`).join('')}</div><div class="reply-actions"><button data-action="reply">${icon('reply')}Rispondi</button><button data-action="reply-all">${icon('reply')}Rispondi a tutti</button><button data-action="forward">${icon('forward')}Inoltra</button><button data-action="ai-reply">${icon('sparkle')}Aiutami a rispondere</button></div>${peer.sent?'':`<div class="quick-replies">${S.suggesting===peer.id?skeleton(1,'block','Milo prepara le risposte…'):suggestions?suggestions.map((reply,index)=>`<button class="quick-reply" data-quick-reply="${index}">${esc(reply)}</button>`).join(''):`<button class="quick-reply ghost" data-action="suggest">${icon('sparkle')}Suggerisci risposte rapide</button>`}</div>`}<div id="inline-composer"></div>`}</article>`);
  fitFrames(panel);
  for(const item of messages)if((item.id===messages.at(-1)?.id||open.has(item.id))&&!item.body_loaded)ensureBody(item.id).catch(()=>{});
  if(S.compose?.inline&&S.selected&&S.compose.thread_key===threadKey(S.selected)){renderInlineComposer(editor);if(editor&&editor.contains(active)){active.focus({preventScroll:true});if(caret)active.setSelectionRange(...caret);}}
}

const viewRequests=new Map();
function currentQuery(){return {view:S.view,account:S.account,category:S.category,search:S.search};}
function listPath(query=currentQuery()){
  const params=new URLSearchParams({view:query.view,search:query.search});
  if(query.category&&query.view==='inbox')params.set('category',query.category);
  if(query.account)params.set('account',query.account);
  return query.view==='drafts'?'/drafts':query.view==='todo'?'/todos':query.view==='screener'?'/screener':'/messages?'+params;
}
function applyState(state){
  const counts=S.optimistic.size?S.state.counts:state.counts;S.state={...state,counts};
  if(pendingMailto||pendingOpen)setTimeout(openPendingMailto);
  for(const operation of S.pendingSettings.values()){
    if(operation.account_id)S.state.accounts=S.state.accounts.map(a=>a.id===operation.account_id?{...a,...operation.body}:a);
    else S.state[operation.setting]=operation.body;
  }
  if(!$('#appearance-form'))applyTheme(S.state.appearance?.theme||S.theme);renderChrome();
}
function paintLocal(){
  if(!S.status?.authenticated||!$('#list-panel'))return;
  if(S.view==='drafts'){
    const drafts=new Map((S.cachedDrafts||[]).map(d=>[d.id,d]));
    for(const draft of S.pendingDrafts.values())drafts.set(draft.id,{...draft,pending:true});
    S.drafts=[...drafts.values()].filter(d=>!S.discardedDrafts.has(d.id));S.messages=[];
  }else if(S.view==='todo'||S.view==='screener')S.messages=[];
  else S.messages=replica.select(currentQuery(),listPath(),S.optimistic,new Set(S.state.screener?.enabled?S.state.screener.pending:[]));
  S.loadingList=S.view==='todo'?!S.todos:S.view==='screener'?!S.screening:S.view!=='drafts'&&!replica.available;
  const listData=S.view==='drafts'?S.drafts:S.view==='todo'?S.todos||[]:S.view==='screener'?S.screening||[]:S.messages;
  const newListSignature=JSON.stringify([S.view,S.account,S.category,S.search,listData.map(m=>[m.id,m.read,m.starred,m.pinned,m.preview,m.subject,m.analyzed_count,m.pending,m.to,m.body?.slice(0,50),m.scheduled?.send_at,m.scheduled?.error,m.text,m.count])]);
  if(newListSignature!==S._lastListSignature){
    S._lastListSignature=newListSignature;
    renderList();
    preloadListBodies();
  }
  const newChromeSignature=JSON.stringify([S.state.counts,S.state.sync,S.online,S.syncing]);
  if(newChromeSignature!==S._lastChromeSignature){
    S._lastChromeSignature=newChromeSignature;
    renderChrome();
  }
  notifyNew();
  if(S.selected){const latest=replica.find(threadKey(S.selected));const fields=['subject','sender','sender_email','preview','date','read','starred','archived','pinned','category','message_count','analyzed_count'];if(latest&&!latest.deleted&&fields.some(field=>latest[field]!==S.selected[field])){S.selected={...S.selected,...Object.fromEntries(fields.map(field=>[field,latest[field]]))};renderReading();}}
}

async function userFirst(){while(S.loadingMessage)await new Promise(resolve=>setTimeout(resolve,150));}
let preloadVersion=0;
function preloadListBodies(){
  const version=++preloadVersion;
  const list=S.view==='drafts'?[]:S.messages;
  if(!list.length||S.view==='drafts')return;
  const toPreload=list.slice(0,15).map(m=>m.id);
  setTimeout(async()=>{
    const concurrency=2;
    const queue=[...toPreload];
    const workers=Array.from({length:Math.min(concurrency,queue.length)},async()=>{
      while(queue.length&&version===preloadVersion&&navigator.onLine&&!document.hidden){
        const id=queue.shift();
        if(!id)break;
        await userFirst();
        try{
          const cached=await deviceCache.get('api:'+bodyPath(id));
          if(cached)continue;
          await api(bodyPath(id));
        }catch{}
      }
    });
    await Promise.all(workers);
  },500);
}
replica.onChange(()=>{if(S.search)paintLocal();});
function revalidateView(query=currentQuery()){
  const path=listPath(query);if(viewRequests.has(path))return viewRequests.get(path);
  const started=replica.revision,ticket=++S.remoteTicket;
  const promise=(async()=>{
    try{
      const [state,list]=await Promise.all([api('/state'),api(path)]);
      if(!S.status?.authenticated)return;
      if(started===replica.revision&&ticket>=(S.stateTicket||0)){S.stateTicket=ticket;applyState(state);}
      if(query.view==='drafts'){if(started===replica.revision)S.cachedDrafts=list.drafts;}
      else if(query.view==='todo')S.todos=list.todos;
      else if(query.view==='screener')S.screening=list.senders;
      else{const shown=replica.select(query,path,S.optimistic);replica.merge(list.messages,query.view,started,ticket);replica.rememberQuery(path,list.messages);if(!query.search)reconcileView(shown,list.messages);}
      paintLocal();
    }catch(error){
      if(!temporarilyUnavailable(error)&&S.status?.authenticated)toast(error.message);
      if(S.status?.authenticated){S.loadingList=false;paintLocal();}
    }finally{
      viewRequests.delete(path);
      if(started!==replica.revision&&S.status?.authenticated)revalidateView();
    }
  })();viewRequests.set(path,promise);return promise;
}
// Rows this view showed but the service no longer lists were changed on another device
// (trashed, archived, moved): verify them now instead of waiting for the full catalogue pass.
const reconciling=new Set();
async function reconcileView(shown,returned){
  const keys=new Set(returned.map(threadKey)),oldest=returned.length>=100?Math.min(...returned.map(row=>row.date)):0;
  const stale=shown.filter(row=>!keys.has(threadKey(row))&&row.date>=oldest&&!S.optimistic.has(threadKey(row))&&!reconciling.has(threadKey(row))).slice(0,20);
  for(const row of stale){
    const id=threadKey(row);reconciling.add(id);
    try{const started=replica.revision,ticket=++S.remoteTicket,data=await api('/client/thread?'+new URLSearchParams({account:row.account_id,thread:row.thread_id||row.id}));if(S.status?.authenticated)replica.merge([data.message],'all',started,ticket);}
    catch(error){if(error.status===404){replica.remove(id);if(S.selected&&threadKey(S.selected)===id){S.readerVersion++;S.readerAnchor=null;S.selected=null;S.thread=[];$('.shell')?.classList.remove('has-selection');renderReading();}}else break;}
    finally{reconciling.delete(id);}
  }
  if(stale.length){paintLocal();replica.commit();}
}
async function refresh(resetSelection=false,showLoading=false){
  if(!S.status?.authenticated)return;
  await replica.init();
  if(resetSelection){S.selected=null;S.thread=[];S.readerAnchor=null;S.readerVersion++;renderReading();}
  const cached=await deviceCache.get('api:/drafts');if(cached)S.cachedDrafts=cached.drafts;
  paintLocal();revalidateView();
}
let lastMailRequest=0;
async function downloadMail({automatic=false}={}){
  if(S.syncing||!S.status?.authenticated||!navigator.onLine)return;
  if(automatic&&Date.now()-lastMailRequest<1500)return;
  lastMailRequest=Date.now();S.syncing=true;renderChrome();
  try{
    await api('/sync','POST');
    flushClientQueue().catch(()=>{});
    if(!automatic)toast('Controllo della posta avviato.');
  }finally{S.syncing=false;await refresh();renderChrome();}
}
let feeding=false,lastFeed=0,feedTimer;
function queueCatalogue(){
  if(feedTimer||feeding||Date.now()-lastFeed<120000)return;
  feedTimer=setTimeout(()=>{feedTimer=null;refreshCatalogue();},1500);
}
async function refreshCatalogue(){
  if(feeding||!navigator.onLine||!S.status?.authenticated||Date.now()-lastFeed<120000)return;
  feeding=true;lastFeed=Date.now();
  try{
    let cursor;const previous=replica.keys(),seen=new Set();
    do{
      const started=replica.revision,ticket=++S.remoteTicket;
      const data=await api('/client/messages'+(cursor?'?'+new URLSearchParams(cursor):''));
      if(!S.status?.authenticated)return;
      replica.merge(data.messages,'all',started,ticket);for(const row of data.messages)seen.add(threadKey(row));paintLocal();cursor=data.next;if(cursor)await new Promise(resolve=>setTimeout(resolve,20));
    }while(cursor&&navigator.onLine);
    for(const id of previous.filter(id=>!seen.has(id))){
      const row=replica.find(id),started=replica.revision,ticket=++S.remoteTicket;try{const data=await api('/client/thread?'+new URLSearchParams({account:row.account_id,thread:row.thread_id||row.id}));if(S.status?.authenticated)replica.merge([data.message],'all',started,ticket);}
      catch(error){if(error.status===404){replica.remove(id);if(S.selected&&threadKey(S.selected)===id){S.readerVersion++;S.readerAnchor=null;S.selected=null;S.thread=[];renderReading();}}}
    }
    paintLocal();await replica.commit();
  }catch{}finally{feeding=false;warmRecentBodies();}
}
let warmingRecent=false,lastWarm=0;
async function warmRecentBodies(){
  if(warmingRecent||!navigator.onLine||document.hidden||!S.status?.authenticated)return;
  warmingRecent=true;
  try{
    const rows=replica.keys().map(id=>replica.find(id)).filter(row=>row&&!row.deleted)
      .sort((a,b)=>(b.date||0)-(a.date||0)).slice(0,60);
    const queue=rows.map(row=>row.id);
    const workers=Array.from({length:Math.min(2,queue.length)},async()=>{
      while(queue.length&&navigator.onLine&&!document.hidden&&S.status?.authenticated){
        const id=queue.shift();
        if(!id)break;
        await userFirst();
        const threadPath='/messages/'+encodeURIComponent(id)+'/thread?lazy=true';
        if(!(await deviceCache.has('api:'+threadPath))){
          try{await api(threadPath);}catch{break;}
        }
        const path=bodyPath(id);
        if(await deviceCache.has('api:'+path))continue;
        try{
          let pending=bodyRequests.get(path);
          if(!pending){pending=api(path);bodyRequests.set(path,pending);pending.finally(()=>{if(bodyRequests.get(path)===pending)bodyRequests.delete(path);}).catch(()=>{});}
          replica.body(await pending);
        }catch{break;}
        await new Promise(resolve=>setTimeout(resolve,150));
      }
    });
    await Promise.all(workers);
  }finally{warmingRecent=false;lastWarm=Date.now();}
}
const bodyRequests=new Map();
S.codesOffered=new Set();
function confirmationCode(text){
  if(!text||!/(codice|code|otp|verific|conferma|one[-\s]?time|authentication|security|temporaneo|monouso)/i.test(text))return null;
  const anchored=/(?:codice|code|otp|verifica(?:zione)?|conferma|verification|authentication|security|one[-\s]?time(?:\s(?:password|code))?|temporaneo|monouso)[^0-9]{0,48}(\d[\d\s-]{3,10}\d)/i.exec(text);
  const cleaned=anchored?.[1].replace(/[\s-]/g,'');
  if(cleaned&&cleaned.length>=4&&cleaned.length<=8)return cleaned;
  return /\b(\d{6})\b/.exec(text)?.[1]||null;
}
function offerConfirmation(message){
  if(!message||message.sent||!S.selected||threadKey(message)!==threadKey(S.selected)||S.codesOffered.has(message.id))return;
  const code=confirmationCode([message.subject,message.body].filter(Boolean).join('\n'));
  if(!code)return;
  S.codesOffered.add(message.id);
  S.confirmation={key:threadKey(message),id:message.id,code};
  navigator.clipboard?.writeText(code).then(()=>toast(`Codice di conferma ${code} copiato negli appunti.`)).catch(()=>{});
  renderReading();
}
function bodyPath(id){return '/messages/'+encodeURIComponent(id)+(S.images?'?load_images=true':'');}
function bodyMarkup(item){
  if(!item.body_loaded)return item.body_error?`<div class="offline-note">${esc(item.body_error)}</div><button class="secondary" data-download-body="${esc(item.id)}">Riprova</button>`:skeleton(3,'message-body','Scarico il messaggio…');
  return `${item.remote_images&&!S.images?'<button class="image-permission" data-action="load-images">Carica immagini esterne</button>':''}${item.html?`<iframe class="email-html" data-frame-key="${esc(frameKey(item))}"${frameHeights.has(frameKey(item))?` style="height:${frameHeights.get(frameKey(item))}px"`:''} title="Contenuto di ${esc(item.subject)}" sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox" referrerpolicy="no-referrer" srcdoc="${esc(htmlDocument(item.html))}"></iframe>`:quotedText(item.body)}${item.attachments?.length?`<div class="attachments">${item.attachments.map(a=>/^image\/(png|jpeg|gif|webp)$|^application\/pdf$/.test(a.type||'')?`<button class="attachment" data-preview-message="${esc(item.id)}" data-preview-index="${a.index}" data-preview-type="${esc(a.type)}" data-preview-name="${esc(a.name)}">${icon('paperclip')}${esc(a.name)}</button>`:`<a class="attachment" href="/api/messages/${encodeURIComponent(item.id)}/attachments/${a.index}">${icon('paperclip')}${esc(a.name)}</a>`).join('')}</div>`:''}`;
}
function displayBody(item){
  const slot=[...document.querySelectorAll('[data-body-for]')].find(el=>el.dataset.bodyFor===item.id);
  if(!slot||!slot.closest('details')?.open)return;
  morphChildren(slot,bodyMarkup(item));fitFrames(slot);
}
async function ensureBody(id,background=false){
  const version=S.readerVersion,path=bodyPath(id),metadata=S.thread.find(m=>m.id===id);
  if(!metadata)return null;
  if(metadata.body_loaded)return metadata;
  if(background&&await deviceCache.has('api:'+path))return metadata;
  let message=await deviceCache.get('api:'+path);
  if(message&&metadata.content_version&&message.content_version!==metadata.content_version)message=null;
  if(!message){
    let pending=bodyRequests.get(path);
    if(!pending){pending=api(path);bodyRequests.set(path,pending);pending.finally(()=>{if(bodyRequests.get(path)===pending)bodyRequests.delete(path);}).catch(()=>{});}
    try{message=await pending;}catch(error){
      if(version===S.readerVersion){metadata.body_error=S.online?error.message:'Questo messaggio non è ancora nella cache del dispositivo. Ricollegati per scaricarlo.';displayBody(metadata);}
      throw error;
    }
  }
  replica.body(message);if(background){offerConfirmation(message);return message;}
  if(version!==S.readerVersion)return message;
  const latest=S.thread.find(m=>m.id===id)||metadata,item={...message,...latest,body_loaded:true,body_error:null};
  S.thread=S.thread.map(m=>m.id===id?item:m);if(S.selected?.id===id)S.selected=item;displayBody(item);offerConfirmation(item);return item;
}
let warmingVersion=0;
function warmThread(){
  const version=++warmingVersion,ids=S.thread.filter(m=>!m.body_loaded).map(m=>m.id).reverse();
  const concurrency=3;
  setTimeout(async()=>{
    const queue=[...ids];
    const workers=Array.from({length:Math.min(concurrency,queue.length)},async()=>{
      while(queue.length&&version===warmingVersion&&navigator.onLine&&!document.hidden){
        const id=queue.shift();
        if(!id)break;
        try{await ensureBody(id,true);}catch{break;}
      }
    });
    await Promise.all(workers);
  },300);
}
async function applyThread(result,id,version,cached=false){
  if(!cached)replica.observe(result.messages);
  if(version!==S.readerVersion||id!==S.readerAnchor)return;
  const visible=new Set([...document.querySelectorAll('.thread-message[open]')].map(el=>el.dataset.threadMessage));visible.add(result.messages.at(-1)?.id);
  const local=replica.find(threadKey(result.messages[0]||S.selected)),overlay=S.optimistic.get(threadKey(result.messages[0]||S.selected))?.patch||{};
  const messages=await Promise.all(result.messages.map(async original=>{
    const metadata={...original,...(cached&&local?{read:local.read,starred:local.starred,pinned:local.pinned}:{}),...overlay};
    if(!visible.has(metadata.id))return metadata;
    const message=await deviceCache.get('api:'+bodyPath(metadata.id));
    if(message)replica.body(message);
    return message&&(!metadata.content_version||message.content_version===metadata.content_version)?{...message,...metadata,body_loaded:true}:metadata;
  }));
  if(version!==S.readerVersion||id!==S.readerAnchor)return;
  const signature=JSON.stringify(result.messages)+JSON.stringify({phase:result.sync?.phase,error:result.sync?.error});
  const changed=S.loadingMessage||S.threadSignature!==signature;S.threadSignature=signature;
  S.thread=messages;S.threadSync=result.sync||{};if(S.thread.length)S.selected=S.thread.at(-1);
  S.loadingMessage=false;if(changed){renderReading();warmThread();}
  for(const message of messages)offerConfirmation(message);
}
const threadRequests=new Map();
async function loadThread(id,version=S.readerVersion){
  const path='/messages/'+encodeURIComponent(id)+'/thread?lazy=true';
  const cached=await deviceCache.get('api:'+path)||await deviceCache.get('thread:'+threadKey(S.selected));
  if(cached)await applyThread(cached,id,version,true);
  let request=threadRequests.get(id);
  if(!request){request={started:replica.revision,promise:api(path)};threadRequests.set(id,request);request.promise.finally(()=>{if(threadRequests.get(id)===request)threadRequests.delete(id);}).catch(()=>{});}
  const started=request.started;
  const remote=(async()=>{
    try{
      const result=await request.promise;
      if(started===replica.revision&&S.status?.authenticated)await applyThread(result,id,version);
      if(started===replica.revision&&S.status?.authenticated&&result.messages.length)await deviceCache.set('thread:'+threadKey(result.messages[0]),result);
    }catch(error){
      if(!cached&&version===S.readerVersion){S.loadingMessage=false;S.threadSync={error:error.message};renderReading();}
      if(!temporarilyUnavailable(error)&&!cached)throw error;
      renderChrome();
    }
  })();remote.catch(()=>{});
  if(!cached)await remote;
}
async function selectMessage(id,markRead=true) {
  warmingVersion++;const version=++S.readerVersion;
  const cached=S.messages.find(m=>m.id===id);
  S.readerAnchor=id;S.selected=cached||{id,subject:'Conversazione',category:'people'};
  S.thread=[];S.threadSync={};S.loadingMessage=true;S.menu=false;
  $('.shell')?.classList.add('has-selection');$('.shell')?.classList.remove('menu-open');
  renderList();renderReading();
  try {
    await loadThread(id,version);
    if(version===S.readerVersion&&markRead&&S.thread.some(m=>!m.read&&!m.sent))mutate({read:true}).catch(error=>toast(error.message));
  }catch(error){if(version===S.readerVersion){S.loadingMessage=false;S.threadSync={error:error.message};renderReading();}throw error;}
}
function adjustCounts(before,after,deleted=false){
  const counts={...S.state.counts};
  const inbox=Number(Boolean(before.has_inbox)),nextInbox=deleted?0:Number(Boolean(after.has_inbox));
  counts.inbox=Math.max(0,(counts.inbox||0)+nextInbox-inbox);
  counts.starred=Math.max(0,(counts.starred||0)+(deleted?0:Number(Boolean(after.starred)))-Number(Boolean(before.starred)));
  const unreadThread=row=>(row.inbox_unread_count??row.unread_count??(row.read?0:1))>0?1:0;
  counts.unread=Math.max(0,(counts.unread||0)+(deleted||!nextInbox?0:unreadThread(after))-unreadThread(before));
  counts.snoozed=Math.max(0,(counts.snoozed||0)+(deleted?0:Number(after.snoozed_until>Date.now()/1000))-Number(before.snoozed_until>Date.now()/1000));
  S.state={...S.state,counts};
}
async function mutate(patch,deleted=false){
  if(!S.selected?.account_id)return;
  if(S.compose&&(deleted||'archived' in patch||'snoozed_until' in patch))closeCompose().catch(error=>toast(error.message));
  const id=S.readerAnchor,key=threadKey(S.selected),before=replica.find(key)||S.selected;
  const operation={id:crypto.randomUUID(),key,message_id:id,patch,deleted};
  await deviceCache.enqueue(operation);
  const token={patch:{...S.optimistic.get(key)?.patch,...patch},deleted,operationId:operation.id};S.optimistic.set(key,token);
  for(const [id,error] of S.queueErrors)if(error.key===key)S.queueErrors.delete(id);
  replica.apply(operation);adjustCounts(before,replica.find(key)||{...before,...patch},deleted);
  const current=S.selected&&threadKey(S.selected)===key;
  if(current){S.selected={...S.selected,...patch};S.thread=S.thread.map(m=>({...m,...patch}));}S.listVersion++;
  let deletedIndex=-1;
  if(current&&deleted){deletedIndex=S.messages.findIndex(m=>threadKey(m)===key);}
  const shouldClose=('archived' in patch||'snoozed_until' in patch||deleted);
  if(current&&shouldClose){S.selected=null;S.thread=[];S.readerAnchor=null;S.readerVersion++;$('.shell')?.classList.remove('has-selection');}
  paintLocal();
  if(current&&deleted&&deletedIndex>=0&&S.messages.length){
    const nextIndex=Math.min(deletedIndex,S.messages.length-1);
    const nextMessage=S.view==='drafts'?S.drafts[nextIndex]:S.messages[nextIndex];
    if(nextMessage)selectMessage(nextMessage.id,false).catch(()=>{});
    else{S.selected=null;S.thread=[];S.readerAnchor=null;S.readerVersion++;$('.shell')?.classList.remove('has-selection');renderReading();}
  }else if(!current||!deleted)renderReading();
  await deviceCache.set('api:/state',S.state);
  if(!S.online)toast('Modifica salvata sul dispositivo. Verrà sincronizzata quando torni online.');
  else if(deleted)toast('Conversazione eliminata. Sincronizzo il cestino in background.');
  flushClientQueue().catch(()=>{});
}
async function savePreference(setting,body,account_id=null){
  const allowed=account_id?['name','enabled','color']:({identity:['name','aliases','context','reply_language'],appearance:['theme'],ai:['model','automatic','cloud_consent']})[setting];
  if(!allowed||Object.keys(body).some(key=>!allowed.includes(key)))throw new Error('Preferenza non valida.');
  const operation={id:crypto.randomUUID(),kind:'setting',key:account_id?'account:'+account_id:'setting:'+setting,
    setting,account_id,body,method:account_id?'PATCH':'PUT',path:account_id?'/accounts/'+encodeURIComponent(account_id):'/settings/'+setting};
  if(setting==='identity'&&(body.aliases.length>20||body.aliases.some(alias=>alias.length>80||/[\r\n\0]/.test(alias))))throw new Error('Usa al massimo 20 nomi, ciascuno entro 80 caratteri.');
  for(const [id,error] of S.queueErrors)if(error.key===operation.key)S.queueErrors.delete(id);
  replica.apply(operation);S.pendingSettings.set(operation.key,operation);
  if(account_id)S.state.accounts=S.state.accounts.map(a=>a.id===account_id?{...a,...body}:a);
  else S.state[setting]=body;
  renderChrome();await deviceCache.enqueue(operation);await deviceCache.set('api:/state',S.state);
  flushClientQueue().catch(()=>{});
}

function showSettings(tab=S.settingsTab) {
  S.settingsTab=tab;
  const tabs=`<div class="modal-tabs">${[['accounts','Account'],['identity','Identità'],['compose','Firme'],['ai','Milo AI'],['rules','Filtri'],['notifications','Notifiche'],['appearance','Aspetto'],['devices','Dispositivi']].map(([id,name])=>`<button data-settings-tab="${id}" class="${id===tab?'active':''}">${name}</button>`).join('')}</div>`;
  let body='';
  if(tab==='accounts') {
    body=`<p>Collegali una volta. Gli account sono conservati sul tuo servizio Milo e disponibili agli altri dispositivi.</p>${S.state.accounts.map(a=>`<div class="settings-account"><span class="dot" style="background:${accountColor(a.id)}"></span><div><strong>${esc(a.name)}</strong><small>${esc(a.email)}</small></div><span class="health ${a.error?'error':''}">${!a.enabled?'In pausa':a.error?'Da controllare':a.last_sync?'Sincronizzato':'In attesa'}</span><button class="secondary" data-edit-account="${esc(a.id)}">Gestisci</button></div>${a.error?`<p class="form-error">${esc(a.error)}</p>`:''}`).join('')}<div class="form-actions"><button class="primary" data-action="add-account">${icon('plus')}Collega un account</button></div>${S.state.pending?.length?`<div class="notice" style="margin-top:20px">${S.state.pending.map(p=>`${p.count} modifiche ${esc(p.kind)}: ${esc(p.error||'in attesa della prossima sincronizzazione')}`).join('<br>')}</div>`:''}`;
  } else if(tab==='identity') {
    const identity=S.state.identity||{};
    body=`<form id="identity-form"><p>Aiuta Milo a riconoscere quando si parla di te e a scrivere dalla tua prospettiva.</p><label class="field"><span>Il tuo nome</span><input name="name" value="${esc(identity.name)}" maxlength="120" placeholder="Il nome con cui ti presenti"></label><label class="field"><span>Come ti chiamano</span><input name="aliases" value="${esc((identity.aliases||[]).join(', '))}" maxlength="1600" placeholder="Nomi e soprannomi, separati da virgole"></label><label class="field"><span>Contesto su di te</span><textarea name="context" maxlength="2000" placeholder="Ruolo, team e informazioni utili per capire chi è chi">${esc(identity.context)}</textarea></label><label class="field"><span>Lingua delle risposte</span><select name="reply_language">${[['auto','Segui la conversazione'],['en','Inglese'],['it','Italiano'],['fr','Francese'],['de','Tedesco'],['es','Spagnolo'],['pt','Portoghese']].map(([value,label])=>`<option value="${value}" ${(identity.reply_language||'auto')===value?'selected':''}>${label}</option>`).join('')}</select></label><p class="fineprint">Gli indirizzi delle caselle collegate sono già riconosciuti come tuoi. Questa identità è condivisa con tutti i tuoi dispositivi.</p><div class="form-error" role="alert"></div><button class="primary" type="submit">Salva identità</button></form>`;
  } else if(tab==='compose') {
    const signatures=S.state.signatures||{},templates=S.state.templates||[];
    body=`<form id="signatures-form"><p>La firma viene aggiunta ai nuovi messaggi e alle risposte della casella da cui scrivi.</p>${S.state.accounts.map(a=>`<label class="field"><span>Firma per ${esc(a.name)} · ${esc(a.email)}</span><textarea name="${esc(a.id)}" maxlength="4000" rows="3" placeholder="Nome, ruolo, contatti">${esc(signatures[a.id]||'')}</textarea></label>`).join('')}<div class="form-error" role="alert"></div><div class="form-actions"><button class="primary" type="submit">Salva firme</button></div></form><h3 class="settings-section">Risposte salvate</h3><p>Testi che usi spesso, da inserire nel messaggio con un clic.</p>${templates.map((template,index)=>`<div class="rule-row"><div><strong>${esc(template.name)}</strong>${esc(template.body.slice(0,120))}</div><button class="icon-button" data-delete-template="${index}" aria-label="Elimina risposta salvata">${icon('trash')}</button></div>`).join('')}<form id="template-form" style="margin-top:16px"><label class="field"><span>Nome</span><input name="name" maxlength="80" required placeholder="Grazie, ti aggiorno"></label><label class="field"><span>Testo</span><textarea name="body" maxlength="8000" required rows="4"></textarea></label><div class="form-error" role="alert"></div><div class="form-actions"><button class="secondary" type="submit">Aggiungi risposta</button></div></form>`;
  } else if(tab==='notifications') {
    const settings=notificationSettings(),supported='Notification' in window,permission=supported?Notification.permission:'denied';
    body=`<form id="notifications-form"><p>Le notifiche arrivano su questo dispositivo mentre Milo è aperto, anche in secondo piano.</p>${!supported?'<div class="notice">Questo browser non supporta le notifiche.</div>':permission==='denied'?'<div class="notice">Le notifiche sono bloccate dal browser per Milo. Riattivale dalle impostazioni del sito.</div>':''}<label class="field"><span>Notificami</span><select name="mode">${[['off','Mai'],['important','Persone e mittenti VIP'],['all','Tutte le nuove email']].map(([value,label])=>`<option value="${value}" ${settings.mode===value?'selected':''}>${label}</option>`).join('')}</select></label><label class="check-field"><input type="checkbox" name="morning" ${settings.morning?'checked':''}><span>Il punto di oggi: un recap della tua inbox ogni mattina dalle 8.</span></label><div class="form-error" role="alert"></div><div class="form-actions"><button class="primary" type="submit">Salva notifiche</button></div></form>`;
  } else if(tab==='appearance') {
    body=`<form id="appearance-form"><p>Scegli come vedere Milo. La preferenza è condivisa con i tuoi dispositivi.</p><label class="field"><span>Tema</span><select name="theme">${[['system','Segui il sistema'],['light','Chiaro'],['dark','Scuro']].map(([value,label])=>`<option value="${value}" ${S.theme===value?'selected':''}>${label}</option>`).join('')}</select></label><div class="notice">Puoi scegliere il colore di ogni casella da Account → Gestisci.</div><div class="form-error" role="alert"></div><button class="primary" type="submit">Salva aspetto</button></form>`;
  } else if(tab==='ai') {
    const ai=S.state.ai;
    body=`<form id="ai-form"><p>Analisi, recap e risposte proposte passano da Ollama. Le risposte restano bozze da rivedere e inviare personalmente.</p><label class="field"><span>Modello Ollama</span><input name="model" value="${esc(ai.model)}" required></label><div class="notice"><strong>DeepSeek V4.1 Flash usa Ollama Cloud.</strong><br>Con <code>deepseek-v4.1-flash:cloud</code>, il contenuto delle email selezionate viene elaborato nel cloud di Ollama. Puoi scegliere un modello locale già installato.</div><label class="check-field"><input type="checkbox" name="cloud_consent" ${ai.cloud_consent?'checked':''}><span>Consento l’elaborazione delle email con modelli cloud.</span></label><label class="check-field"><input type="checkbox" name="automatic" ${ai.automatic?'checked':''}><span>Analizza automaticamente le nuove email e organizza l’inbox in Persone, Notifiche e Newsletter.</span></label>${S.state.ai_error?`<p class="form-error">${esc(S.state.ai_error)}</p>`:''}<div class="form-actions"><button class="primary" type="submit">Salva preferenze</button></div></form>`;
  } else if(tab==='rules') {
    body=`<form id="screener-form" class="screener-setting"><label class="check-field"><input type="checkbox" name="enabled" ${S.state.screener?.enabled?'checked':''}><span><strong>Filtra i nuovi mittenti.</strong> Chi ti scrive per la prima volta aspetta in Nuovi mittenti finché non lo approvi. Le persone a cui hai già scritto passano sempre.</span></label><button class="secondary" type="submit">Salva</button></form><p>I tuoi filtri hanno precedenza sulla classificazione AI e vengono applicati anche alle email già salvate.</p>${S.state.rules.map(r=>`<div class="rule-row"><div><strong>${esc(r.name)}</strong>${esc(r.contains)} → ${categoryNames[r.category]}</div><button class="icon-button" data-delete-rule="${esc(r.id)}" aria-label="Elimina filtro">${icon('trash')}</button></div>`).join('')}<form id="rule-form" style="margin-top:22px"><div class="form-grid"><label class="field full"><span>Nome del filtro</span><input name="name" placeholder="Le notifiche di GitHub" required></label><label class="field"><span>Quando</span><select name="field"><option value="sender">Il mittente contiene</option><option value="subject">L’oggetto contiene</option><option value="body">Il testo contiene</option></select></label><label class="field"><span>Questo testo</span><input name="contains" placeholder="github.com" required></label><label class="field full"><span>Sposta nella categoria</span><select name="category">${Object.entries(categoryNames).map(([key,name])=>`<option value="${key}">${name}</option>`).join('')}</select></label></div><div class="form-actions"><button class="primary" type="submit">Crea filtro</button></div></form>`;
  } else {
    body=`<p>Questa è la casa del tuo archivio. Un altro dispositivo che accede allo stesso indirizzo trova account, email, preferenze e bozze già configurati.</p><div class="notice"><strong>Indirizzo del servizio</strong><br>${esc(location.origin)}</div><p>Per accedere da iPhone servirà un indirizzo HTTPS raggiungibile dal telefono. La versione nativa iOS e le notifiche push sono i prossimi passi; questa prima versione parte da Linux.</p><div class="notice">I messaggi scaricati sono conservati nella cache privata di questo dispositivo e si possono leggere offline. L’archivio completo e gli account restano sul servizio.</div><h3 class="settings-section">Backup della configurazione</h3><p>Identità, firme, risposte salvate, filtri, mittenti, bozze, cose da fare e il lavoro di Milo sulle email (categorie, analisi, pin). Le password non sono incluse: dopo un ripristino ricollega le caselle e la posta torna dai provider.</p><div class="form-actions backup-actions"><a class="secondary" href="/api/backup" download="milo-configurazione.json">${icon('download')}Scarica configurazione</a></div><form id="restore-form"><label class="field"><span>Ripristina da un file di configurazione</span><input type="file" name="file" accept=".json,application/json" required></label><div class="form-error" role="alert"></div><div class="form-actions"><button class="secondary" type="submit">Ripristina</button></div></form>${S.status.access==='tailscale'?'<div class="notice">Accesso privato tramite i tuoi dispositivi Tailscale autorizzati. Il dominio pubblico mostra solo la presentazione di Milo.</div>':!S.status.demo?'<div class="form-actions"><button class="secondary" data-action="logout">Esci da questo dispositivo</button></div>':''}`;
  }
  showModal('Il tuo Milo',tabs+body);
}

function showAccountForm() {
  if(S.status.demo) { toast('Apri il servizio Milo per collegare la tua posta.'); return; }
  const google=S.state.google;
  const setup=google?.configured?'':`<details class="oauth-help" open><summary>Configura Google una volta per il tuo servizio</summary><ol><li>In <a href="https://console.cloud.google.com/apis/library/gmail.googleapis.com" target="_blank" rel="noopener">Google Cloud</a> abilita Gmail API e configura il consenso OAuth per Milo.</li><li>Crea un client di tipo <strong>Applicazione web</strong> con questo URI di reindirizzamento:<div class="notice callback-url">${esc(google?.redirect_uri||'')}</div></li><li>Scarica il JSON delle credenziali e importalo qui. Se l’app è in Testing, aggiungi i tuoi indirizzi come utenti di test.</li></ol><form id="google-config-form"><label class="field"><span>Credenziali OAuth Google (.json)</span><input type="file" name="credentials" accept=".json,application/json" required></label><div class="form-error" role="alert"></div><div class="form-actions"><button class="primary" type="submit">Configura Google</button></div></form></details>`;
  showModal('Collega la tua posta',`<p>Accedi al tuo account Google e autorizza Milo a leggere, organizzare e inviare la tua posta. Il collegamento resta sul servizio e vale per tutti i tuoi dispositivi.</p>${setup}<div class="account-connect-actions"><button class="primary google-connect" data-action="google-connect" ${google?.configured?'':'disabled'}>${googleIcon()}Continua con Google ${icon('arrow')}</button><button class="secondary" data-action="imap-account">Collega iCloud o un account IMAP</button></div>`);
}

function showIMAPForm() {
  showModal('Collega un account IMAP',`<form id="account-form"><label class="field"><span>Provider</span><select id="provider"><option value="icloud">iCloud Mail</option><option value="other">Altro account IMAP</option></select></label><div class="notice" id="provider-notice"><strong>Per iCloud serve una password specifica per app.</strong><br>iCloud non permette l'accesso con la password del tuo account Apple. Devi generarne una:
<details class="guide-steps" style="margin-top:8px"><summary>Come creare la password per app su iCloud</summary><ol style="margin:8px 0 0;padding-left:18px;font-size:13px;line-height:1.6">
<li>Vai su <strong>appleid.apple.com</strong> e accedi con il tuo Apple ID</li>
<li>Nella sezione <strong>"Accesso e sicurezza"</strong>, clicca su <strong>"Password specifiche per app"</strong></li>
<li>Clicca il pulsante <strong>+</strong> (o "Genera password")</li>
<li>Inserisci un nome, es. <em>"Milo"</em>, e clicca <strong>"Crea"</strong></li>
<li>Copia la password generata (sarà del tipo <code>xxxx-xxxx-xxxx-xxxx</code>) e incollala qui sotto</li>
</ol>
<p style="margin:8px 0 0;font-size:12px;color:var(--muted)">Puoi revocarla in qualsiasi momento da appleid.apple.com. La password di Apple non vienemai salvata da Milo.</p></details>
Il nome utente IMAP è la parte prima di <code>@icloud.com</code> (es. <code>mario</code> per <code>mario@icloud.com</code>).</div><div class="form-grid"><label class="field"><span>Nome dell’account</span><input name="name" value="Personale" required maxlength="80"></label><label class="field"><span>Indirizzo email</span><input name="email" type="email" required autocomplete="email" placeholder="mario@icloud.com"></label><label class="field"><span>Nome utente</span><input name="username" placeholder="Di solito l’indirizzo email" required></label><label class="field"><span>Password per app</span><input name="password" type="password" required autocomplete="off" placeholder="xxxx-xxxx-xxxx-xxxx"></label><label class="field"><span>Server IMAP</span><input name="imap_host" value="imap.mail.me.com" required></label><label class="field"><span>Porta IMAP (TLS)</span><input name="imap_port" type="number" value="993" min="1" max="65535" required></label><label class="field"><span>Server SMTP</span><input name="smtp_host" value="smtp.mail.me.com" required></label><label class="field"><span>Porta SMTP</span><input name="smtp_port" type="number" value="587" min="1" max="65535" required></label><label class="field full"><span>Sicurezza SMTP</span><select name="smtp_security"><option value="tls">TLS</option><option value="starttls" selected>STARTTLS</option></select></label></div><div class="form-error" role="alert"></div><div class="form-actions"><button class="secondary" type="button" data-action="close-modal">Annulla</button><button class="primary" type="submit">Collega e sincronizza ${icon('arrow')}</button></div></form>`);
}

function showAccountSettings(accountId) {
  const a=S.state.accounts.find(account=>account.id===accountId);
  if(!a) return;
  const imap=a.provider==='imap';
  const connection=imap?`<div class="form-grid"><label class="field"><span>Nome utente</span><input name="username" value="${esc(a.username)}" required></label><label class="field"><span>Nuova password per app</span><input name="password" type="password" autocomplete="new-password" placeholder="Lascia vuoto per conservarla"></label><label class="field"><span>Server IMAP</span><input name="imap_host" value="${esc(a.imap_host)}" required></label><label class="field"><span>Porta IMAP (TLS)</span><input name="imap_port" type="number" value="${a.imap_port}" min="1" max="65535" required></label><label class="field"><span>Server SMTP</span><input name="smtp_host" value="${esc(a.smtp_host)}" required></label><label class="field"><span>Porta SMTP</span><input name="smtp_port" type="number" value="${a.smtp_port}" min="1" max="65535" required></label><label class="field full"><span>Sicurezza SMTP</span><select name="smtp_security"><option value="tls" ${a.smtp_security==='tls'?'selected':''}>TLS</option><option value="starttls" ${a.smtp_security==='starttls'?'selected':''}>STARTTLS</option></select></label></div>`:`<p>L’accesso Google è conservato sul servizio. Se Google lo revoca o scade, ricollega questa casella.</p><button class="secondary" type="button" data-action="google-connect" data-reconnect-account="${esc(a.id)}">Ricollega ${esc(a.email)}</button>`;
  showModal('Gestisci account',`<form id="account-settings-form" data-account-id="${esc(a.id)}"><div class="notice">${esc(a.email)} · ${imap?'IMAP':'Google'}</div><label class="field"><span>Nome dell’account</span><input name="name" value="${esc(a.name)}" required maxlength="80"></label><label class="field color-field"><span>Colore della casella</span><input name="color" type="color" value="${accountColor(a.id)}"></label><label class="check-field"><input type="checkbox" name="enabled" ${a.enabled?'checked':''}><span>Sincronizza questa casella. In pausa, le email e le bozze salvate restano disponibili; le modifiche aspettano la ripresa.</span></label>${connection}<div class="form-error" role="alert"></div><div class="form-actions"><button class="secondary danger remove-account" type="button" data-remove-account="${esc(a.id)}">Rimuovi account</button><button class="secondary" type="button" data-action="close-modal">Annulla</button><button class="primary" type="submit">Salva account</button></div></form>`);
}

function composeMarkup(draft,inline=false) {
  return `<form id="compose-form" class="${inline?'inline-compose-form':''}"><div class="compose-heading"><h3>${draft.mode==='forward'?'Inoltra':['reply','reply_all'].includes(draft.mode)?draft.mode==='reply_all'?'Rispondi a tutti':'Rispondi':'Nuovo messaggio'}</h3>${inline?`<button class="icon-button" type="button" data-action="close-compose" aria-label="Chiudi" title="Chiudi bozza">${icon('close')}</button>`:''}</div><label class="field"><span>Da</span><select name="account_id">${S.state.accounts.map(a=>`<option value="${esc(a.id)}" ${draft.account_id===a.id?'selected':''}>${esc(a.name)} · ${esc(a.email)}</option>`).join('')}</select></label><label class="field recipient-field"><span>A</span><input name="to" value="${esc(draft.to)}" placeholder="nome@example.com" maxlength="2000" autocomplete="off" role="combobox" aria-autocomplete="list" aria-expanded="false"></label><label class="field recipient-field"><span>Cc</span><input name="cc" value="${esc(draft.cc)}" placeholder="Copia conoscenza" maxlength="2000" autocomplete="off" role="combobox" aria-autocomplete="list" aria-expanded="false"></label><label class="field"><span>Oggetto</span><input name="subject" value="${esc(draft.subject)}" placeholder="Di cosa parliamo?" maxlength="998"></label><label class="field"><span>Messaggio</span><textarea class="composer-body" name="body" placeholder="Scrivi qui…" maxlength="1000000">
${esc(draft.body)}</textarea></label>${composeHtmlMarkup(draft)}<div class="attachments compose-attachments">${composeAttachments(draft)}</div><div class="compose-tools"><button class="secondary attach-button" type="button" data-action="attach-file">${icon('paperclip')}Allega</button><input class="attach-input" type="file" multiple hidden>${(S.state.templates||[]).length?`<select class="template-select" aria-label="Inserisci una risposta salvata"><option value="">Risposte salvate…</option>${S.state.templates.map((template,index)=>`<option value="${index}">${esc(template.name)}</option>`).join('')}</select>`:''}<label class="followup-field"><span>Ricordamelo se non risponde</span><select name="followup_days">${[['','mai'],['1','entro 1 giorno'],['3','entro 3 giorni'],['7','entro una settimana']].map(([value,label])=>`<option value="${value}" ${String(draft.followup_days||'')===value?'selected':''}>${label}</option>`).join('')}</select></label></div><div class="form-error" role="alert"></div><div class="form-actions"><button class="secondary" type="button" data-action="delete-draft">Elimina bozza</button><button class="secondary" type="button" data-action="save-draft">Salva bozza</button><button class="secondary" type="button" data-action="schedule-send">${icon('clock')}Programma</button><button class="primary" type="submit">${icon('sent')}Invia messaggio</button></div><div class="draft-save-status" role="status">${S.pendingDrafts.has(draft.id)?'Salvataggio in attesa':'Le modifiche vengono salvate automaticamente.'}</div></form>`;
}
function composeHtmlPreview(html){return `<!doctype html><html><head><meta charset="utf-8"><meta name="referrer" content="no-referrer"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><style>html{color-scheme:light}body{margin:0;padding:16px;font:15px/1.6 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#172033;overflow-wrap:anywhere}img,table{max-width:100%!important}</style></head><body>${html}</body></html>`;}
function composeHtmlMarkup(draft){const html=draft.html||'';return `<details class="compose-html"${html?' open':''}><summary><span>Versione HTML</span><small>${html?'Inviata insieme al testo semplice':'Facoltativa: chi la supporta vede questa, gli altri il testo'}</small></summary><div class="compose-html-grid"><label class="field"><span>Codice HTML</span><textarea class="composer-html" name="html" spellcheck="false" autocapitalize="off" placeholder="<p>Ciao…</p>" maxlength="1000000">
${esc(html)}</textarea></label><div class="compose-html-preview"><span>Anteprima</span><iframe sandbox="" referrerpolicy="no-referrer" title="Anteprima della versione HTML" srcdoc="${esc(composeHtmlPreview(html))}"></iframe><small>Le immagini esterne non si caricano nell'anteprima, così il pixel di tracciamento non si attiva.</small></div></div></details>`;}
let htmlPreviewTimer=0;
function scheduleComposeHtmlPreview(field){clearTimeout(htmlPreviewTimer);htmlPreviewTimer=setTimeout(()=>{const frame=field.closest('.compose-html')?.querySelector('iframe');if(frame)frame.srcdoc=composeHtmlPreview(field.value);const label=field.closest('.compose-html')?.querySelector('summary small');if(label)label.textContent=field.value.trim()?'Inviata insieme al testo semplice':'Facoltativa: chi la supporta vede questa, gli altri il testo';},250);}
const ATTACHMENT_LIMIT=18*1024*1024;
function fileSize(bytes){return bytes<1024?`${bytes} B`:bytes<1048576?`${Math.round(bytes/1024)} KB`:`${(bytes/1048576).toFixed(1).replace('.',',')} MB`;}
function composeAttachments(draft){
  return (draft.attachments||[]).map(a=>`<span class="attachment draft-attachment${a.uploading?' uploading':''}">${icon('paperclip')}<span class="attachment-name">${esc(a.name)}</span><small>${a.uploading?'Caricamento…':fileSize(a.size)}</small>${a.uploading?'':`<button type="button" data-action="remove-attachment" data-attachment-id="${esc(a.id)}" aria-label="Rimuovi ${esc(a.name)}" title="Rimuovi">${icon('close')}</button>`}</span>`).join('');
}
function paintComposeAttachments(){const slot=$('#compose-form .compose-attachments');if(slot&&S.compose)slot.innerHTML=composeAttachments(S.compose);}
const recipientSuggest={field:null,items:[],active:0,request:0,timer:0};
function recipientToken(value,cursor){
  const before=value.slice(0,cursor??value.length);
  const cut=Math.max(before.lastIndexOf(','),before.lastIndexOf(';'));
  return before.slice(cut+1).trim();
}
function finishedAddress(token){return /^[^\s,;<>@]+@[^\s,;<>@]+\.[^\s,;<>@]+$/.test(token);}
function chosenRecipients(value){
  return new Set([...value.matchAll(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi)].map(match=>match[0].toLowerCase()));
}
function hideRecipients(){
  clearTimeout(recipientSuggest.timer);
  document.querySelectorAll('.recipient-list').forEach(node=>node.remove());
  document.querySelectorAll('#compose-form [role="combobox"]').forEach(input=>input.setAttribute('aria-expanded','false'));
  recipientSuggest.field=null;
}
function paintRecipients(field,items){
  field.parentElement?.querySelector('.recipient-list')?.remove();
  if(!items.length||document.activeElement!==field){field.setAttribute('aria-expanded','false');return;}
  recipientSuggest.items=items;
  recipientSuggest.active=Math.min(recipientSuggest.active,items.length-1);
  const list=document.createElement('div');
  list.className='recipient-list';list.id='recipient-list';list.setAttribute('role','listbox');
  items.forEach((person,index)=>{
    const button=document.createElement('button');
    button.type='button';button.className='recipient-option'+(index===recipientSuggest.active?' active':'');
    button.setAttribute('role','option');button.dataset.recipient=String(index);
    button.setAttribute('aria-selected',index===recipientSuggest.active?'true':'false');
    const name=document.createElement('strong');name.textContent=person.name||person.email;
    button.append(name);
    if(person.name){const mail=document.createElement('small');mail.textContent=person.email;button.append(mail);}
    list.append(button);
  });
  field.setAttribute('aria-expanded','true');field.setAttribute('aria-controls','recipient-list');
  field.after(list);
}
async function loadRecipients(field){
  const token=recipientToken(field.value,field.selectionStart);
  if(token.includes('<')||token.length>80||finishedAddress(token)){hideRecipients();return;}
  const request=++recipientSuggest.request;
  recipientSuggest.field=field;
  try{
    const data=await api('/recipients'+(token?`?q=${encodeURIComponent(token)}`:''));
    if(request!==recipientSuggest.request||document.activeElement!==field)return;
    const taken=chosenRecipients(field.value);
    paintRecipients(field,(data.recipients||[]).filter(person=>person.email&&!taken.has(person.email.toLowerCase())));
  }catch{if(request===recipientSuggest.request)hideRecipients();}
}
function scheduleRecipients(field){clearTimeout(recipientSuggest.timer);recipientSuggest.timer=setTimeout(()=>loadRecipients(field),120);}
function acceptRecipient(index){
  const field=recipientSuggest.field&&document.contains(recipientSuggest.field)?recipientSuggest.field:document.activeElement;
  const person=recipientSuggest.items[index];
  if(!field||!person||!field.matches?.('[name="to"],[name="cc"]'))return;
  const value=field.value,cursor=field.selectionStart??value.length;
  const before=value.slice(0,cursor),after=value.slice(cursor);
  const cut=Math.max(before.lastIndexOf(','),before.lastIndexOf(';'));
  const head=cut<0?'':before.slice(0,cut+1).trimEnd()+' ';
  const restAt=after.search(/[,;]/);
  const tail=restAt<0?'':after.slice(restAt).trimStart();
  const label=person.name?`${person.name} <${person.email}>`:person.email;
  const sep=tail?'':', ';
  field.value=head+label+sep+tail;
  const pos=(head+label+sep).length;
  field.focus();field.setSelectionRange(pos,pos);
  field.dispatchEvent(new Event('input',{bubbles:true}));
}
// Files go straight to the server under the draft id; the draft row may be saved later.
async function attachFiles(files){
  const compose=S.compose;if(!compose||!files.length)return;
  let used=(compose.attachments||[]).reduce((total,a)=>total+(a.size||0),0);
  for(const file of files){
    if(used+file.size>ATTACHMENT_LIMIT){toast(`${file.name}: gli allegati superano 18 MB, il messaggio verrebbe rifiutato.`);continue;}
    used+=file.size;
    const pending={id:'uploading-'+crypto.randomUUID(),name:file.name,size:file.size,uploading:true};
    compose.attachments=[...(compose.attachments||[]),pending];paintComposeAttachments();
    try{
      const response=await fetch(`/api/drafts/${encodeURIComponent(compose.id)}/attachments?name=${encodeURIComponent(file.name)}`,{method:'POST',credentials:'same-origin',headers:{'Content-Type':file.type||'application/octet-stream'},body:file});
      const data=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(data.detail||'Allegato non caricato');
      compose.attachments=compose.attachments.map(a=>a.id===pending.id?data:a);
    }catch(error){
      used-=file.size;compose.attachments=compose.attachments.filter(a=>a.id!==pending.id);
      toast(error.message==='Failed to fetch'?'Connessione a Milo interrotta: allegato non caricato.':error.message);
    }
    if(S.compose===compose)paintComposeAttachments();
  }
}
async function removeAttachment(id){
  const compose=S.compose;if(!compose)return;
  await api(`/drafts/${encodeURIComponent(compose.id)}/attachments/${encodeURIComponent(id)}`,'DELETE');
  compose.attachments=(compose.attachments||[]).filter(a=>a.id!==id);if(S.compose===compose)paintComposeAttachments();
}
function renderInlineComposer(existing=null) {
  const slot=$('#inline-composer');if(!slot||!S.compose)return;
  if(existing)slot.append(existing);else slot.innerHTML=composeMarkup(S.compose,true);
}
function captureCompose() {
  const form=$('#compose-form');if(!form||!S.compose)return null;
  const fields=Object.fromEntries(new FormData(form));
  const changed=Object.keys(fields).some(key=>fields[key]!==String(S.compose[key]||''));
  S.compose={...S.compose,...fields,revision:changed?Math.max(Date.now(),(S.compose.revision||0)+1):S.compose.revision};
  return {...S.compose};
}
function storePendingDrafts(){clearTimeout(localDraftTimer);try{localStorage.setItem('milo-pending-drafts',JSON.stringify([...S.pendingDrafts.values()]));}catch{toast('Spazio locale esaurito. La bozza resta in Bozze finché Milo è aperto; attendi il salvataggio sul server prima di uscire.');}}
function rememberDraft(draft,immediate=true){if(!draft||S.discardedDrafts.has(draft.id)||(!draft.to&&!draft.subject&&!draft.body))return false;if((S.pendingDrafts.get(draft.id)?.revision||0)>draft.revision)return true;S.pendingDrafts.set(draft.id,{...draft});if(immediate)storePendingDrafts();else{clearTimeout(localDraftTimer);localDraftTimer=setTimeout(storePendingDrafts,200);}return true;}
function draftPayload(draft){return Object.fromEntries(['id','account_id','to','cc','subject','body','html','reply_to_id','context_message_id','mode','revision'].map(key=>[key,draft[key]??(['to','cc','subject','body','html'].includes(key)?'':null)]));}
function persistDraft(draft) {
  if(!rememberDraft(draft)||S.discardedDrafts.has(draft.id))return Promise.resolve(null);
  const previous=S.draftWrites.get(draft.id);
  if(previous&&previous.revision>=draft.revision)return previous.promise;
  const promise=(previous?.promise||Promise.resolve()).catch(()=>{}).then(async()=>{
    if(S.discardedDrafts.has(draft.id))return null;
    if($('#compose-form')&&S.compose?.id===draft.id&&$('.draft-save-status'))$('.draft-save-status').textContent='Bozza salvata sul dispositivo · sincronizzazione…';
    const result=await api('/drafts','PUT',draftPayload(draft));
    if(!S.discardedDrafts.has(draft.id))await cachedDraftChange(result.id,draft);
    if((S.pendingDrafts.get(draft.id)?.revision||0)<=draft.revision)S.pendingDrafts.delete(draft.id);
    storePendingDrafts();
    if(S.compose?.id===draft.id&&$('.draft-save-status'))$('.draft-save-status').textContent='Bozza salvata';
    return result.id;
  });
  S.draftWrites.set(draft.id,{revision:draft.revision,promise});
  promise.finally(()=>{if(S.draftWrites.get(draft.id)?.promise===promise)S.draftWrites.delete(draft.id);flushClientQueue().catch(()=>{});}).catch(()=>{});
  return promise;
}
function removeComposer(){clearTimeout(autosaveTimer);if($('#overlay #compose-form'))$('#overlay').innerHTML='';if($('#inline-composer'))$('#inline-composer').innerHTML='';S.compose=null;}
async function cachedDraftChange(id,draft=null){
  const existing=await deviceCache.get('api:/drafts')||{drafts:[]};
  const drafts=existing.drafts.filter(item=>item.id!==id);
  if(draft)drafts.unshift({...draft,id,updated:Date.now()/1000});
  await deviceCache.set('api:/drafts',{drafts});
}
async function saveLocalDraft(draft){if(!rememberDraft(draft))return null;await cachedDraftChange(draft.id,draft);if(S.compose?.id===draft.id&&$('.draft-save-status'))$('.draft-save-status').textContent='Bozza salvata sul dispositivo';persistDraft(draft).catch(error=>{if(S.compose?.id===draft.id&&$('.draft-save-status'))$('.draft-save-status').textContent='Bozza salvata sul dispositivo · sincronizzazione in attesa';else toast(error.message);});return draft.id;}
async function closeCompose(){const draft=captureCompose();removeComposer();if(draft)await saveLocalDraft(draft);}
async function saveCompose(){clearTimeout(autosaveTimer);return saveLocalDraft(captureCompose());}
function showCompose(draft={},inline=Boolean(draft.reply_to_id||draft.context_message_id)) {
  if(!S.state.accounts.length){showAccountForm();return;}
  if(S.compose){
    if(inline&&S.compose.context_message_id===(draft.context_message_id||draft.reply_to_id)&&S.compose.mode===(draft.mode||'reply')){$('#compose-form [name="body"]')?.focus();return;}
    closeCompose().catch(error=>toast(error.message));
  }
  const mode=draft.reply_to_id&&(!draft.mode||draft.mode==='new')?'reply':draft.mode||'new';
  const fresh=!draft.id,accountId=draft.account_id||S.state.accounts[0].id,signature=S.state.signatures?.[accountId];
  if(fresh&&signature)draft={...draft,body:draft.mode==='forward'?`\n\n-- \n${signature}${draft.body||''}`:`${draft.body||''}\n\n-- \n${signature}`};
  const current={...draft,id:draft.id||crypto.randomUUID(),account_id:accountId,to:draft.to||'',cc:draft.cc||'',subject:draft.subject||'',body:draft.body||'',mode,reply_to_id:draft.reply_to_id||null,context_message_id:draft.context_message_id||draft.reply_to_id||null,revision:draft.revision||Date.now(),inline:inline&&Boolean($('#inline-composer')),thread_key:S.selected?threadKey(S.selected):null};
  current.initialBody=fresh?current.body:null;
  S.compose=current;
  if(current.inline){renderInlineComposer();$('#inline-composer').scrollIntoView({block:'nearest'});$('#inline-composer [name="body"]').focus({preventScroll:true});}
  else{showModal('Nuovo messaggio',composeMarkup(current),true);S.compose=current;}
}
async function openDraft(draft){
  if(S.compose)closeCompose().catch(error=>toast(error.message));
  if(draft.scheduled&&!draft.scheduled.error){await api('/drafts/'+encodeURIComponent(draft.id)+'/schedule','DELETE');toast('Programmazione annullata: rimandalo quando sei pronto.');}
  const anchor=draft.context_message_id||draft.reply_to_id;
  if(anchor){S.view='inbox';renderShell();await selectMessage(anchor,false);showCompose(draft,true);}
  else showCompose(draft,false);
}
async function discardCompose(){
  const draft=captureCompose();if(!draft)return;
  S.discardedDrafts.add(draft.id);localStorage.setItem('milo-discarded-drafts',JSON.stringify([...S.discardedDrafts]));S.pendingDrafts.delete(draft.id);storePendingDrafts();removeComposer();
  const operation={id:crypto.randomUUID(),kind:'draft_delete',key:'draft:'+draft.id,message_id:draft.id};
  replica.apply(operation);await deviceCache.enqueue(operation);await cachedDraftChange(draft.id);await refresh();toast('Bozza eliminata.');flushClientQueue().catch(()=>{});
}

function showRecap(result) {
  const scroll=S.recapOpen?$('.modal')?.scrollTop||0:0,phase=result.status?.phase||'pending';
  const status=phase==='updating'?'Aggiornamento in background…':phase==='disabled'?'Attiva l’AI nelle impostazioni per ricevere il recap automatico.':phase==='error'?'Aggiornamento in pausa. Milo riproverà in background.':result.generated_at?'Aggiornato '+dateLabel(result.generated_at,true):'Il primo recap arriverà in background.';
  const priorities=result.priorities||[];
  showModal('Il punto della tua inbox',`<div class="recap-meta" role="status">${icon('sparkle')}<span>${esc(status)}</span></div>${result.overview?`<p class="recap-overview">${esc(result.overview)}</p>`:'<p class="recap-empty">Quando sarà pronto, troverai qui il riepilogo della tua posta.</p>'}${priorities.length?`<h3 class="recap-section-title">Da tenere d’occhio</h3><div class="recap-priorities">${priorities.map((item,index)=>`<button class="priority-item" data-recap-message="${esc(item.message_id)}"><span class="priority-number">${index+1}</span><span>${esc(item.action)}</span>${icon('arrow')}</button>`).join('')}</div>`:''}${result.generated_at?`<p class="fineprint recap-source">${result.message_ids?.length||0} conversazioni · Verifica i dettagli nelle email originali.</p>`:''}`);
  S.recapOpen=true;S.recapSignature=JSON.stringify(S.state.recap);$('.modal').scrollTop=scroll;
}
async function openRecap() {
  const cached=await deviceCache.get('api:/recap');
  showRecap(cached||{status:{phase:S.state.recap?.phase||'pending'}});
  try{const result=await api('/recap');if(S.recapOpen)showRecap(result);}
  catch(error){if(!cached)toast(error.message);}
}
async function recipientContext(message){
  if('to_addresses' in message)return message;
  const path='/messages/'+encodeURIComponent(message.id)+'/recipients';
  const [body,cached]=await Promise.all([deviceCache.get('api:'+bodyPath(message.id)),deviceCache.get('api:'+path)]);
  const reusable=[body,cached].find(value=>value&&'to_addresses' in value&&(!message.content_version||value.content_version===message.content_version));
  return {...message,...(reusable||await api(path))};
}
async function runAI(action,button) {
  if(action==='recap'){await openRecap();return;}
  if(S.status.demo) { toast('Le funzioni AI si attivano sulla tua posta reale. Questa demo non simula analisi.'); return; }
  if(!S.state.ai.cloud_consent && S.state.ai.model?.includes('cloud')) { showSettings('ai'); toast('Scegli come elaborare la tua posta prima di attivare l’AI.'); return; }
  const source=S.thread.findLast(message=>!message.sent)||S.selected;
  const id=action==='ai-reply'?source?.id:S.selected?.id;
  if(button){button.disabled=true;button.classList.add('is-loading');if(action==='analyze'){S.analyzing=true;renderReading();}}
  let generatedDraft;
  const readerVersion=S.readerVersion;
  try {
  if(action==='ai-reply'){
    const original=await recipientContext(source);if(readerVersion!==S.readerVersion)return;
    showCompose({account_id:original.account_id,...replyRecipients(original),subject:'Re: '+subjectCore(original.subject),reply_to_id:id});
    generatedDraft={id:S.compose.id,revision:S.compose.revision};
    $('#compose-form .compose-heading').insertAdjacentHTML('afterend',`<div class="reply-generation">${skeleton(3,'block','Milo prepara una risposta…')}</div>`);
  }
    while(S.pendingSettings.size){if([...S.pendingSettings.values()].some(op=>S.queueErrors.has(op.id)))throw new Error('Controlla le preferenze non sincronizzate prima di usare l’AI.');await flushClientQueue();if(!S.online||Date.now()<queueRetryAt)throw new Error('Le preferenze devono essere sincronizzate prima di usare l’AI.');}
    if(action==='analyze') {
      await api('/messages/'+id+'/analyze','POST');
      S.analyzing=false;if(S.selected?.id===id)await loadThread(S.readerAnchor);
      await refresh();renderList();
    } else {
      const result=await api('/messages/'+id+'/reply','POST');
      if(S.compose?.id===generatedDraft.id&&S.compose.revision===generatedDraft.revision&&(S.compose.body||'')===(S.compose.initialBody||'')){
        const field=$('#compose-form [name="body"]');field.value=result.body+(S.compose.initialBody||'');field.dispatchEvent(new Event('input',{bubbles:true}));
      }else if(S.compose?.id===generatedDraft.id)toast('Hai già modificato la bozza. Il tuo testo è stato conservato.');
    }
  } catch(error) { if(action==='recap') closeModal(); toast(error.message); }
  finally { if(S.compose?.id===generatedDraft?.id)$('#compose-form .reply-generation')?.remove();S.analyzing=false;if(action==='analyze')renderReading();if(button){button.disabled=false;button.classList.remove('is-loading');} }
}

function notificationSettings(){try{return {mode:'off',morning:false,...JSON.parse(localStorage.getItem('milo-notify')||'{}')};}catch{return {mode:'off',morning:false};}}
function notifyNew(){
  const settings=notificationSettings();
  if(settings.mode==='off'||!('Notification' in window)||Notification.permission!=='granted'||!replica.available)return;
  let since=Number(settings.since||Date.now()/1000);try{since=Math.max(since,Number(localStorage.getItem('milo-notified-until')||0));}catch{}
  const vips=new Set(S.state.vips||[]),screened=new Set(S.state.screener?.enabled?S.state.screener.pending:[]);
  const rows=replica.keys().map(id=>replica.find(id)).filter(row=>row&&row.date>since);
  if(!rows.length)return;
  try{localStorage.setItem('milo-notified-until',String(Math.max(...rows.map(row=>row.date))));}catch{}
  const fresh=rows.filter(row=>{const sender=(row.sender_email||'').toLowerCase();return !row.deleted&&!row.sent&&row.has_inbox&&row.unread_count&&!screened.has(sender)&&(settings.mode==='all'||vips.has(sender)||row.category==='people');});
  for(const row of fresh.slice(0,3)){const note=new Notification(row.sender||row.sender_email,{body:subjectCore(row.subject),tag:threadKey(row),icon:'/static/icon-192.png'});note.onclick=()=>{window.focus();selectMessage(row.id).catch(()=>{});note.close();};}
  if(fresh.length>3)new Notification('Milo',{body:`Altre ${fresh.length-3} email nuove`,icon:'/static/icon-192.png'});
}
async function maybeMorningRecap(){
  const settings=notificationSettings(),now=new Date(),today=now.toDateString();
  if(!settings.morning||!('Notification' in window)||Notification.permission!=='granted'||now.getHours()<8)return;
  try{if(localStorage.getItem('milo-morning')===today)return;localStorage.setItem('milo-morning',today);}catch{return;}
  try{const recap=await api('/recap');if(recap.overview){const note=new Notification('Il punto di oggi',{body:recap.overview.slice(0,240),icon:'/static/icon-192.png'});note.onclick=()=>{window.focus();openRecap();note.close();};}}catch{}
}
async function bulkMutate(kind){
  const keys=[...S.multi];S.multi.clear();
  if(kind==='clear'||!keys.length){renderList();return;}
  const patch={archive:{archived:true},read:{read:true},star:{starred:true}}[kind]||{},deleted=kind==='trash';
  for(const key of keys){
    const before=replica.find(key);if(!before)continue;
    const operation={id:crypto.randomUUID(),key,message_id:before.id,patch,deleted};
    await deviceCache.enqueue(operation);
    S.optimistic.set(key,{patch:{...S.optimistic.get(key)?.patch,...patch},deleted,operationId:operation.id});
    replica.apply(operation);adjustCounts(before,replica.find(key)||{...before,...patch},deleted);
    if(S.selected&&threadKey(S.selected)===key&&(deleted||patch.archived)){S.selected=null;S.thread=[];S.readerAnchor=null;S.readerVersion++;$('.shell')?.classList.remove('has-selection');renderReading();}
  }
  S.listVersion++;paintLocal();renderList();await deviceCache.set('api:/state',S.state);
  toast(`${keys.length} ${keys.length===1?'conversazione aggiornata':'conversazioni aggiornate'}. Milo sincronizza in background.`);flushClientQueue().catch(()=>{});
}
function toggleTodo(id,range=false){
  const items=S.todos||[],index=items.findIndex(todo=>todo.id===id);if(index<0)return;
  if(range&&S.lastTodo!=null){const [from,to]=[Math.min(S.lastTodo,index),Math.max(S.lastTodo,index)];for(const todo of items.slice(from,to+1))S.todoMulti.add(todo.id);}
  else if(S.todoMulti.has(id))S.todoMulti.delete(id);else S.todoMulti.add(id);
  S.lastTodo=index;renderList();
}
async function completeTodos(ids){
  const chosen=[...ids];if(!chosen.length)return;
  S.todoMulti.clear();
  S.todos=(S.todos||[]).filter(todo=>!chosen.includes(todo.id));
  S.state.counts.todo=Math.max(0,(S.state.counts.todo||0)-chosen.length);
  renderList();renderChrome();
  try{for(const id of chosen)await api('/todos/'+encodeURIComponent(id),'PATCH',{done:true});}
  catch(error){revalidateView();throw error;}
  const label=chosen.length===1?'Fatto.':`${chosen.length} cose da fare segnate come fatte.`;
  toast(label,{label:'Annulla',run:()=>Promise.all(chosen.map(id=>api('/todos/'+encodeURIComponent(id),'PATCH',{done:false}))).then(()=>revalidateView()).catch(error=>toast(error.message))});
}
function toggleMulti(id,range=false){
  const index=S.messages.findIndex(m=>m.id===id);if(index<0)return;
  if(range&&S.lastMulti!=null){const [from,to]=[Math.min(S.lastMulti,index),Math.max(S.lastMulti,index)];for(const m of S.messages.slice(from,to+1))S.multi.add(threadKey(m));}
  else{const key=threadKey(S.messages[index]);S.multi.has(key)?S.multi.delete(key):S.multi.add(key);}
  S.lastMulti=index;renderList();
}
function scheduleOptions(){
  const at=(days,hours)=>{const date=new Date();date.setDate(date.getDate()+days);date.setHours(hours,0,0,0);return date;};
  const monday=at((8-new Date().getDay())%7||7,8),options=[[new Date(Date.now()+3600000),'Tra un’ora']];
  if(new Date().getHours()<17)options.push([at(0,18),'Oggi alle 18']);
  options.push([at(1,8),'Domani alle 8'],[monday,'Lunedì alle 8']);
  return options;
}
async function scheduleDraft(id,sendAt,followup){
  await api('/drafts/'+encodeURIComponent(id)+'/schedule','PUT',{send_at:sendAt,followup_days:Number(followup)||null});
  await cachedDraftChange(id);
}
async function undoSend(id,draft){
  try{await api('/drafts/'+encodeURIComponent(id)+'/schedule','DELETE');}
  catch(error){toast(error.status===409?'Troppo tardi: il messaggio è già partito.':error.message);return;}
  await openDraft({...draft,scheduled:null});toast('Invio annullato. Il messaggio è di nuovo aperto.');
}
function showPalette(){
  const go=view=>()=>document.querySelector(`.nav-button[data-view="${view}"]`)?.click();
  const commands=[['Nuovo messaggio','C',()=>showCompose()],['Smart inbox','',go('inbox')],['Da leggere','',go('unread')],['Da fare','',go('todo')],
    ...(S.state.screener?.enabled?[['Nuovi mittenti','',go('screener')]]:[]),['Preferiti','',go('starred')],['Bozze','',go('drafts')],['Posta inviata','',go('sent')],['Per dopo','',go('snoozed')],['Archivio','',go('archive')],
    ['Chiedi a Milo','',()=>showAsk()],['Recap dell’inbox','',()=>openRecap()],['Gestisci i mittenti di newsletter','',()=>showNewsletterSenders()],
    ['Scarica posta ora','',()=>document.querySelector('[data-action="sync"]')?.click()],['Impostazioni','',()=>showSettings('accounts')],['Firme e risposte salvate','',()=>showSettings('compose')],
    ['Notifiche','',()=>showSettings('notifications')],['Scorciatoie da tastiera','?',()=>showShortcuts()],
    ['Tema chiaro','',()=>{applyTheme('light');savePreference('appearance',{theme:'light'}).catch(()=>{});}],['Tema scuro','',()=>{applyTheme('dark');savePreference('appearance',{theme:'dark'}).catch(()=>{});}],
    ...S.state.accounts.map(a=>[`Mostra solo ${a.name}`,'',()=>document.querySelector(`[data-account="${CSS.escape(a.id)}"]`)?.click()]),['Mostra tutti gli account','',()=>document.querySelector('[data-account=""]')?.click()]];
  S.palette={commands,items:commands,active:0};
  showModal('Comandi',`<input id="palette-input" class="palette-input" placeholder="Cerca un comando o scrivi per cercare nella posta" autocomplete="off" aria-label="Comando"><div id="palette-results" class="palette-results" role="listbox"></div>`);
  renderPalette();setTimeout(()=>$('#palette-input')?.focus(),0);
}
function renderPalette(){
  const box=$('#palette-results');if(!box||!S.palette)return;
  const term=($('#palette-input')?.value||'').trim().toLowerCase();
  const items=S.palette.commands.filter(([label])=>!term||label.toLowerCase().includes(term));
  if(term)items.push([`Cerca «${term}» nella posta`,'/',()=>{const input=$('#search-input');if(input){input.value=term;input.dispatchEvent(new Event('input',{bubbles:true}));}}]);
  S.palette.items=items;S.palette.active=Math.min(S.palette.active,Math.max(0,items.length-1));
  box.innerHTML=items.map(([label,key],index)=>`<button class="palette-item ${index===S.palette.active?'active':''}" data-palette="${index}" role="option" aria-selected="${index===S.palette.active}"><span>${esc(label)}</span>${key?`<kbd>${esc(key)}</kbd>`:''}</button>`).join('');
  box.querySelector('.active')?.scrollIntoView({block:'nearest'});
}
function runPalette(index){const item=S.palette?.items[index];if(!item)return;S.palette=null;closeModal();item[2]();}
function showShortcuts(){
  const rows=[['C','Nuovo messaggio'],['/','Cerca'],['Ctrl+K','Comandi'],['J / ↓','Conversazione successiva'],['K / ↑','Conversazione precedente'],['R','Rispondi'],['A','Rispondi a tutti'],['F','Inoltra'],['E','Archivia'],['U','Segna come letta o da leggere'],['P / S','Preferito'],['# / Canc','Elimina'],['X','Seleziona per azioni multiple'],['Ctrl+clic, Maiusc+clic','Seleziona più conversazioni'],['Esc','Chiudi o annulla la selezione'],['?','Questo elenco']];
  showModal('Scorciatoie da tastiera',`<div class="shortcut-list">${rows.map(([key,label])=>`<div><kbd>${esc(key)}</kbd><span>${esc(label)}</span></div>`).join('')}</div>`);
}
function showAsk(open=!$('#ask-dock .ask-panel')){
  const dock=$('#ask-dock');if(!dock)return;
  $('.ask-fab')?.classList.toggle('open',open);$('.ask-fab')?.setAttribute('aria-expanded',String(open));
  if(!open){dock.innerHTML='';return;}
  dock.innerHTML=`<section class="ask-panel" role="dialog" aria-label="Chiedi a Milo"><div class="modal-header"><h2>Chiedi a Milo</h2><button class="icon-button" data-action="close-ask" aria-label="Chiudi">${icon('close')}</button></div><div class="ask-body"><div id="ask-result" aria-live="polite"><p class="ask-hint">Fai una domanda sulla tua posta. Milo cerca le email pertinenti e risponde citandole.</p></div></div><form id="ask-form"><textarea name="question" required minlength="3" maxlength="500" rows="2" placeholder="Quando mi ha mandato Marco il contratto?" aria-label="Domanda"></textarea><div class="form-error" role="alert"></div><button class="primary" type="submit" aria-label="Chiedi">${icon('sent')}</button></form></section>`;
  setTimeout(()=>$('#ask-form textarea')?.focus(),0);
}
async function showNewsletterSenders(){
  showModal('Mittenti di newsletter',skeleton(6,'block','Carico i mittenti…'),true);
  try{
    const {senders}=await api('/senders/newsletters');if(!$('#overlay .modal'))return;
    $('#overlay .modal').querySelector('.skeleton-group')?.remove();
    $('#overlay .modal').insertAdjacentHTML('beforeend',senders.length?`<p>Disiscriviti da chi non leggi più e fai pulizia in un colpo solo.</p><div class="sender-list">${senders.map(s=>`<div class="sender-row" data-sender-row="${esc(s.email)}"><div><strong>${esc(s.name||s.email)}</strong><small>${esc(s.email)} · ${s.threads} conversazioni${s.unread?` · ${s.unread} da leggere`:''} · ultima ${esc(dateLabel(s.last,true))}</small></div><div class="sender-actions">${s.unsubscribed?'<span class="sender-done">Disiscritto</span>':`<button class="secondary" data-unsubscribe-message="${esc(s.sample_id)}">Disiscriviti</button>`}<button class="secondary" data-sender-bulk="archive" data-sender="${esc(s.email)}" ${s.inbox?'':'disabled'}>Archivia tutto</button><button class="secondary danger" data-sender-bulk="trash" data-sender="${esc(s.email)}">Elimina tutto</button></div></div>`).join('')}</div>`:emptyMarkup('filter','Nessuna newsletter.','Le email riconosciute come newsletter appariranno qui raggruppate per mittente.'));
  }catch(error){closeModal();toast(error.message);}
}
async function unsubscribeFrom(messageId,button){
  if(button){button.disabled=true;button.classList.add('is-loading');}
  try{
    const result=await api('/messages/'+encodeURIComponent(messageId)+'/unsubscribe','POST');
    if(result.method==='link'){window.open(result.url,'_blank','noopener,noreferrer');toast('Ho aperto la pagina di disiscrizione del mittente.');}
    else toast(result.method==='email'?'Richiesta di disiscrizione inviata via email.':'Disiscrizione completata.');
    if(button)button.outerHTML='<span class="sender-done">Disiscritto</span>';
  }finally{if(button?.isConnected){button.disabled=false;button.classList.remove('is-loading');}}
}
async function startReply(all=false,body=''){
  const source=S.thread.findLast(message=>!message.sent)||S.selected;if(!source)return;
  const version=S.readerVersion,m=await recipientContext(source);
  if(version===S.readerVersion)showCompose({account_id:m.account_id,...replyRecipients(m,all),mode:all?'reply_all':'reply',subject:'Re: '+subjectCore(m.subject),reply_to_id:m.id,body});
}
function replyRecipients(message,all=false){
  const mine=new Set(S.state.accounts.map(a=>a.email.toLowerCase())),seen=new Set(mine);
  const unique=addresses=>addresses.filter(address=>{const email=address.email?.trim();if(!email||!email.includes('@')||seen.has(email.toLowerCase()))return false;seen.add(email.toLowerCase());return true;}).map(address=>address.email);
  const primary=message.sent?(message.to_addresses||[]):message.reply_to_addresses?.length?message.reply_to_addresses:[{email:message.sender_email}];
  const to=unique(all?[...primary,...(message.to_addresses||[])]:primary);
  const cc=all?unique(message.cc_addresses||[]):[];
  return {to:to.join(', '),cc:cc.join(', ')};
}
document.addEventListener('toggle',event=>{const details=event.target;if(details.matches?.('.thread-message')&&details.open){const item=S.thread.find(m=>m.id===details.dataset.threadMessage);if(item?.body_loaded)displayBody(item);else if(item)ensureBody(item.id).catch(()=>{});}},true);
document.addEventListener('click', async event => {
  const target=event.target.closest('button,a'); if(!target) return;
  try {
      if(target.dataset.copyCode){navigator.clipboard?.writeText(target.dataset.copyCode).then(()=>toast('Codice copiato negli appunti.')).catch(()=>toast('Copia non riuscita: seleziona il codice e copialo a mano.'));return;}
    if(target.dataset.recipient!=null){acceptRecipient(Number(target.dataset.recipient));return;}
    if(target.dataset.view) {
      if(S.compose)closeCompose().catch(error=>toast(error.message));
      S.view=target.dataset.view; S.category=''; S.selected=null; S.menu=false; S.todoMulti.clear();
      S.loadingList=true;renderShell();await refresh(true,true);renderList();return;
    }
    if('category' in target.dataset) { if(S.compose)closeCompose().catch(error=>toast(error.message));S.category=target.dataset.category; S.selected=null; S.loadingList=true;renderShell();await refresh(true,true);renderList();return; }
    if('account' in target.dataset) { if(S.compose)closeCompose().catch(error=>toast(error.message));S.account=target.dataset.account;S.menu=false;S.readerVersion++;S.readerAnchor=null;S.selected=null;S.thread=[];S.loadingList=true;renderShell();await refresh(true,true);renderList();return; }
    if((event.ctrlKey||event.metaKey||event.shiftKey)&&target.closest('.todo-row')){const id=target.closest('.todo-row').querySelector('[data-todo-done]')?.dataset.todoDone;if(id){toggleTodo(id,event.shiftKey);return;}}
    if(target.dataset.message&&target.classList.contains('message-row')&&(event.ctrlKey||event.metaKey||event.shiftKey)){toggleMulti(target.dataset.message,event.shiftKey);return;}
    if(target.dataset.message) { if(S.compose)closeCompose().catch(error=>toast(error.message));await selectMessage(target.dataset.message); return; }
    if(target.dataset.bulk){await bulkMutate(target.dataset.bulk);return;}
    if(target.dataset.palette){runPalette(Number(target.dataset.palette));return;}
    if(target.dataset.acceptTodo){
      const id=target.dataset.acceptTodo,text=target.dataset.todoText;target.disabled=true;
      try{
        const todo=await api('/messages/'+encodeURIComponent(id)+'/todos','POST',{text});
        const message=S.thread.find(message=>message.id===id);
        if(message)message.todos=[...(message.todos||[]).filter(item=>item.text!==text),todo];
        if(S.selected?.id===id)S.selected.todos=message?.todos||[todo];
        renderReading();toast('Aggiunto ai da fare.');await revalidateView();
      }catch(error){target.disabled=false;throw error;}
      return;
    }
    if(target.dataset.todoDone){
      const id=target.dataset.todoDone;S.todoMulti.delete(id);S.todos=(S.todos||[]).filter(t=>t.id!==id);S.state.counts.todo=Math.max(0,(S.state.counts.todo||1)-1);renderList();renderChrome();
      try{await api('/todos/'+encodeURIComponent(id),'PATCH',{done:true});}catch(error){revalidateView();throw error;}
      toast('Fatto.',{label:'Annulla',run:()=>api('/todos/'+encodeURIComponent(id),'PATCH',{done:false}).then(()=>revalidateView()).catch(error=>toast(error.message))});return;
    }
    if(target.dataset.senderStatus){
      const email=target.dataset.sender,status=target.dataset.senderStatus;await api('/senders/'+encodeURIComponent(email),'PATCH',{status});
      S.screening=(S.screening||[]).filter(item=>item.email!==email);if(S.state.screener)S.state.screener.pending=(S.state.screener.pending||[]).filter(item=>item!==email);
      S.state.counts.screener=Math.max(0,(S.state.counts.screener||1)-1);renderList();renderChrome();
      toast(status==='approved'?'Mittente approvato: lo trovi nella Smart inbox.':'Mittente bloccato: le sue email vanno in archivio.');revalidateView();return;
    }
    if(target.dataset.senderBulk){
      const action=target.dataset.senderBulk;target.disabled=true;
      const result=await api('/senders/'+encodeURIComponent(target.dataset.sender)+'/action','POST',{action});
      if(action==='trash')target.closest('.sender-row')?.remove();
      toast(`${result.conversations} ${result.conversations===1?'conversazione':'conversazioni'} ${action==='trash'?'nel cestino':'archiviate'}. Milo sincronizza in background.`);revalidateView();return;
    }
    if(target.dataset.unsubscribeMessage){await unsubscribeFrom(target.dataset.unsubscribeMessage,target);return;}
    if(target.dataset.quickReply){const peer=S.thread.findLast(message=>!message.sent)||S.selected;await startReply(false,S.suggestions.get(peer?.id)?.[Number(target.dataset.quickReply)]||'');return;}
    if(target.dataset.previewMessage){
      const url=`/api/messages/${encodeURIComponent(target.dataset.previewMessage)}/attachments/${encodeURIComponent(target.dataset.previewIndex)}`,name=target.dataset.previewName,pdf=target.dataset.previewType==='application/pdf';
      showModal(name,`<div class="attachment-preview">${pdf?`<iframe src="${url}?preview=true" title="${esc(name)}"></iframe>`:`<img src="${url}" alt="${esc(name)}">`}</div><div class="form-actions"><a class="secondary" href="${url}" download="${esc(name)}">${icon('download')}Scarica</a></div>`,true);return;
    }
    if(target.dataset.deleteTemplate){
      const templates=(S.state.templates||[]).filter((_,index)=>index!==Number(target.dataset.deleteTemplate));
      S.state.templates=(await api('/settings/templates','PUT',{templates})).templates;showSettings('compose');return;
    }
    if(target.dataset.removeAccount){
      const a=S.state.accounts.find(account=>account.id===target.dataset.removeAccount);if(!a)return;
      showModal('Rimuovere l’account?',`<p>Milo smette di sincronizzare <strong>${esc(a.email)}</strong> e cancella dal tuo archivio le sue email, le bozze e le cose da fare collegate. La posta resta intatta sul provider: puoi ricollegare la casella quando vuoi.</p><div class="form-actions"><button class="secondary" data-action="close-modal">Annulla</button><button class="primary danger-solid" data-confirm-remove="${esc(a.id)}">Rimuovi account</button></div>`);return;
    }
    if(target.dataset.confirmRemove){
      const id=target.dataset.confirmRemove;target.disabled=true;await api('/accounts/'+encodeURIComponent(id),'DELETE');
      for(const key of replica.keys())if(replica.find(key)?.account_id===id)replica.remove(key);
      S.state.accounts=S.state.accounts.filter(a=>a.id!==id);if(S.account===id)S.account='';
      if(S.selected?.account_id===id){S.selected=null;S.thread=[];S.readerAnchor=null;S.readerVersion++;}
      closeModal();renderShell();await refresh();toast('Account rimosso. Milo libera lo spazio in background.');return;
    }
    if(target.dataset.confirmBlock){
      await api('/senders/'+encodeURIComponent(target.dataset.confirmBlock),'PATCH',{status:'blocked'});closeModal();
      S.selected=null;S.thread=[];S.readerAnchor=null;S.readerVersion++;$('.shell')?.classList.remove('has-selection');renderReading();
      toast('Mittente bloccato: le sue email vanno in archivio, anche quelle future.');await revalidateView();return;
    }
    if(target.dataset.scheduleAt){
      const at=Number(target.dataset.scheduleAt);await scheduleDraft(S.scheduling.id,at,S.scheduling.followup);S.scheduling=null;closeModal();
      toast('Invio programmato per '+dateLabel(at,true)+'.');await refresh();renderList();return;
    }
    if(target.dataset.downloadBody){await ensureBody(target.dataset.downloadBody);return;}
    if(target.dataset.draft) { await openDraft(S.drafts.find(d=>d.id===target.dataset.draft)); return; }
    if(target.dataset.editAccount) { showAccountSettings(target.dataset.editAccount);return; }
    if(target.dataset.settingsTab) { showSettings(target.dataset.settingsTab); return; }
    if(target.dataset.deleteRule) { await api('/rules/'+target.dataset.deleteRule,'DELETE');await refresh();showSettings('rules');renderList();return; }
    if(target.dataset.recapMessage) { closeModal();await selectMessage(target.dataset.recapMessage);return; }
    const action=target.dataset.action;
    if(['recap','analyze','ai-reply'].includes(action)) { await runAI(action,target);return; }
    if(action==='palette'){showPalette();return;}
    if(action==='ask'){showAsk();return;}
    if(action==='close-ask'){showAsk(false);return;}
    if(action==='select-todos'){const items=S.todos||[];const all=items.length>0&&items.every(todo=>S.todoMulti.has(todo.id));S.todoMulti=all?new Set():new Set(items.map(todo=>todo.id));renderList();return;}
    if(action==='clear-todos'){S.todoMulti.clear();renderList();return;}
    if(action==='complete-todos'){await completeTodos(S.todoMulti);return;}
    if(action==='newsletter-senders'){await showNewsletterSenders();return;}
    if(action==='unsubscribe'){
      await unsubscribeFrom(target.dataset.messageId,null);
      S.thread=S.thread.map(message=>message.id===target.dataset.messageId?{...message,unsubscribe:null}:message);renderReading();return;
    }
    if(action==='vip'){
      const email=target.dataset.sender,vip=!(S.state.vips||[]).includes(email);await api('/senders/'+encodeURIComponent(email),'PATCH',{vip});
      S.state.vips=vip?[...(S.state.vips||[]),email]:(S.state.vips||[]).filter(item=>item!==email);renderReading();
      toast(vip?'Mittente VIP: ti avviso sempre quando scrive.':'Mittente rimosso dai VIP.');return;
    }
    if(action==='block-sender'){
      showModal('Bloccare il mittente?',`<p>Le email di <strong>${esc(target.dataset.sender)}</strong> vengono archiviate, anche quelle che arriveranno. Puoi sempre ritrovarle in Archivio.</p><div class="form-actions"><button class="secondary" data-action="close-modal">Annulla</button><button class="primary danger-solid" data-confirm-block="${esc(target.dataset.sender)}">Blocca</button></div>`);return;
    }
    if(action==='suggest'){
      if(S.status.demo){toast('Le funzioni AI si attivano sulla tua posta reale.');return;}
      const peer=S.thread.findLast(message=>!message.sent)||S.selected;S.suggesting=peer.id;renderReading();
      try{S.suggestions.set(peer.id,(await api('/messages/'+encodeURIComponent(peer.id)+'/suggestions','POST')).replies);}
      finally{S.suggesting=null;renderReading();}
      return;
    }
    if(action==='schedule-send'){
      const draft=captureCompose();if(!draft)return;
      if(!String(draft.to||'').trim()&&!String(draft.cc||'').trim())throw new Error('Inserisci almeno un destinatario.');
      const id=await saveCompose();await persistDraft(draft);removeComposer();S.scheduling={id,followup:draft.followup_days};
      showModal('Quando lo invio?',`<p>Il messaggio resta nelle bozze fino all’invio. Aprendolo annulli la programmazione.</p><div class="schedule-options">${scheduleOptions().map(([date,label])=>`<button class="secondary" data-schedule-at="${date.getTime()/1000}"><span>${esc(label)}</span><small>${esc(date.toLocaleString('it-IT',{weekday:'short',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}))}</small></button>`).join('')}</div><form id="schedule-form"><label class="field"><span>Oppure scegli data e ora</span><input type="datetime-local" name="at" required></label><div class="form-error" role="alert"></div><div class="form-actions"><button class="primary" type="submit">${icon('clock')}Programma</button></div></form>`);return;
    }
    if(action==='settings') showSettings('accounts');
    if(action==='settings-ai') showSettings('ai');
    if(action==='add-account') showAccountForm();
    if(action==='imap-account') showIMAPForm();
    if(action==='google-connect') { target.disabled=true;try { const result=await api('/oauth/google/start','POST',target.dataset.reconnectAccount?{account_id:target.dataset.reconnectAccount}:undefined);location.assign(result.url); } catch(error) { target.disabled=false;throw error; } }
    if(action==='compose') showCompose();
    if(action==='menu') { S.menu=!S.menu;$('.shell').classList.toggle('menu-open',S.menu); }
    if(action==='back') { if(S.compose)closeCompose().catch(error=>toast(error.message));S.readerVersion++;S.readerAnchor=null;S.selected=null;$('.shell').classList.remove('has-selection');renderList();renderReading(); }
    if(action==='pin') await mutate({pinned:!S.selected.pinned});
    if(action==='trash') await mutate({},true);
    if(action==='load-images'){S.images=true;S.loadingMessage=true;renderReading();await loadThread(S.readerAnchor);}
    if(action==='star') await mutate({starred:!S.selected.starred});
    if(action==='read') await mutate({read:!S.selected.read});
    if(action==='archive') { await mutate({archived:!S.selected.archived});toast('Modifica salvata. Milo la sincronizza con il provider.'); }
    if(action==='snooze') showModal('Un momento migliore.',`<p>La conversazione torna nella tua inbox quando arriva il momento.</p><div class="form-actions"><button class="secondary" data-snooze="${Date.now()/1000+3600}">Tra un’ora</button><button class="primary" data-snooze="${Date.now()/1000+86400}">Domani</button></div>`);
    if(target.dataset.snooze) { await mutate({snoozed_until:Number(target.dataset.snooze)});closeModal();toast('Email messa da parte.'); }
    if(action==='reply'||action==='reply-all') {target.disabled=true;target.classList.add('is-loading');try{await startReply(action==='reply-all');}finally{target.disabled=false;target.classList.remove('is-loading');}}
    if(action==='forward') { const m=await ensureBody(S.selected.id);if(!m)return;showCompose({account_id:m.account_id,mode:'forward',context_message_id:m.id,subject:'Fwd: '+subjectCore(m.subject),body:`\n\n---------- Messaggio inoltrato ----------\nDa: ${m.sender} <${m.sender_email}>\nOggetto: ${m.subject}\n\n${m.body}`}); }
    if(action==='save-draft') { if(await saveCompose()) { await refresh();renderList();toast('Bozza salvata nel tuo archivio.'); } }
    if(action==='attach-file')target.closest('#compose-form')?.querySelector('.attach-input')?.click();
    if(action==='remove-attachment')await removeAttachment(target.dataset.attachmentId);
    if(action==='delete-draft')await discardCompose();
    if(action==='close-compose')await closeCompose();
    if(action==='close-modal'){if($('#overlay #compose-form'))await closeCompose();else closeModal();await refresh();renderList();}
    if(action==='sync') {
      downloadMail().catch(error=>toast(error.message));
      await deviceCache.retryOperations();S.queueErrors.clear();queueRetryAt=0;flushClientQueue().catch(()=>{});
    }
    if(action==='retry-login') { await boot(); }
    if(action==='logout') { await api('/logout','POST');replica.clear();S.optimistic.clear();S.pendingSettings.clear();S.queueErrors.clear();await deviceCache.clear();S.status.authenticated=false;S.selected=null;S.messages=[];renderLogin(); }
  } catch(error) { toast(error.message); }
});

document.addEventListener('submit', async event => {
  event.preventDefault(); const form=event.target;
  const button=form.querySelector('button[type="submit"]'); if(button){button.disabled=true;button.classList.add('is-loading');}
  const errorBox=form.querySelector('.form-error');if(errorBox) errorBox.textContent='';
  try {
    const data=Object.fromEntries(new FormData(form));
    if(form.id==='login-form') {
      await api(S.status.initialized?'/login':'/setup','POST',data);S.status=await api('/status');S.loadingList=true;renderShell();await refresh(false,true);renderList();
    }
    if(form.id==='google-config-form') {
      const file=form.elements.credentials.files[0];
      if(!file || file.size>16000) throw new Error('Seleziona il JSON OAuth Google (massimo 16 KB).');
      let config;try { config=JSON.parse(await file.text()); } catch { throw new Error('Il file non contiene un JSON valido.'); }
      await api('/settings/google','PUT',config);await revalidateView();showAccountForm();toast('Google configurato. Ora collega la tua casella.');
    }
    if(form.id==='account-form') {
      data.imap_port=Number(data.imap_port);data.smtp_port=Number(data.smtp_port);
      await api('/accounts','POST',data);closeModal();await revalidateView();renderShell();paintLocal();toast('Account salvato. La prima sincronizzazione è in corso.');
    }
    if(form.id==='account-settings-form') {
      data.enabled=form.elements.enabled.checked;
      if(form.elements.password) {
        if(!data.password) delete data.password;
        data.imap_port=Number(data.imap_port);data.smtp_port=Number(data.smtp_port);
      }
      const previous=S.state.accounts.find(a=>a.id===form.dataset.accountId),patch=Object.fromEntries(Object.entries(data).filter(([key,value])=>value!==previous?.[key]));
      if(Object.keys(patch).every(key=>['name','enabled','color'].includes(key)))await savePreference(null,patch,form.dataset.accountId);
      else await api('/accounts/'+encodeURIComponent(form.dataset.accountId),'PATCH',patch);
      S.loadingList=true;renderShell();await refresh(false,true);revalidateView().then(()=>{queueCatalogue();if(S.status.demo&&S.messages.length&&innerWidth>900)selectMessage(S.messages[0].id,false).catch(()=>{});});renderList();showSettings('accounts');toast('Account aggiornato su Milo.');
    }
    if(form.id==='identity-form') {
      data.aliases=data.aliases.split(',').map(name=>name.trim()).filter(Boolean);
      await savePreference('identity',data);await refresh();closeModal();toast('Identità salvata. Milo la userà nelle prossime risposte.');
    }
    if(form.id==='appearance-form'){applyTheme(data.theme);await savePreference('appearance',data);closeModal();toast('Aspetto salvato.');}
    if(form.id==='ai-form') {
      data.automatic=form.elements.automatic.checked;data.cloud_consent=form.elements.cloud_consent.checked;
      await savePreference('ai',data);await refresh();closeModal();toast('Preferenze AI salvate.');
    }
    if(form.id==='rule-form') { await api('/rules','POST',data);await revalidateView();showSettings('rules');renderList();toast('Filtro creato e applicato.'); }
    if(form.id==='compose-form') {
      const snapshot=captureCompose(),id=await saveCompose();if(!id)throw new Error('Scrivi prima il tuo messaggio.');
      if(!String(snapshot.to||'').trim()&&!String(snapshot.cc||'').trim())throw new Error('Inserisci almeno un destinatario.');
      await persistDraft(snapshot);await scheduleDraft(id,Date.now()/1000+UNDO_SECONDS,snapshot.followup_days);
      if(S.compose?.id===id)removeComposer();
      toast('Messaggio in partenza…',{label:'Annulla',duration:UNDO_SECONDS*1000,run:()=>undoSend(id,snapshot).catch(error=>toast(error.message))});
      setTimeout(async()=>{try{const {drafts}=await api('/drafts'),failed=drafts.find(d=>d.id===id&&d.scheduled?.error);
        if(failed)toast('Invio non riuscito: '+failed.scheduled.error);else if(!drafts.some(d=>d.id===id))toast('Messaggio inviato.');
        await refresh();if(S.readerAnchor)await loadThread(S.readerAnchor);renderList();}catch{}},(UNDO_SECONDS+7)*1000);
    }
    if(form.id==='schedule-form'){
      const at=new Date(data.at).getTime()/1000;if(!(at>Date.now()/1000))throw new Error('Scegli un momento futuro.');
      await scheduleDraft(S.scheduling.id,at,S.scheduling.followup);S.scheduling=null;closeModal();toast('Invio programmato per '+dateLabel(at,true)+'.');await refresh();renderList();
    }
    if(form.id==='ask-form'){
      const box=$('#ask-result'),question=String(data.question||'').trim();if(!question)return;
      box.querySelector('.ask-hint')?.remove();form.reset();
      const turn=document.createElement('div');turn.className='ask-turn';
      turn.innerHTML=`<p class="ask-question">${esc(question)}</p><div class="ask-answer">${skeleton(2,'block','Milo cerca nella tua posta…')}</div>`;
      box.append(turn);turn.scrollIntoView({block:'end'});
      const answer=turn.querySelector('.ask-answer');
      try{const result=await api('/ask','POST',{question});
        answer.innerHTML=`<p>${esc(result.answer)}</p>`;
        if(result.sources.length){const sources=document.createElement('div');sources.className='ask-sources';sources.innerHTML=result.sources.map(source=>`<button data-recap-message="${esc(source.id)}"><strong>${esc(source.sender||source.subject||'Email')}</strong><span>${esc(subjectCore(source.subject))}</span><time>${esc(dateLabel(source.date,true))}</time></button>`).join('');answer.after(sources);}
        turn.scrollIntoView({block:'end'});
      }catch(error){answer.innerHTML=`<p class="form-error">${esc(error.message)}</p>`;}
    }
    if(form.id==='signatures-form'){S.state.signatures=(await api('/settings/signatures','PUT',{signatures:data})).signatures;closeModal();toast('Firme salvate.');}
    if(form.id==='template-form'){S.state.templates=(await api('/settings/templates','PUT',{templates:[...(S.state.templates||[]),{name:data.name,body:data.body}]})).templates;showSettings('compose');toast('Risposta salvata.');}
    if(form.id==='notifications-form'){
      const previous=notificationSettings(),settings={mode:data.mode,morning:form.elements.morning.checked,since:previous.mode==='off'&&data.mode!=='off'?Date.now()/1000:previous.since||Date.now()/1000};
      if((settings.mode!=='off'||settings.morning)&&'Notification' in window&&Notification.permission==='default')await Notification.requestPermission();
      try{localStorage.setItem('milo-notify',JSON.stringify(settings));}catch{throw new Error('Questo dispositivo non può salvare la preferenza.');}
      closeModal();toast(settings.mode==='off'&&!settings.morning?'Notifiche disattivate.':'Notifiche attive su questo dispositivo.');
    }
    if(form.id==='screener-form'){
      const result=await api('/settings/screener','PUT',{enabled:form.elements.enabled.checked});S.state.screener={...result,pending:[]};
      closeModal();renderShell();await refresh();toast(result.enabled?'Da ora i nuovi mittenti aspettano in Nuovi mittenti.':'Filtro dei nuovi mittenti disattivato.');
    }
    if(form.id==='restore-form'){
      const file=form.elements.file.files[0];if(!file)throw new Error('Scegli un file di configurazione.');
      let backup;try{backup=JSON.parse(await file.text());}catch{throw new Error('Il file non contiene un JSON valido.');}
      const counts=await api('/backup/restore','POST',backup);closeModal();await revalidateView();renderShell();
      toast(`Ripristinati ${counts.messages} messaggi, ${counts.drafts} bozze, ${counts.todos} cose da fare e ${counts.settings} preferenze.`);
    }
  } catch(error) { if(errorBox) errorBox.textContent=error.message;else toast(error.message); }
  finally { S.analyzing=false;if(button){button.disabled=false;button.classList.remove('is-loading');} }
});

document.addEventListener('input', event => {
  if(event.target.closest('#compose-form')){const draft=captureCompose();rememberDraft(draft,false);clearTimeout(autosaveTimer);autosaveTimer=setTimeout(()=>persistDraft(draft).catch(()=>{if($('.draft-save-status'))$('.draft-save-status').textContent='Salvataggio in attesa. La copia resta nelle bozze.';}),700);}
  if(event.target.matches?.('#compose-form [name="to"], #compose-form [name="cc"]'))scheduleRecipients(event.target);
  if(event.target.matches?.('#compose-form [name="html"]'))scheduleComposeHtmlPreview(event.target);
  if(event.target.id==='palette-input'&&S.palette){S.palette.active=0;renderPalette();}
  if(event.target.id==='search-input') {
    S.search=event.target.value;clearTimeout(searchTimer);
    searchTimer=setTimeout(async()=>{try{await refresh(false,true);renderList();}catch(error){toast(error.message);}},200);
  }
  if(event.target.name==='email' && $('#account-form')) $('#account-form').elements.username.value=event.target.value;
});
// Drop files anywhere on the open composer.
document.addEventListener('dragover',event=>{const form=event.target.closest?.('#compose-form');if(form&&event.dataTransfer?.types.includes('Files')){event.preventDefault();form.classList.add('dropping');}});
document.addEventListener('dragleave',event=>{const form=event.target.closest?.('#compose-form');if(form&&!form.contains(event.relatedTarget))form.classList.remove('dropping');});
document.addEventListener('drop',event=>{const form=event.target.closest?.('#compose-form');if(!form||!event.dataTransfer?.files.length)return;event.preventDefault();form.classList.remove('dropping');attachFiles([...event.dataTransfer.files]);});
document.addEventListener('change', async event => {
  if(event.target.classList?.contains('attach-input')){const files=[...event.target.files];event.target.value='';await attachFiles(files);return;}
  if(event.target.name==='theme'&&$('#appearance-form'))applyTheme(event.target.value);
  if(event.target.classList?.contains('template-select')&&event.target.value!==''){
    const template=S.state.templates?.[Number(event.target.value)],field=$('#compose-form [name="body"]');event.target.value='';
    if(template&&field){const start=field.selectionStart??field.value.length;field.value=field.value.slice(0,start)+template.body+field.value.slice(field.selectionEnd??start);field.focus();field.setSelectionRange(start+template.body.length,start+template.body.length);field.dispatchEvent(new Event('input',{bubbles:true}));}
  }
  if(event.target.name==='account_id'&&event.target.closest('#compose-form')&&S.compose){
    const field=$('#compose-form [name="body"]'),before=S.state.signatures?.[S.compose.account_id],after=S.state.signatures?.[event.target.value];
    if(field&&before&&field.value.includes('-- \n'+before))field.value=field.value.replace('-- \n'+before,after?'-- \n'+after:'');
    else if(field&&after&&!field.value.includes('-- \n'+after))field.value=`${field.value}\n\n-- \n${after}`;
    S.compose.account_id=event.target.value;field?.dispatchEvent(new Event('input',{bubbles:true}));
  }
  if(event.target.id==='message-category') { try{await mutate({category:event.target.value});}catch(error){toast(error.message);} }
  if(event.target.id==='provider') {
    const form=$('#account-form'), provider=event.target.value;
    const presets={icloud:['imap.mail.me.com','smtp.mail.me.com',587,'starttls'],other:['','',465,'tls']};
    const [imap,smtp,port,security]=presets[provider];form.elements.imap_host.value=imap;form.elements.smtp_host.value=smtp;form.elements.smtp_port.value=port;form.elements.smtp_security.value=security;
    const notice=$('#provider-notice');
    if(provider==='other'&&!notice.dataset.icloudHtml){notice.dataset.icloudHtml=notice.innerHTML;}
    if(provider==='icloud'&&notice.dataset.icloudHtml){notice.innerHTML=notice.dataset.icloudHtml;}
    else if(provider==='other'){notice.innerHTML='Inserisci i parametri del tuo provider. IMAP usa TLS; SMTP può usare TLS oppure STARTTLS.';}
  }
});
document.addEventListener('focusin',event=>{
  if(event.target?.matches?.('#compose-form [name="to"], #compose-form [name="cc"]'))scheduleRecipients(event.target);
});
document.addEventListener('focusout',event=>{
  if(!event.target?.matches?.('#compose-form [name="to"], #compose-form [name="cc"]'))return;
  setTimeout(()=>{
    const active=document.activeElement;
    if(active===event.target||active?.closest?.('.recipient-list'))return;
    event.target.parentElement?.querySelector('.recipient-list')?.remove();
    event.target.setAttribute('aria-expanded','false');
    if(!active?.matches?.('#compose-form [name="to"], #compose-form [name="cc"]'))hideRecipients();
  },0);
});
document.addEventListener('mousedown',event=>{if(event.target.closest?.('.recipient-option'))event.preventDefault();});
async function handleKeydown(event) {
  if(event.defaultPrevented||event.isComposing)return;
  if(document.querySelector('.recipient-list')&&event.target?.closest?.('.recipient-field')){
    if(event.key==='ArrowDown'||event.key==='ArrowUp'){
      event.preventDefault();
      const count=recipientSuggest.items.length;
      recipientSuggest.active=(recipientSuggest.active+(event.key==='ArrowDown'?1:-1)+count)%count;
      paintRecipients(event.target,recipientSuggest.items);return;
    }
    if(event.key==='Enter'){event.preventDefault();acceptRecipient(recipientSuggest.active);return;}
    if(event.key==='Escape'){event.preventDefault();hideRecipients();return;}
  }
  if(event.target?.id==='palette-input'&&S.palette){
    if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();const count=Math.max(1,S.palette.items.length);S.palette.active=(S.palette.active+(event.key==='ArrowDown'?1:-1)+count)%count;renderPalette();return;}
    if(event.key==='Enter'){event.preventDefault();runPalette(S.palette.active);return;}
  }
  if((event.ctrlKey||event.metaKey)&&!event.altKey&&event.key.toLowerCase()==='k'&&S.status?.authenticated){event.preventDefault();showPalette();return;}
  if(event.target?.closest?.('#ask-form')&&event.key==='Enter'&&!event.shiftKey){event.preventDefault();event.target.closest('form').requestSubmit();return;}
  if(event.key==='Escape'&&$('#ask-dock .ask-panel')&&!$('#overlay').children.length){showAsk(false);return;}
  const editing=['INPUT','TEXTAREA','SELECT'].includes(event.target?.tagName)||event.target?.isContentEditable;
  if(event.key==='Escape') {
    try { if((S.multi.size||S.todoMulti.size)&&!$('#overlay').children.length&&!$('#compose-form')){S.multi.clear();S.todoMulti.clear();renderList();}else if($('#compose-form')){closeCompose().catch(error=>toast(error.message));}else closeModal();S.palette=null;S.menu=false;$('.shell')?.classList.remove('menu-open'); }
    catch(error) { toast(error.message); }
  }
  if(S.status?.authenticated && !editing && !$('#overlay').children.length && !$('#compose-form') && !event.ctrlKey && !event.metaKey && !event.altKey && !event.repeat) {
    const key=event.key.toLowerCase();
    if(key==='/') { event.preventDefault();$('#search-input')?.focus(); }
    if(key==='c') { event.preventDefault();showCompose(); }
    if(key==='?'){event.preventDefault();showShortcuts();return;}
    if(key==='x'&&S.selected){event.preventDefault();const row=S.messages.find(m=>threadKey(m)===threadKey(S.selected));if(row)toggleMulti(row.id);return;}
    if(S.multi.size&&(key==='e'||key==='#'||key==='delete'||key==='backspace')){event.preventDefault();await bulkMutate(key==='e'?'archive':'trash');return;}
    if(key==='j'||key==='k'||key==='arrowdown'||key==='arrowup') {
      event.preventDefault();
      const list=S.view==='drafts'?S.drafts:S.messages;
      if(!list.length)return;
      const currentIndex=S.selected?list.findIndex(m=>threadKey(m)===(S.selected?threadKey(S.selected):'')):-1;
      let nextIndex;
      const down=key==='arrowdown'||key==='j';
      if(down) nextIndex=currentIndex+1>=list.length?0:currentIndex+1;
      else nextIndex=currentIndex<=0?list.length-1:currentIndex-1;
      if(currentIndex===-1) nextIndex=down?0:list.length-1;
      const target=list[nextIndex];
      if(target){selectMessage(target.id,false).catch(()=>{});document.querySelector(`[data-message="${target.id}"]`)?.scrollIntoView({block:'nearest',behavior:'smooth'});}
    }
    if(S.selected) {
      try {
        if(key==='e') { event.preventDefault();await mutate({archived:true}); }
        if(key==='backspace'||key==='delete'||key==='#') { event.preventDefault();await mutate({},true); }
        if(key==='p'||key==='s') { event.preventDefault();await mutate({starred:!S.selected.starred}); }
        if(key==='u') { event.preventDefault();await mutate({read:!S.selected.read}); }
        if(key==='r'||key==='a') { event.preventDefault();await startReply(key==='a'); }
        if(key==='f') { event.preventDefault();$('[data-action="forward"]')?.click(); }
      } catch(error) { toast(error.message); }
    }
  }
  if(event.key==='Tab' && $('#overlay .modal')) {
    const controls=[...$('#overlay .modal').querySelectorAll('button,input,textarea,select,a[href]')].filter(el=>!el.disabled);
    const first=controls[0],last=controls.at(-1);
    if(event.shiftKey && document.activeElement===first) { event.preventDefault();last.focus(); }
    if(!event.shiftKey && document.activeElement===last) { event.preventDefault();first.focus(); }
  }
}
document.addEventListener('keydown',handleKeydown);

let pendingMailto=null,pendingOpen=null;
// mailto: links handed over by the desktop launcher (#compose=mailto:...).
function parseMailto(value){
  const text=String(value||'');if(!/^mailto:/i.test(text))return null;
  const [target,query='']=text.slice(7).split('?');
  const params=new URLSearchParams(query.replace(/\+/g,'%2B')),field=name=>[...params].filter(([key])=>key.toLowerCase()===name).map(([,v])=>v);
  const decode=part=>{try{return decodeURIComponent(part);}catch{return part;}};
  const to=[decode(target),...field('to')].filter(Boolean).join(', ');
  return {to,cc:field('cc').join(', '),subject:field('subject')[0]||'',body:(field('body')[0]||'').replace(/\r\n/g,'\n')};
}
function openPendingMailto(){
  // Waits for the accounts list, which may arrive after the first refresh.
  const draft=parseMailto(pendingMailto);
  if(draft&&S.state?.accounts?.length){pendingMailto=null;showCompose(draft);}
  // A desktop notification click (#open=<message id>) shows that conversation.
  if(pendingOpen&&S.state?.accounts?.length){const id=pendingOpen;pendingOpen=null;selectMessage(id).catch(()=>toast('Questa email non è più disponibile.'));}
}
async function boot() {
  try {
    const oauth=new URLSearchParams(location.hash.slice(1));
    const oauthError=oauth.get('google_error'),connected=oauth.has('google_connected'),ownerToken=oauth.get('setup');
    pendingMailto=oauth.get('compose');pendingOpen=oauth.get('open');
    if(ownerToken || oauthError || connected || pendingMailto || pendingOpen) history.replaceState(null,'',location.pathname);
    await replica.init();
    const cachedStatus=await deviceCache.get('api:/status'),cachedState=await deviceCache.get('api:/state');
    for(const operation of await deviceCache.get('pending-operations')||[]){if(operation.error)S.queueErrors.set(operation.id,operation);replica.apply(operation);if(operation.kind==='setting')S.pendingSettings.set(operation.key,operation);else if(!operation.kind)S.optimistic.set(operation.key,{patch:{...S.optimistic.get(operation.key)?.patch,...operation.patch},deleted:operation.deleted,operationId:operation.id});}
    if(cachedStatus?.authenticated&&cachedState){
      S.status=cachedStatus;S.state=cachedState;S.online=navigator.onLine;applyState(cachedState);renderShell();downloadMail({automatic:true}).catch(()=>{});openPendingMailto();await refresh();
      api('/status').then(status=>{S.status=status;if(!status.authenticated)renderLogin();else{flushClientQueue().catch(()=>{});queueCatalogue();}}).catch(error=>{if(temporarilyUnavailable(error))recordServerError();});
      return;
    }
    try{S.status=await api('/status');}catch(error){if(!temporarilyUnavailable(error))throw error;if(!cachedStatus?.authenticated)throw error;S.status=cachedStatus;recordServerError();}

    if(!S.status.initialized&&!S.status.authenticated) {
      if(ownerToken) {
        try { await api('/setup/authorize','POST',{token:ownerToken}); }
        catch(error) { if(error.status!==403) throw error;toast(error.message); }
      }
      S.setupAuthorized=(await api('/setup/status')).authorized;
    }
    if(oauthError) toast(oauthError);
    if(connected) toast('Casella Google collegata. Sto sincronizzando la tua posta.');
    if(!S.status.authenticated) { renderLogin();return; }
    S.loadingList=true;renderShell();downloadMail({automatic:true}).catch(()=>{});await refresh(false,true);openPendingMailto();revalidateView().then(()=>{queueCatalogue();if(S.status.demo&&S.messages.length&&innerWidth>900)selectMessage(S.messages[0].id,false).catch(()=>{});});renderList();

  } catch(error) { $('#app').innerHTML=`<div class="empty" style="min-height:100vh">${icon('mail')}<h3>Milo non è raggiungibile.</h3><p>${esc(error.message)}</p></div>`; }
}
let queueTask,queueRetryAt=0;
function flushClientQueue(){
  if(queueTask)return queueTask;
  if(!S.online||!S.status?.authenticated||Date.now()<queueRetryAt)return Promise.resolve();
  queueTask=runClientQueue();queueTask.finally(async()=>{queueTask=null;const remaining=await deviceCache.get('pending-operations')||[];if(remaining.some(op=>!op.error&&(op.kind!=='draft_delete'||!S.draftWrites.has(op.message_id)))&&S.online&&Date.now()>=queueRetryAt)flushClientQueue().catch(()=>{});}).catch(()=>{});return queueTask;
}
async function runClientQueue(){
  try{
    for(const operation of await deviceCache.get('pending-operations')||[]){
      if(operation.error)continue;
      if(operation.kind==='draft_delete'&&S.draftWrites.has(operation.message_id))continue;
      try{
        if(operation.kind==='setting')await api(operation.path,operation.method,operation.body);
        else if(operation.kind==='draft_delete')await api('/drafts/'+encodeURIComponent(operation.message_id),'DELETE');
        else await api('/messages/'+encodeURIComponent(operation.message_id)+'/thread',operation.deleted?'DELETE':'PATCH',operation.deleted?undefined:operation.patch);
      }catch(error){
        if(error.status!==404||operation.kind==='setting'){if(temporarilyUnavailable(error)||error.status===401)throw error;await deviceCache.markFailed(operation.id,error.message);S.queueErrors.set(operation.id,{...operation,error:error.message});toast('Una modifica richiede attenzione: '+error.message);continue;}
        if(!operation.kind){const row=replica.find(operation.key);if(row){try{const newer=await api('/client/thread?'+new URLSearchParams({account:row.account_id,thread:row.thread_id||row.id}));await api('/messages/'+newer.message.id+'/thread',operation.deleted?'DELETE':'PATCH',operation.deleted?undefined:operation.patch);}catch(missing){if(missing.status!==404)throw missing;}}}
      }
      if(!S.status?.authenticated)return;
      replica.confirm(operation);
      if(!await replica.commit())throw new Error('Cache locale non disponibile. La sincronizzazione resterà in attesa.');
      await deviceCache.acknowledge(operation.id);
      if(S.optimistic.get(operation.key)?.operationId===operation.id)S.optimistic.delete(operation.key);
      if(S.pendingSettings.get(operation.key)?.id===operation.id)S.pendingSettings.delete(operation.key);
    }
    revalidateView();
  }catch(error){queueRetryAt=Date.now()+3000;if(!temporarilyUnavailable(error)&&S.status?.authenticated)toast(error.message);}
  finally{renderChrome();}
}
// Server-sent change notices make the list current at once, even in a hidden
// window; polling stays as a slower safety net while the stream is connected.
let events=null,eventsLive=false,eventTimer=null,lastEventRefresh=0,eventsRetryAt=0;
function connectEvents(){
  if(!S.status?.authenticated||S.status.demo||typeof EventSource==='undefined'){if(events){events.close();events=null;eventsLive=false;}return;}
  if(events||Date.now()<eventsRetryAt)return;
  events=new EventSource('/api/events');
  events.addEventListener('hello',()=>{const missed=!eventsLive&&lastEventRefresh;eventsLive=true;if(missed)eventRefresh();});
  events.addEventListener('change',()=>{eventsLive=true;eventRefresh();});
  // The browser retries dropped streams itself; a refused one (older server, 5xx) waits a minute.
  events.onerror=()=>{eventsLive=false;if(events?.readyState===EventSource.CLOSED){events=null;eventsRetryAt=Date.now()+60000;}};
}
function eventRefresh(){
  if(eventTimer)return;
  eventTimer=setTimeout(()=>{eventTimer=null;lastEventRefresh=Date.now();lastPollRefresh=Date.now();
    refresh().catch(()=>{});flushClientQueue().catch(()=>{});},Math.max(0,1500-(Date.now()-lastEventRefresh)));
}
let lastHiddenRefresh=0,lastPollRefresh=0;
async function poll(){
  try{
    connectEvents();
    // A hidden window (another workspace, minimized) keeps the list current every 30 seconds.
    if(S.status?.authenticated&&document.hidden&&Date.now()-lastHiddenRefresh>(eventsLive?120000:30000)){
      lastHiddenRefresh=Date.now();await refresh().catch(()=>{});flushClientQueue().catch(()=>{});
    }
    if(S.status?.authenticated&&!document.hidden){
      if(!eventsLive||Date.now()-lastPollRefresh>30000){lastPollRefresh=Date.now();await refresh().catch(()=>{});}
      flushClientQueue().catch(()=>{});queueCatalogue();
      if(Date.now()-lastWarm>120000)warmRecentBodies();
      maybeMorningRecap();
      if(S.recapOpen&&S.recapSignature!==JSON.stringify(S.state.recap))api('/recap').then(result=>{if(S.recapOpen)showRecap(result);}).catch(()=>{});
      for(const draft of S.pendingDrafts.values())if(!S.draftWrites.has(draft.id)&&S.compose?.id!==draft.id)persistDraft(draft).catch(()=>{});
      if(S.readerAnchor&&S.threadSync.phase==='downloading'&&!S.loadingMessage)loadThread(S.readerAnchor).catch(()=>{});
    }
  }finally{
    // The next tick is unconditional: one failed pass must not stop the
    // safety-net refresh for the rest of a long-lived window session.
    setTimeout(poll,3000);
  }
}
setTimeout(poll,1500);
function downloadMailOnEntry(){downloadMail({automatic:true}).catch(()=>{});}
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&S.status?.authenticated){downloadMailOnEntry();revalidateView();flushClientQueue().catch(()=>{});}});
addEventListener('focus',()=>{if(S.status?.authenticated){downloadMailOnEntry();revalidateView();flushClientQueue().catch(()=>{});}});
addEventListener('milo-download-mail',downloadMailOnEntry);
addEventListener('online',()=>{updateOnlineState();queueRetryAt=0;downloadMailOnEntry();flushClientQueue().catch(()=>{});revalidateView();queueCatalogue();});
addEventListener('offline',()=>{S.online=false;renderChrome();});
addEventListener('pagehide',()=>{const draft=captureCompose();if(draft)rememberDraft(draft);else storePendingDrafts();});
if('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js',{type:'module'}).catch(()=>{});
boot();
