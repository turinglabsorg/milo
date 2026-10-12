import {deviceCache} from './cache.js';
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
const icon = (name, extra = '') => `<svg class="icon ${extra}" viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[name] || paths.mail}"/></svg>`;
const googleIcon = () => '<svg class="google-mark" viewBox="0 0 48 48" aria-hidden="true"><path fill="#4285f4" d="M43.6 24.5c0-1.4-.1-2.8-.4-4.1H24v7.8h11a9.4 9.4 0 0 1-4.1 6.2v5.2h6.6c3.9-3.6 6.1-8.9 6.1-15.1z"/><path fill="#34a853" d="M24 44c5.5 0 10.1-1.8 13.5-4.9l-6.6-5.2c-1.8 1.2-4.1 1.9-6.9 1.9-5.3 0-9.8-3.6-11.4-8.4H5.8v5.3A20.4 20.4 0 0 0 24 44z"/><path fill="#fbbc05" d="M12.6 27.4a12.3 12.3 0 0 1 0-6.8v-5.3H5.8a20.4 20.4 0 0 0 0 17.4z"/><path fill="#ea4335" d="M24 12.2c3 0 5.7 1 7.8 3.1l5.9-5.9A19.8 19.8 0 0 0 24 4 20.4 20.4 0 0 0 5.8 15.3l6.8 5.3c1.6-4.8 6.1-8.4 11.4-8.4z"/></svg>';
const logo = () => '<div class="logo"><img src="/static/icon.svg" alt="">milo<small>MAIL</small></div>';
const S = {status:null, setupAuthorized:false, state:{accounts:[], counts:{}, ai:{}, sync:[]}, messages:[], selected:null, thread:[], threadSync:{}, readerAnchor:null, loadingMessage:false, loadingList:false, listVersion:0, readerVersion:0, optimistic:new Map(), view:'inbox', category:'', account:'', search:'', settingsTab:'accounts', menu:false, syncing:false, online:true, compose:null, theme:'system', images:false};
const categoryNames = {people:'Persone', updates:'Notifiche', newsletters:'Newsletter'};
const viewNames = {inbox:'Smart inbox', starred:'Preferiti', drafts:'Bozze', sent:'Posta inviata', snoozed:'Per dopo', archive:'Archivio'};
let toastTimer, searchTimer, autosaveTimer, localDraftTimer;
S.pendingDrafts=new Map();S.draftWrites=new Map();S.discardedDrafts=new Set();
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
function syncMarkup() {
  const active=(S.state.sync||[]).filter(p=>['connecting','downloading','applying'].includes(p.phase));
  const count=active.reduce((n,p)=>n+(p.downloaded||0),0);
  const pending=(S.state.pending||[]).reduce((n,p)=>n+p.count,0)+S.optimistic.size;
  const text=active.some(p=>p.phase==='downloading')?`Scarico messaggi · ${count} salvati`:active.some(p=>p.phase==='applying')?'Sincronizzo le modifiche':active.length||S.syncing?'Collegamento alla posta…':pending?`${pending} modifiche in sincronizzazione`:S.online?'Posta aggiornata':'Connessione interrotta';
  return `<span class="sync-status ${active.length||S.syncing?'working':''}" role="status">${icon(active.length||S.syncing?'refresh':'check')}<span>${esc(text)}</span></span>`;
}

const temporarilyUnavailable=error=>!error.status||error.status>=500||[408,429].includes(error.status);
async function api(path, method='GET', body) {
  let response;
  try { response = await fetch('/api' + path, {method, signal:AbortSignal.timeout(method==='GET'?12000:60000), credentials:'same-origin', headers:body ? {'Content-Type':'application/json'} : {}, body:body ? JSON.stringify(body) : undefined}); }
  catch { S.online=false; throw new Error('Connessione a Milo interrotta. I dati salvati restano sul servizio.'); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if ((response.status === 401 || response.status===404&&['/status','/state'].includes(path)) && S.status?.authenticated) { await deviceCache.clear(); S.status.authenticated=false; renderLogin(); }
    const message = Array.isArray(data.detail) ? data.detail.map(item => item.msg).join('; ') : data.detail;
    const error=new Error(message || 'Operazione non riuscita');error.status=response.status;if(temporarilyUnavailable(error))S.online=false;throw error;
  }
  S.online=true;
  if(method==='GET'&&(/^(?:\/status|\/state|\/recap|\/messages(?:[/?]|$)|\/drafts)/.test(path)))deviceCache.set('api:'+path,data).then(saved=>{if(!saved&&!S.cacheWarning){S.cacheWarning=true;toast('Cache locale non disponibile. I messaggi restano sul server, ma non saranno disponibili offline su questo dispositivo.');}});
  return data;
}

function toast(message) {
  clearTimeout(toastTimer); $('#toast').textContent=message; $('#toast').classList.add('visible');
  toastTimer=setTimeout(() => $('#toast').classList.remove('visible'), 5500);
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
  return `<div class="nav-label">Account</div>${S.state.accounts.map(a=>`<button class="account-button ${S.account===a.id?'active':''}" data-account="${esc(a.id)}"><span class="dot" style="background:${accountColor(a.id)};${a.enabled?'':'opacity:.4'}"></span>${esc(a.name)}${S.account===a.id?icon('check'):''}</button>`).join('')}<button class="account-button plus-account" data-action="add-account">${icon('plus')}Aggiungi account</button>`;
}
function renderChrome() {
  if($('#sync-status')) $('#sync-status').innerHTML=syncMarkup();
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
  const folders=[['inbox','inbox'],['starred','star'],['drafts','edit'],['sent','sent'],['snoozed','clock'],['archive','archive']];
  $('#app').innerHTML=`<main class="shell ${S.selected?'has-selection':''} ${S.menu?'menu-open':''}"><aside class="sidebar">${logo()}<button class="primary compose-button" data-action="compose">${icon('plus')}Nuovo messaggio</button><div class="nav-label">La tua posta</div><nav class="nav">${folders.map(([view,name])=>`<button class="nav-button ${S.view===view?'active':''}" data-view="${view}">${icon(name)}${viewNames[view]}${counts[view]?`<span class="count">${counts[view]}</span>`:''}</button>`).join('')}</nav><div class="account-section">${accountMarkup()}</div><div class="sidebar-bottom"><div class="sidebar-footer"><div class="user-avatar">${esc(initials(S.state.identity?.name || S.state.accounts[0]?.name || 'Tu'))}</div><span>${esc(S.state.identity?.name||'Il tuo spazio')}</span><button data-action="settings" aria-label="Impostazioni">${icon('settings')}</button></div>${S.status.demo?'<div class="demo-label">DEMO · messaggi fittizi</div>':''}</div></aside><header class="topbar"><button class="icon-button mobile-menu" data-action="menu" aria-label="Apri menu">${icon('menu')}</button><div class="breadcrumbs">Il tuo spazio ${icon('arrow')}<strong>${viewNames[S.view]}</strong></div><div class="top-tools"><div id="sync-status">${syncMarkup()}</div><label class="search">${icon('search')}<input id="search-input" placeholder="Cerca nella tua posta" value="${esc(S.search)}" aria-label="Cerca nella tua posta"><kbd>/</kbd></label><button class="icon-button ${S.syncing?'spinner':''}" data-action="sync" aria-label="Sincronizza" title="Sincronizza">${icon('refresh')}</button><span class="sync-indicator ${!S.online||S.state.accounts.some(a=>a.error)?'offline':''}" title="${S.online?'Servizio connesso':'Servizio non raggiungibile'}"></span><button class="icon-button" data-action="settings" aria-label="Impostazioni">${icon('settings')}</button></div></header><section class="list-panel" id="list-panel"></section><section class="reading-panel" id="reading-panel"></section></main>`;
  renderList(); renderReading();
}

function renderList() {
  if (!$('#list-panel')) return;
  const inbox = S.view==='inbox';
  const count = S.messages.length;
  $('#list-panel').innerHTML=`<div class="list-heading"><div class="eyebrow">${new Date().toLocaleDateString('it-IT',{weekday:'long',day:'numeric',month:'long'})}</div><div class="title-row"><h1>${viewNames[S.view]}</h1><span class="badge">${S.view==='drafts'?S.drafts?.length||0:count} ${S.view==='drafts'?'bozze':count===1?'conversazione':'conversazioni'}</span></div><p class="subheading">${inbox?`${S.state.counts.unread||0} email da leggere. Facciamo un po’ di spazio.`:({starred:'Le conversazioni a cui vuoi tornare.',drafts:'Le parole giuste, con i tuoi tempi.',sent:'I messaggi che hai inviato.',snoozed:'Al momento giusto, di nuovo nella tua inbox.',archive:'Tutto conservato, niente in mezzo.'}[S.view])}</p></div>${inbox?`<button class="recap-card" data-action="recap"><span class="recap-symbol">${icon('sparkle')}</span><span><strong>La tua inbox, in un minuto.</strong><p>${S.state.recap?.phase==='updating'?'Si aggiorna in background…':S.state.recap?.generated_at?'Aggiornato alle '+dateLabel(S.state.recap.generated_at):'Si aggiorna quando arriva nuova posta.'}</p></span>${icon('arrow')}</button><div class="tabs">${[['','Tutte'],['people','Persone'],['updates','Notifiche'],['newsletters','Newsletter']].map(([category,name])=>`<button class="tab ${S.category===category?'active':''}" data-category="${category}">${name}</button>`).join('')}</div>`:''}${!S.online?'<div class="offline-note">Sei offline. Mostro la posta salvata su questo dispositivo.</div>':''}${S.state.accounts.some(a=>a.error)?`<div class="error-banner">${esc(S.state.accounts.find(a=>a.error).error)} <button data-action="settings">Apri account</button></div>`:''}${S.state.pending?.some(p=>p.error)?'<div class="error-banner">Le modifiche sono salvate in Milo. La sincronizzazione con la casella verrà riprovata. <button data-action="settings">Dettagli</button></div>':''}<div id="message-list"></div>`;
  const container=$('#message-list');
  if (S.loadingList) { container.innerHTML=skeleton(9,'list','Carico le conversazioni…');return; }
  if (S.view==='drafts') {
    container.innerHTML=(S.drafts?.length?S.drafts.map(d=>`<button class="draft-row" data-draft="${esc(d.id)}"><small>${d.pending?'Salvataggio in attesa · ':''}${esc(d.to||'Nessun destinatario')}</small><strong>${esc(d.subject||'Senza oggetto')}</strong><p>${esc(d.body.slice(0,100))}</p></button>`).join(''):emptyMarkup('edit','Un pensiero da scrivere.','Le bozze salvate appariranno qui, anche sugli altri dispositivi.'));
    return;
  }
  if (!count) {
    container.innerHTML=emptyMarkup('inbox',S.state.accounts.length?'Un po’ di spazio.':'Cominciamo dalla tua posta.',S.state.accounts.length?'Qui non ci sono messaggi. Le email arriveranno con la sincronizzazione.':'Collega il tuo primo account. Al resto pensiamo insieme.',!S.state.accounts.length);
    return;
  }
  let lastDay='';
  container.innerHTML=S.messages.map(m=>{
    const day=m.pinned?'In evidenza':isToday(m.date)?'Oggi':new Date(m.date*1000).toLocaleDateString('it-IT',{day:'numeric',month:'long'});
    const heading=day!==lastDay?`<div class="day-heading">${esc(day)}<span class="right">${S.search?'Risultati di ricerca':'Le tue conversazioni'}</span></div>`:'';
    lastDay=day;
    return heading+`<button class="message-row ${m.read?'':'unread'} ${S.selected?.id===m.id?'selected':''}" data-message="${esc(m.id)}" style="--account-color:${accountColor(m.account_id)}">${avatar(m)}<span class="message-content"><span class="sender-line"><strong>${esc(m.sender)}</strong>${m.message_count>1?`<span class="thread-count">${m.message_count}</span>`:''}${!m.read?'<span class="unread-dot"></span>':''}<span class="row-markers"><span class="dot account-dot" title="${esc(S.state.accounts.find(a=>a.id===m.account_id)?.name||'Account')}"></span>${m.pinned?`<span class="row-pin" aria-label="Conversazione fissata" title="Fissata in alto">${icon('pin')}</span>`:''}${m.analyzed_count?`<span class="row-analysis" aria-label="${m.analyzed_count} messaggi analizzati" title="${m.analyzed_count} messaggi analizzati da Milo AI">${icon('sparkle')}</span>`:''}</span><time>${dateLabel(m.date)}</time></span><span class="row-subject">${esc(subjectCore(m.subject))}</span><span class="row-preview">${m.sent?'Tu: ':''}${esc(m.preview)}</span>${m.replied?`<span class="reply-badge">${icon('reply')}Hai risposto</span>`:''}</span>${m.starred?`<span class="row-star">${icon('star')}</span>`:''}</button>`;
  }).join('');
}
function emptyMarkup(symbol,title,description,add=false) {
  return `<div class="empty">${icon(symbol)}<h3>${esc(title)}</h3><p>${esc(description)}</p>${add?'<button class="primary" data-action="add-account">Collega un account</button>':''}</div>`;
}

function subjectCore(subject) {
  return String(subject||'').replace(/^\s*(?:(?:re|aw|sv|r|fw|fwd)(?:\[\d+\])?\s*:\s*)+/i,'').trim()||'Senza oggetto';
}
function quotedHTML(html) {
  const doc=new DOMParser().parseFromString(html,'text/html');
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
  if(!match||match.index===0)return `<div class="mail-body">${esc(text)}</div>`;
  return `<div class="mail-body">${esc(text.slice(0,match.index).trimEnd())}</div><details class="quoted-history"><summary>Mostra il testo citato</summary><div class="mail-body">${esc(text.slice(match.index))}</div></details>`;
}
function htmlDocument(html) {
  const images=S.images?"'self' https:":"'self'";
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="referrer" content="no-referrer"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src ${images}; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><style>html{color-scheme:light}body{margin:0;height:auto!important;font:15px/1.6 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#172033;overflow-wrap:anywhere}.milo-email-document{display:flow-root;padding:16px;box-sizing:border-box}img,table{max-width:100%!important}img{height:auto}pre{white-space:pre-wrap}a{color:#2563eb}table{border-collapse:collapse}.milo-quoted-history{margin:16px 0;border-top:1px solid #dfe7f2;padding-top:10px}.milo-quoted-history>summary{cursor:pointer;color:#64748b;font:13px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}.milo-quoted-history blockquote{margin-left:12px!important;padding-left:12px!important;border-left:2px solid #dfe7f2}.milo-quoted-history:not([open])>*:not(summary){display:none!important}</style></head><body><div class="milo-email-document">${quotedHTML(html)}</div></body></html>`;
}
function fitFrames(root=document) {
  root.querySelectorAll('.email-html').forEach(frame=>{
    if(frame.dataset.fitted)return;frame.dataset.fitted='true';
    frame.addEventListener('load',()=>{
      const doc=frame.contentDocument,content=doc?.querySelector('.milo-email-document');
      if(!content)return;
      const fit=()=>{if(!frame.getClientRects().length)return;const height=Math.max(48,Math.ceil(content.getBoundingClientRect().height));if(frame.style.height!==height+'px')frame.style.height=height+'px';};
      fit();const observer=new ResizeObserver(fit);observer.observe(content);
      doc.addEventListener('toggle',fit,true);doc.addEventListener('load',fit,true);
      frame.closest('.thread-message')?.addEventListener('toggle',fit);
      frame._observer=observer;
    },{once:true});
  });
}
function renderReading() {
  const panel=$('#reading-panel');if(!panel)return;
  const editor=$('#inline-composer #compose-form'),active=document.activeElement;
  const caret=active?.tagName==='TEXTAREA'?[active.selectionStart,active.selectionEnd]:null;
  if(editor)captureCompose();
  if(editor)editor.remove();
  panel.querySelectorAll('.email-html').forEach(frame=>frame._observer?.disconnect());
  const m=S.selected;
  if (!m) { panel.innerHTML=emptyMarkup('mail','Spazio per una conversazione.','Scegli un’email e prenditi il tempo per leggerla.');return; }
  const open=new Set([...panel.querySelectorAll('details[open]')].map(el=>el.dataset.threadMessage));
  const messages=S.thread.length?S.thread:[m];
  const analysis=S.thread.findLast(message=>message.analysis)?.analysis||m.analysis;
  const downloading=S.loadingMessage||S.threadSync.phase==='downloading';
  panel.innerHTML=`<div class="reading-toolbar"><button class="icon-button back-button" data-action="back" aria-label="Torna alla lista">${icon('back')}</button><button class="icon-button ${m.pinned?'is-active':''}" data-action="pin" aria-label="${m.pinned?'Rimuovi pin':'Fissa in alto'}" title="${m.pinned?'Rimuovi pin':'Fissa in alto'}">${icon('pin')}</button><button class="icon-button" data-action="archive" aria-label="${m.archived?'Sposta in inbox':'Archivia'}" title="Archivia">${icon('archive')}</button><button class="icon-button" data-action="trash" aria-label="Elimina conversazione" title="Sposta nel cestino">${icon('trash')}</button><button class="icon-button" data-action="snooze" aria-label="Posticipa" title="Posticipa">${icon('clock')}</button><button class="icon-button" data-action="read" aria-label="${m.read?'Segna da leggere':'Segna come letta'}">${icon('mail')}</button><button class="icon-button ${m.starred?'is-active':''}" data-action="star" aria-label="${m.starred?'Rimuovi dai preferiti':'Aggiungi ai preferiti'}">${icon('star')}</button><div class="right"><span class="dot" style="background:${accountColor(m.account_id)}"></span>${esc(S.state.accounts.find(a=>a.id===m.account_id)?.name||'Account')}</div></div><article class="mail-content"><span class="mail-label">${icon('people')}${categoryNames[m.category]||'Email'}</span><select class="category-select" id="message-category" aria-label="Categoria della email">${Object.entries(categoryNames).map(([key,name])=>`<option value="${key}" ${key===m.category?'selected':''}>${name}</option>`).join('')}</select><h2>${esc(subjectCore(m.subject))}</h2>${downloading?`<div class="download-status" role="status">${icon('refresh','spinner')}Scarico la conversazione e le tue risposte…</div>`:''}${S.threadSync.error?`<div class="error-banner">${esc(S.threadSync.error)}</div>`:''}${S.loadingMessage?skeleton(7,'reader','Carico il messaggio…'):`<section class="ai-summary"><div class="ai-summary-title">${icon('sparkle')}${analysis?'Il punto, secondo Milo':'Milo AI'}<button data-action="analyze">${analysis?'Rianalizza':'Analizza'}${icon('arrow')}</button></div><div id="analysis-content">${S.analyzing?skeleton(3,'block','Analisi in corso…'):`<p>${analysis?esc(analysis.summary):'Sintesi, cose da fare e priorità della conversazione.'}</p>${analysis?.action_items?.length?`<ul>${analysis.action_items.map(item=>`<li>${esc(item)}</li>`).join('')}</ul>`:''}`}</div></section><div class="thread-messages">${messages.map((item,index)=>`<details class="thread-message ${item.sent?'sent-message':''}" data-thread-message="${esc(item.id)}" ${index===messages.length-1||open.has(item.id)?'open':''}><summary><span class="sender-detail">${avatar(item)}<span><strong>${item.sent?'Tu':esc(item.sender)}</strong><span class="address">${esc(item.sender_email)}</span><small>${item.sent?'Risposta inviata':esc(item.preview.slice(0,90))}</small></span><time>${dateLabel(item.date,true)}</time></span></summary><div class="thread-message-body" data-body-for="${esc(item.id)}">${index===messages.length-1||open.has(item.id)?bodyMarkup(item):''}</div></details>`).join('')}</div><div class="reply-actions"><button data-action="reply">${icon('reply')}Rispondi</button><button data-action="reply-all">${icon('reply')}Rispondi a tutti</button><button data-action="forward">${icon('forward')}Inoltra</button><button data-action="ai-reply">${icon('sparkle')}Aiutami a rispondere</button></div><div id="inline-composer"></div>`}</article>`;
  fitFrames();
  for(const item of messages)if((item.id===messages.at(-1)?.id||open.has(item.id))&&!item.body_loaded)ensureBody(item.id).catch(()=>{});
  if(S.compose?.inline&&S.selected&&S.compose.thread_key===threadKey(S.selected)){renderInlineComposer(editor);if(editor&&editor.contains(active)){active.focus({preventScroll:true});if(caret)active.setSelectionRange(...caret);}}
}

async function refresh(resetSelection=false,showLoading=false) {
  if (!S.status?.authenticated) return;
  const version=++S.listVersion;
  const view=S.view,params=new URLSearchParams({view,search:S.search});
  if(S.category&&view==='inbox')params.set('category',S.category);
  if(S.account)params.set('account',S.account);
  if(showLoading){S.loadingList=true;renderList();}
  const cachePath=view==='drafts'?'/drafts':'/messages?'+params;
  const [cachedState,cachedList]=await Promise.all([deviceCache.get('api:/state'),deviceCache.get('api:'+cachePath)]);
  if(version!==S.listVersion)return;
  if(cachedState&&cachedList){
    S.state=cachedState;
    const before=JSON.stringify(S.messages);
    if(view==='drafts'){const drafts=new Map(cachedList.drafts.map(d=>[d.id,d]));for(const draft of S.pendingDrafts.values())drafts.set(draft.id,{...draft,pending:true});S.drafts=[...drafts.values()].filter(d=>!S.discardedDrafts.has(d.id));S.messages=[];}
    else S.messages=cachedList.messages.filter(m=>!S.optimistic.get(threadKey(m))?.deleted).map(m=>({...m,...S.optimistic.get(threadKey(m))?.patch}));
    const repaint=S.loadingList||before!==JSON.stringify(S.messages);S.loadingList=false;if(repaint)renderList();
  }
  try {
    const path=view==='drafts'?'/drafts':'/messages?'+params;
    const [state,list]=await Promise.all([api('/state').catch(async error=>{if(!temporarilyUnavailable(error))throw error;return await deviceCache.get('api:/state')||Promise.reject(error);}),api(path).catch(async error=>{if(!temporarilyUnavailable(error))throw error;return await deviceCache.get('api:'+path)||(view==='drafts'&&S.pendingDrafts.size?{drafts:[]}:Promise.reject(error));})]);
    if(version!==S.listVersion)return;
    S.state=state;if(!$('#appearance-form'))applyTheme(state.appearance?.theme||S.theme);
    if(view==='drafts'){const drafts=new Map(list.drafts.map(d=>[d.id,d]));for(const draft of S.pendingDrafts.values())drafts.set(draft.id,{...draft,pending:true});S.drafts=[...drafts.values()].filter(d=>!S.discardedDrafts.has(d.id));S.messages=[];}
    else S.messages=list.messages.filter(m=>!S.optimistic.get(threadKey(m))?.deleted).map(m=>({...m,...S.optimistic.get(threadKey(m))?.patch}));
    S.messages.sort((a,b)=>(b.pinned||0)-(a.pinned||0)||b.date-a.date);
    if(resetSelection){S.selected=null;S.thread=[];S.readerAnchor=null;}
  } finally {if(version===S.listVersion)S.loadingList=false;}
}
const bodyRequests=new Map();
const bodyPath=id=>'/messages/'+encodeURIComponent(id)+(S.images?'?load_images=true':'');
function bodyMarkup(item){
  if(!item.body_loaded)return item.body_error?`<div class="offline-note">${esc(item.body_error)}</div><button class="secondary" data-download-body="${esc(item.id)}">Riprova</button>`:skeleton(3,'message-body','Scarico il messaggio…');
  return `${item.remote_images&&!S.images?'<button class="image-permission" data-action="load-images">Carica immagini esterne</button>':''}${item.html?`<iframe class="email-html" title="Contenuto di ${esc(item.subject)}" sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox" referrerpolicy="no-referrer" srcdoc="${esc(htmlDocument(item.html))}"></iframe>`:quotedText(item.body)}${item.attachments?.length?`<div class="attachments">${item.attachments.map(a=>`<a class="attachment" href="/api/messages/${encodeURIComponent(item.id)}/attachments/${a.index}">${icon('paperclip')}${esc(a.name)}</a>`).join('')}</div>`:''}`;
}
function displayBody(item){
  const slot=[...document.querySelectorAll('[data-body-for]')].find(el=>el.dataset.bodyFor===item.id);
  if(!slot||!slot.closest('details')?.open)return;
  slot.querySelectorAll('.email-html').forEach(frame=>frame._observer?.disconnect());
  slot.innerHTML=bodyMarkup(item);fitFrames(slot);
}
async function ensureBody(id){
  const version=S.readerVersion,path=bodyPath(id),metadata=S.thread.find(m=>m.id===id);
  if(!metadata)return null;
  if(metadata.body_loaded)return metadata;
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
  if(version!==S.readerVersion)return message;
  const latest=S.thread.find(m=>m.id===id)||metadata,item={...message,...latest,body_loaded:true,body_error:null};
  S.thread=S.thread.map(m=>m.id===id?item:m);if(S.selected?.id===id)S.selected=item;displayBody(item);return item;
}
let warmingVersion=0;
function warmThread(){
  const version=++warmingVersion,ids=S.thread.filter(m=>!m.body_loaded).map(m=>m.id).reverse();
  setTimeout(async()=>{for(const id of ids){if(version!==warmingVersion||!S.online||document.hidden)break;try{await ensureBody(id);}catch{break;}}},1200);
}
async function applyThread(result,id,version){
  if(version!==S.readerVersion||id!==S.readerAnchor)return;
  const messages=await Promise.all(result.messages.map(async metadata=>{
    const message=await deviceCache.get('api:'+bodyPath(metadata.id));
    return message&&(!metadata.content_version||message.content_version===metadata.content_version)?{...message,...metadata,body_loaded:true}:metadata;
  }));
  if(version!==S.readerVersion||id!==S.readerAnchor)return;
  const signature=JSON.stringify(result.messages)+JSON.stringify({phase:result.sync?.phase,error:result.sync?.error});
  const changed=S.loadingMessage||S.threadSignature!==signature;S.threadSignature=signature;
  S.thread=messages;S.threadSync=result.sync||{};if(S.thread.length)S.selected=S.thread.at(-1);
  S.loadingMessage=false;if(changed){renderReading();warmThread();}
}
async function loadThread(id,version=S.readerVersion){
  const path='/messages/'+encodeURIComponent(id)+'/thread?lazy=true';
  const cached=await deviceCache.get('api:'+path);
  if(cached)await applyThread(cached,id,version);
  try{await applyThread(await api(path),id,version);}
  catch(error){if(!cached||!temporarilyUnavailable(error))throw error;S.online=false;renderChrome();}
}
async function selectMessage(id,markRead=true) {
  warmingVersion++;const version=++S.readerVersion;
  const cached=S.messages.find(m=>m.id===id);
  S.readerAnchor=id;S.selected=cached||{id,subject:'Conversazione',category:'people'};
  S.thread=[];S.threadSync={};S.images=false;S.loadingMessage=true;S.menu=false;
  $('.shell')?.classList.add('has-selection');$('.shell')?.classList.remove('menu-open');
  renderList();renderReading();
  try {
    await loadThread(id,version);
    if(version===S.readerVersion&&markRead&&S.thread.some(m=>!m.read&&!m.sent))mutate({read:true}).catch(error=>toast(error.message));
  }catch(error){if(version===S.readerVersion){S.loadingMessage=false;S.threadSync={error:error.message};renderReading();}throw error;}
}
async function mutate(patch,deleted=false) {
  if(!S.selected||S.loadingMessage)return;
  if(S.compose&&(deleted||'archived' in patch||'snoozed_until' in patch))closeCompose().catch(error=>toast(error.message));
  const id=S.readerAnchor,key=threadKey(S.selected),previous=S.selected;
  const token={patch:{...S.optimistic.get(key)?.patch,...patch},deleted};S.optimistic.set(key,token);
  S.listVersion++;
  S.selected={...S.selected,...patch};S.thread=S.thread.map(m=>({...m,...patch}));
  S.messages=S.messages.map(m=>threadKey(m)===key?{...m,...patch}:m);
  if(deleted||('archived' in patch&&S.view==='inbox'&&patch.archived)||('snoozed_until' in patch&&S.view==='inbox'))S.messages=S.messages.filter(m=>threadKey(m)!==key);
  S.messages.sort((a,b)=>(b.pinned||0)-(a.pinned||0)||b.date-a.date);
  if(deleted||'archived' in patch||'snoozed_until' in patch){S.selected=null;S.thread=[];S.readerAnchor=null;S.readerVersion++;$('.shell')?.classList.remove('has-selection');}
  renderList();renderReading();renderChrome();
  try {
    await api('/messages/'+encodeURIComponent(id)+'/thread',deleted?'DELETE':'PATCH',deleted?undefined:patch);
    if(S.optimistic.get(key)===token)S.optimistic.delete(key);
    S.listVersion++;await refresh();renderList();renderChrome();
    if(deleted)toast('Conversazione eliminata. Sincronizzo il cestino in background.');
  }catch(error){
    if(temporarilyUnavailable(error)&&!S.online){
      const operation={id:crypto.randomUUID(),key,message_id:id,patch,deleted};token.operationId=operation.id;
      await deviceCache.enqueue(operation);await deviceCache.set('api:/messages?view=inbox&search=',{messages:S.messages});
      renderChrome();toast('Modifica salvata sul dispositivo. Verrà sincronizzata quando torni online.');return;
    }
    if(S.optimistic.get(key)===token)S.optimistic.delete(key);
    if(S.selected?.id===previous.id)S.selected=previous;
    await refresh().catch(()=>{});renderList();renderReading();
    throw error;
  }
}

function showSettings(tab=S.settingsTab) {
  S.settingsTab=tab;
  const tabs=`<div class="modal-tabs">${[['accounts','Account'],['identity','Identità'],['ai','Milo AI'],['rules','Filtri'],['appearance','Aspetto'],['devices','Dispositivi']].map(([id,name])=>`<button data-settings-tab="${id}" class="${id===tab?'active':''}">${name}</button>`).join('')}</div>`;
  let body='';
  if(tab==='accounts') {
    body=`<p>Collegali una volta. Gli account sono conservati sul tuo servizio Milo e disponibili agli altri dispositivi.</p>${S.state.accounts.map(a=>`<div class="settings-account"><span class="dot" style="background:${accountColor(a.id)}"></span><div><strong>${esc(a.name)}</strong><small>${esc(a.email)}</small></div><span class="health ${a.error?'error':''}">${!a.enabled?'In pausa':a.error?'Da controllare':a.last_sync?'Sincronizzato':'In attesa'}</span><button class="secondary" data-edit-account="${esc(a.id)}">Gestisci</button></div>${a.error?`<p class="form-error">${esc(a.error)}</p>`:''}`).join('')}<div class="form-actions"><button class="primary" data-action="add-account">${icon('plus')}Collega un account</button></div>${S.state.pending?.length?`<div class="notice" style="margin-top:20px">${S.state.pending.map(p=>`${p.count} modifiche ${esc(p.kind)}: ${esc(p.error||'in attesa della prossima sincronizzazione')}`).join('<br>')}</div>`:''}`;
  } else if(tab==='identity') {
    const identity=S.state.identity||{};
    body=`<form id="identity-form"><p>Aiuta Milo a riconoscere quando si parla di te e a scrivere dalla tua prospettiva.</p><label class="field"><span>Il tuo nome</span><input name="name" value="${esc(identity.name)}" maxlength="120" placeholder="Il nome con cui ti presenti"></label><label class="field"><span>Come ti chiamano</span><input name="aliases" value="${esc((identity.aliases||[]).join(', '))}" maxlength="1600" placeholder="Nomi e soprannomi, separati da virgole"></label><label class="field"><span>Contesto su di te</span><textarea name="context" maxlength="2000" placeholder="Ruolo, team e informazioni utili per capire chi è chi">${esc(identity.context)}</textarea></label><label class="field"><span>Lingua delle risposte</span><select name="reply_language">${[['auto','Segui la conversazione'],['en','Inglese'],['it','Italiano'],['fr','Francese'],['de','Tedesco'],['es','Spagnolo'],['pt','Portoghese']].map(([value,label])=>`<option value="${value}" ${(identity.reply_language||'auto')===value?'selected':''}>${label}</option>`).join('')}</select></label><p class="fineprint">Gli indirizzi delle caselle collegate sono già riconosciuti come tuoi. Questa identità è condivisa con tutti i tuoi dispositivi.</p><div class="form-error" role="alert"></div><button class="primary" type="submit">Salva identità</button></form>`;
  } else if(tab==='appearance') {
    body=`<form id="appearance-form"><p>Scegli come vedere Milo. La preferenza è condivisa con i tuoi dispositivi.</p><label class="field"><span>Tema</span><select name="theme">${[['system','Segui il sistema'],['light','Chiaro'],['dark','Scuro']].map(([value,label])=>`<option value="${value}" ${S.theme===value?'selected':''}>${label}</option>`).join('')}</select></label><div class="notice">Puoi scegliere il colore di ogni casella da Account → Gestisci.</div><div class="form-error" role="alert"></div><button class="primary" type="submit">Salva aspetto</button></form>`;
  } else if(tab==='ai') {
    const ai=S.state.ai;
    body=`<form id="ai-form"><p>Analisi, recap e risposte proposte passano da Ollama. Le risposte restano bozze da rivedere e inviare personalmente.</p><label class="field"><span>Modello Ollama</span><input name="model" value="${esc(ai.model)}" required></label><div class="notice"><strong>Mistral Large 4 usa Ollama Cloud.</strong><br>Con <code>mistral-large-4:cloud</code>, il contenuto delle email selezionate viene elaborato nel cloud di Ollama. Puoi scegliere un modello locale già installato.</div><label class="check-field"><input type="checkbox" name="cloud_consent" ${ai.cloud_consent?'checked':''}><span>Consento l’elaborazione delle email con modelli cloud.</span></label><label class="check-field"><input type="checkbox" name="automatic" ${ai.automatic?'checked':''}><span>Analizza automaticamente le nuove email e organizza l’inbox in Persone, Notifiche e Newsletter.</span></label>${S.state.ai_error?`<p class="form-error">${esc(S.state.ai_error)}</p>`:''}<div class="form-actions"><button class="primary" type="submit">Salva preferenze</button></div></form>`;
  } else if(tab==='rules') {
    body=`<p>I tuoi filtri hanno precedenza sulla classificazione AI e vengono applicati anche alle email già salvate.</p>${S.state.rules.map(r=>`<div class="rule-row"><div><strong>${esc(r.name)}</strong>${esc(r.contains)} → ${categoryNames[r.category]}</div><button class="icon-button" data-delete-rule="${esc(r.id)}" aria-label="Elimina filtro">${icon('trash')}</button></div>`).join('')}<form id="rule-form" style="margin-top:22px"><div class="form-grid"><label class="field full"><span>Nome del filtro</span><input name="name" placeholder="Le notifiche di GitHub" required></label><label class="field"><span>Quando</span><select name="field"><option value="sender">Il mittente contiene</option><option value="subject">L’oggetto contiene</option><option value="body">Il testo contiene</option></select></label><label class="field"><span>Questo testo</span><input name="contains" placeholder="github.com" required></label><label class="field full"><span>Sposta nella categoria</span><select name="category">${Object.entries(categoryNames).map(([key,name])=>`<option value="${key}">${name}</option>`).join('')}</select></label></div><div class="form-actions"><button class="primary" type="submit">Crea filtro</button></div></form>`;
  } else {
    body=`<p>Questa è la casa del tuo archivio. Un altro dispositivo che accede allo stesso indirizzo trova account, email, preferenze e bozze già configurati.</p><div class="notice"><strong>Indirizzo del servizio</strong><br>${esc(location.origin)}</div><p>Per accedere da iPhone servirà un indirizzo HTTPS raggiungibile dal telefono. La versione nativa iOS e le notifiche push sono i prossimi passi; questa prima versione parte da Linux.</p><div class="notice">I messaggi scaricati sono conservati nella cache privata di questo dispositivo e si possono leggere offline. L’archivio completo e gli account restano sul servizio.</div>${S.status.access==='tailscale'?'<div class="notice">Accesso privato tramite i tuoi dispositivi Tailscale autorizzati. Il dominio pubblico mostra solo la presentazione di Milo.</div>':!S.status.demo?'<div class="form-actions"><button class="secondary" data-action="logout">Esci da questo dispositivo</button></div>':''}`;
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
  showModal('Collega un account IMAP',`<form id="account-form"><label class="field"><span>Provider</span><select id="provider"><option value="icloud">iCloud Mail</option><option value="other">Altro account IMAP</option></select></label><div class="notice" id="provider-notice">Usa una password specifica per app generata nel tuo account Apple. Il nome utente IMAP può essere la parte prima di @icloud.com.</div><div class="form-grid"><label class="field"><span>Nome dell’account</span><input name="name" value="Personale" required maxlength="80"></label><label class="field"><span>Indirizzo email</span><input name="email" type="email" required autocomplete="email"></label><label class="field"><span>Nome utente</span><input name="username" placeholder="Di solito l’indirizzo email" required></label><label class="field"><span>Password per app</span><input name="password" type="password" required autocomplete="off"></label><label class="field"><span>Server IMAP</span><input name="imap_host" value="imap.mail.me.com" required></label><label class="field"><span>Porta IMAP (TLS)</span><input name="imap_port" type="number" value="993" min="1" max="65535" required></label><label class="field"><span>Server SMTP</span><input name="smtp_host" value="smtp.mail.me.com" required></label><label class="field"><span>Porta SMTP</span><input name="smtp_port" type="number" value="587" min="1" max="65535" required></label><label class="field full"><span>Sicurezza SMTP</span><select name="smtp_security"><option value="tls">TLS</option><option value="starttls" selected>STARTTLS</option></select></label></div><div class="form-error" role="alert"></div><div class="form-actions"><button class="secondary" type="button" data-action="close-modal">Annulla</button><button class="primary" type="submit">Collega e sincronizza ${icon('arrow')}</button></div></form>`);
}

function showAccountSettings(accountId) {
  const a=S.state.accounts.find(account=>account.id===accountId);
  if(!a) return;
  const imap=a.provider==='imap';
  const connection=imap?`<div class="form-grid"><label class="field"><span>Nome utente</span><input name="username" value="${esc(a.username)}" required></label><label class="field"><span>Nuova password per app</span><input name="password" type="password" autocomplete="new-password" placeholder="Lascia vuoto per conservarla"></label><label class="field"><span>Server IMAP</span><input name="imap_host" value="${esc(a.imap_host)}" required></label><label class="field"><span>Porta IMAP (TLS)</span><input name="imap_port" type="number" value="${a.imap_port}" min="1" max="65535" required></label><label class="field"><span>Server SMTP</span><input name="smtp_host" value="${esc(a.smtp_host)}" required></label><label class="field"><span>Porta SMTP</span><input name="smtp_port" type="number" value="${a.smtp_port}" min="1" max="65535" required></label><label class="field full"><span>Sicurezza SMTP</span><select name="smtp_security"><option value="tls" ${a.smtp_security==='tls'?'selected':''}>TLS</option><option value="starttls" ${a.smtp_security==='starttls'?'selected':''}>STARTTLS</option></select></label></div>`:`<p>L’accesso Google è conservato sul servizio. Se Google lo revoca o scade, ricollega questa casella.</p><button class="secondary" type="button" data-action="google-connect" data-reconnect-account="${esc(a.id)}">Ricollega ${esc(a.email)}</button>`;
  showModal('Gestisci account',`<form id="account-settings-form" data-account-id="${esc(a.id)}"><div class="notice">${esc(a.email)} · ${imap?'IMAP':'Google'}</div><label class="field"><span>Nome dell’account</span><input name="name" value="${esc(a.name)}" required maxlength="80"></label><label class="field color-field"><span>Colore della casella</span><input name="color" type="color" value="${accountColor(a.id)}"></label><label class="check-field"><input type="checkbox" name="enabled" ${a.enabled?'checked':''}><span>Sincronizza questa casella. In pausa, le email e le bozze salvate restano disponibili; le modifiche aspettano la ripresa.</span></label>${connection}<div class="form-error" role="alert"></div><div class="form-actions"><button class="secondary" type="button" data-action="close-modal">Annulla</button><button class="primary" type="submit">Salva account</button></div></form>`);
}

function composeMarkup(draft,inline=false) {
  return `<form id="compose-form" class="${inline?'inline-compose-form':''}"><div class="compose-heading"><h3>${draft.mode==='forward'?'Inoltra':['reply','reply_all'].includes(draft.mode)?draft.mode==='reply_all'?'Rispondi a tutti':'Rispondi':'Nuovo messaggio'}</h3>${inline?`<button class="icon-button" type="button" data-action="close-compose" aria-label="Chiudi" title="Chiudi bozza">${icon('close')}</button>`:''}</div><label class="field"><span>Da</span><select name="account_id">${S.state.accounts.map(a=>`<option value="${esc(a.id)}" ${draft.account_id===a.id?'selected':''}>${esc(a.name)} · ${esc(a.email)}</option>`).join('')}</select></label><label class="field"><span>A</span><input name="to" value="${esc(draft.to)}" placeholder="nome@example.com" maxlength="2000"></label><label class="field"><span>Cc</span><input name="cc" value="${esc(draft.cc)}" placeholder="Copia conoscenza" maxlength="2000"></label><label class="field"><span>Oggetto</span><input name="subject" value="${esc(draft.subject)}" placeholder="Di cosa parliamo?" maxlength="998"></label><label class="field"><span>Messaggio</span><textarea class="composer-body" name="body" placeholder="Scrivi qui…" maxlength="1000000">
${esc(draft.body)}</textarea></label><div class="form-error" role="alert"></div><div class="form-actions"><button class="secondary" type="button" data-action="delete-draft">Elimina bozza</button><button class="secondary" type="button" data-action="save-draft">Salva bozza</button><button class="primary" type="submit">${icon('sent')}Invia messaggio</button></div><div class="draft-save-status" role="status">${S.pendingDrafts.has(draft.id)?'Salvataggio in attesa':'Le modifiche vengono salvate automaticamente.'}</div></form>`;
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
function rememberDraft(draft,immediate=true){if(!draft||(!draft.to&&!draft.subject&&!draft.body))return false;S.pendingDrafts.set(draft.id,{...draft});if(immediate)storePendingDrafts();else{clearTimeout(localDraftTimer);localDraftTimer=setTimeout(storePendingDrafts,200);}return true;}
function draftPayload(draft){return Object.fromEntries(['id','account_id','to','cc','subject','body','reply_to_id','context_message_id','mode','revision'].map(key=>[key,draft[key]??(['to','cc','subject','body'].includes(key)?'':null)]));}
function persistDraft(draft) {
  if(!rememberDraft(draft)||S.discardedDrafts.has(draft.id))return Promise.resolve(null);
  const previous=S.draftWrites.get(draft.id);
  if(previous&&previous.revision>=draft.revision)return previous.promise;
  const promise=(previous?.promise||Promise.resolve()).catch(()=>{}).then(async()=>{
    if(S.discardedDrafts.has(draft.id))return null;
    if($('#compose-form')&&S.compose?.id===draft.id&&$('.draft-save-status'))$('.draft-save-status').textContent='Salvataggio…';
    const result=await api('/drafts','PUT',draftPayload(draft));
    await cachedDraftChange(result.id,draft);
    if((S.pendingDrafts.get(draft.id)?.revision||0)<=draft.revision)S.pendingDrafts.delete(draft.id);
    storePendingDrafts();
    if(S.compose?.id===draft.id&&$('.draft-save-status'))$('.draft-save-status').textContent='Bozza salvata';
    return result.id;
  });
  S.draftWrites.set(draft.id,{revision:draft.revision,promise});
  promise.finally(()=>{if(S.draftWrites.get(draft.id)?.promise===promise)S.draftWrites.delete(draft.id);}).catch(()=>{});
  return promise;
}
function removeComposer(){clearTimeout(autosaveTimer);if($('#overlay #compose-form'))$('#overlay').innerHTML='';if($('#inline-composer'))$('#inline-composer').innerHTML='';S.compose=null;}
async function cachedDraftChange(id,draft=null){
  const existing=await deviceCache.get('api:/drafts')||{drafts:[]};
  const drafts=existing.drafts.filter(item=>item.id!==id);
  if(draft)drafts.unshift({...draft,id,updated:Date.now()/1000});
  await deviceCache.set('api:/drafts',{drafts});
}
async function closeCompose(){const draft=captureCompose();removeComposer();if(draft)await persistDraft(draft);}
async function saveCompose(){clearTimeout(autosaveTimer);return persistDraft(captureCompose());}
function showCompose(draft={},inline=Boolean(draft.reply_to_id||draft.context_message_id)) {
  if(!S.state.accounts.length){showAccountForm();return;}
  if(S.compose){
    if(inline&&S.compose.context_message_id===(draft.context_message_id||draft.reply_to_id)&&S.compose.mode===(draft.mode||'reply')){$('#compose-form [name="body"]')?.focus();return;}
    closeCompose().catch(error=>toast(error.message));
  }
  const mode=draft.reply_to_id&&(!draft.mode||draft.mode==='new')?'reply':draft.mode||'new';
  const current={...draft,id:draft.id||crypto.randomUUID(),account_id:draft.account_id||S.state.accounts[0].id,to:draft.to||'',cc:draft.cc||'',subject:draft.subject||'',body:draft.body||'',mode,reply_to_id:draft.reply_to_id||null,context_message_id:draft.context_message_id||draft.reply_to_id||null,revision:draft.revision||Date.now(),inline:inline&&Boolean($('#inline-composer')),thread_key:S.selected?threadKey(S.selected):null};
  S.compose=current;
  if(current.inline){renderInlineComposer();$('#inline-composer').scrollIntoView({block:'nearest'});$('#inline-composer [name="body"]').focus({preventScroll:true});}
  else{showModal('Nuovo messaggio',composeMarkup(current),true);S.compose=current;}
}
async function openDraft(draft){
  if(S.compose)closeCompose().catch(error=>toast(error.message));
  const anchor=draft.context_message_id||draft.reply_to_id;
  if(anchor){S.view='inbox';renderShell();await selectMessage(anchor,false);showCompose(draft,true);}
  else showCompose(draft,false);
}
async function discardCompose(){
  const draft=captureCompose();if(!draft)return;
  S.discardedDrafts.add(draft.id);S.pendingDrafts.delete(draft.id);storePendingDrafts();removeComposer();
  await S.draftWrites.get(draft.id)?.promise.catch(()=>{});await api('/drafts/'+encodeURIComponent(draft.id),'DELETE');await cachedDraftChange(draft.id);
  await refresh();renderList();toast('Bozza eliminata.');
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
    if(action==='analyze') {
      await api('/messages/'+id+'/analyze','POST');
      S.analyzing=false;if(S.selected?.id===id)await loadThread(S.readerAnchor);
      await refresh();renderList();
    } else {
      const result=await api('/messages/'+id+'/reply','POST');
      if(S.compose?.id===generatedDraft.id&&S.compose.revision===generatedDraft.revision&&!S.compose.body){
        const field=$('#compose-form [name="body"]');field.value=result.body;field.dispatchEvent(new Event('input',{bubbles:true}));
      }else if(S.compose?.id===generatedDraft.id)toast('Hai già modificato la bozza. Il tuo testo è stato conservato.');
    }
  } catch(error) { if(action==='recap') closeModal(); toast(error.message); }
  finally { if(S.compose?.id===generatedDraft?.id)$('#compose-form .reply-generation')?.remove();S.analyzing=false;if(action==='analyze')renderReading();if(button){button.disabled=false;button.classList.remove('is-loading');} }
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
    if(target.dataset.view) {
      if(S.compose)closeCompose().catch(error=>toast(error.message));
      S.view=target.dataset.view; S.category=''; S.selected=null; S.menu=false;
      S.loadingList=true;renderShell();await refresh(true,true);renderList();return;
    }
    if('category' in target.dataset) { if(S.compose)closeCompose().catch(error=>toast(error.message));S.category=target.dataset.category; S.selected=null; S.loadingList=true;renderShell();await refresh(true,true);renderList();return; }
    if(target.dataset.account) { if(S.compose)closeCompose().catch(error=>toast(error.message));S.account=S.account===target.dataset.account?'':target.dataset.account; S.loadingList=true;renderShell();await refresh(true,true);renderList();return; }
    if(target.dataset.message) { if(S.compose)closeCompose().catch(error=>toast(error.message));await selectMessage(target.dataset.message); return; }
    if(target.dataset.downloadBody){await ensureBody(target.dataset.downloadBody);return;}
    if(target.dataset.draft) { await openDraft(S.drafts.find(d=>d.id===target.dataset.draft)); return; }
    if(target.dataset.editAccount) { showAccountSettings(target.dataset.editAccount);return; }
    if(target.dataset.settingsTab) { showSettings(target.dataset.settingsTab); return; }
    if(target.dataset.deleteRule) { await api('/rules/'+target.dataset.deleteRule,'DELETE');await refresh();showSettings('rules');renderList();return; }
    if(target.dataset.recapMessage) { closeModal();await selectMessage(target.dataset.recapMessage);return; }
    const action=target.dataset.action;
    if(['recap','analyze','ai-reply'].includes(action)) { await runAI(action,target);return; }
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
    if(action==='reply'||action==='reply-all') {target.disabled=true;target.classList.add('is-loading');const version=S.readerVersion;try{const source=S.thread.findLast(message=>!message.sent)||S.selected,m=await recipientContext(source);if(version===S.readerVersion)showCompose({account_id:m.account_id,...replyRecipients(m,action==='reply-all'),mode:action==='reply-all'?'reply_all':'reply',subject:'Re: '+subjectCore(m.subject),reply_to_id:m.id});}finally{target.disabled=false;target.classList.remove('is-loading');}}
    if(action==='forward') { const m=await ensureBody(S.selected.id);if(!m)return;showCompose({account_id:m.account_id,mode:'forward',context_message_id:m.id,subject:'Fwd: '+subjectCore(m.subject),body:`\n\n---------- Messaggio inoltrato ----------\nDa: ${m.sender} <${m.sender_email}>\nOggetto: ${m.subject}\n\n${m.body}`}); }
    if(action==='save-draft') { if(await saveCompose()) { await refresh();renderList();toast('Bozza salvata nel tuo archivio.'); } }
    if(action==='delete-draft')await discardCompose();
    if(action==='close-compose')await closeCompose();
    if(action==='close-modal'){if($('#overlay #compose-form'))await closeCompose();else closeModal();await refresh();renderList();}
    if(action==='sync') {
      if(S.syncing)return;S.syncing=true;renderChrome();
      try{await api('/sync','POST');toast('Sincronizzazione avviata in background.');}
      finally{S.syncing=false;await refresh();renderChrome();renderList();}
    }
    if(action==='retry-login') { await boot(); }
    if(action==='logout') { await api('/logout','POST');await deviceCache.clear();S.status.authenticated=false;S.selected=null;S.messages=[];renderLogin(); }
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
      await api('/settings/google','PUT',config);await refresh();showAccountForm();toast('Google configurato. Ora collega la tua casella.');
    }
    if(form.id==='account-form') {
      data.imap_port=Number(data.imap_port);data.smtp_port=Number(data.smtp_port);
      await api('/accounts','POST',data);closeModal();await refresh();renderShell();toast('Account salvato. La prima sincronizzazione è in corso.');
    }
    if(form.id==='account-settings-form') {
      data.enabled=form.elements.enabled.checked;
      if(form.elements.password) {
        if(!data.password) delete data.password;
        data.imap_port=Number(data.imap_port);data.smtp_port=Number(data.smtp_port);
      }
      await api('/accounts/'+encodeURIComponent(form.dataset.accountId),'PATCH',data);
      S.loadingList=true;renderShell();await refresh(false,true);renderList();showSettings('accounts');toast('Account aggiornato su Milo.');
    }
    if(form.id==='identity-form') {
      data.aliases=data.aliases.split(',').map(name=>name.trim()).filter(Boolean);
      S.state.identity=await api('/settings/identity','PUT',data);await refresh();closeModal();toast('Identità salvata. Milo la userà nelle prossime risposte.');
    }
    if(form.id==='appearance-form'){applyTheme(data.theme);await api('/settings/appearance','PUT',data);S.state.appearance=data;closeModal();toast('Aspetto salvato.');}
    if(form.id==='ai-form') {
      data.automatic=form.elements.automatic.checked;data.cloud_consent=form.elements.cloud_consent.checked;
      await api('/settings/ai','PUT',data);await refresh();closeModal();toast('Preferenze AI salvate.');
    }
    if(form.id==='rule-form') { await api('/rules','POST',data);await refresh();showSettings('rules');renderList();toast('Filtro creato e applicato.'); }
    if(form.id==='compose-form') {
      const snapshot=captureCompose(),id=await saveCompose();if(!id)throw new Error('Scrivi prima il tuo messaggio.');
      await api('/drafts/'+encodeURIComponent(id)+'/send','POST');
      if(S.compose?.id===id&&(S.compose.revision||0)<=snapshot.revision){removeComposer();await cachedDraftChange(id);}
      await refresh();if(S.readerAnchor)await loadThread(S.readerAnchor);renderList();toast('Messaggio inviato.');
    }
  } catch(error) { if(errorBox) errorBox.textContent=error.message;else toast(error.message); }
  finally { S.analyzing=false;if(button){button.disabled=false;button.classList.remove('is-loading');} }
});

document.addEventListener('input', event => {
  if(event.target.closest('#compose-form')){const draft=captureCompose();rememberDraft(draft,false);clearTimeout(autosaveTimer);autosaveTimer=setTimeout(()=>persistDraft(draft).catch(()=>{if($('.draft-save-status'))$('.draft-save-status').textContent='Salvataggio in attesa. La copia resta nelle bozze.';}),700);}
  if(event.target.id==='search-input') {
    S.search=event.target.value;clearTimeout(searchTimer);
    searchTimer=setTimeout(async()=>{try{await refresh(false,true);renderList();}catch(error){toast(error.message);}},200);
  }
  if(event.target.name==='email' && $('#account-form')) $('#account-form').elements.username.value=event.target.value;
});
document.addEventListener('change', async event => {
  if(event.target.name==='theme'&&$('#appearance-form'))applyTheme(event.target.value);
  if(event.target.id==='message-category') { try{await mutate({category:event.target.value});}catch(error){toast(error.message);} }
  if(event.target.id==='provider') {
    const form=$('#account-form'), provider=event.target.value;
    const presets={icloud:['imap.mail.me.com','smtp.mail.me.com',587,'starttls'],other:['','',465,'tls']};
    const [imap,smtp,port,security]=presets[provider];form.elements.imap_host.value=imap;form.elements.smtp_host.value=smtp;form.elements.smtp_port.value=port;form.elements.smtp_security.value=security;
    $('#provider-notice').textContent={icloud:'Usa una password specifica per app generata nel tuo account Apple. Il nome utente IMAP può essere la parte prima di @icloud.com.',other:'Inserisci i parametri del tuo provider. IMAP usa TLS; SMTP può usare TLS oppure STARTTLS.'}[provider];
  }
});
document.addEventListener('keydown', async event => {
  const editing=['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName);
  if(event.key==='Escape') {
    try { if($('#compose-form')){closeCompose().catch(error=>toast(error.message));}else closeModal();S.menu=false;$('.shell')?.classList.remove('menu-open'); }
    catch(error) { toast(error.message); }
  }
  if(!editing && !$('#overlay').children.length) {
    if(event.key==='/') { event.preventDefault();$('#search-input')?.focus(); }
    if(event.key==='c') showCompose();
    if(event.key==='e' && S.selected) { try{await mutate({archived:true});}catch(error){toast(error.message);} }
  }
  if(event.key==='Tab' && $('#overlay .modal')) {
    const controls=[...$('#overlay .modal').querySelectorAll('button,input,textarea,select,a[href]')].filter(el=>!el.disabled);
    const first=controls[0],last=controls.at(-1);
    if(event.shiftKey && document.activeElement===first) { event.preventDefault();last.focus(); }
    if(!event.shiftKey && document.activeElement===last) { event.preventDefault();first.focus(); }
  }
});

async function boot() {
  try {
    const oauth=new URLSearchParams(location.hash.slice(1));
    const oauthError=oauth.get('google_error'),connected=oauth.has('google_connected'),ownerToken=oauth.get('setup');
    if(ownerToken || oauthError || connected) history.replaceState(null,'',location.pathname);
    const cachedStatus=await deviceCache.get('api:/status'),cachedState=await deviceCache.get('api:/state'),cachedList=await deviceCache.get('api:/messages?view=inbox&search=');
    for(const operation of await deviceCache.get('pending-operations')||[])S.optimistic.set(operation.key,{patch:{...S.optimistic.get(operation.key)?.patch,...operation.patch},deleted:operation.deleted,operationId:operation.id});
    if(cachedStatus?.authenticated&&cachedState&&cachedList){S.status=cachedStatus;S.state=cachedState;S.messages=cachedList.messages.filter(m=>!S.optimistic.get(threadKey(m))?.deleted).map(m=>({...m,...S.optimistic.get(threadKey(m))?.patch}));S.online=navigator.onLine;renderShell();renderList();}
    try{S.status=await api('/status');}catch(error){if(!temporarilyUnavailable(error))throw error;if(!cachedStatus?.authenticated)throw error;S.status=cachedStatus;S.online=false;}

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
    S.loadingList=true;renderShell();await refresh(false,true);renderList();
    if(S.status.demo && S.messages.length && innerWidth>900) await selectMessage(S.messages[0].id,false);
  } catch(error) { $('#app').innerHTML=`<div class="empty" style="min-height:100vh">${icon('mail')}<h3>Milo non è raggiungibile.</h3><p>${esc(error.message)}</p></div>`; }
}
let flushingQueue=false;
async function flushClientQueue(){
  if(flushingQueue||!S.online)return;flushingQueue=true;
  try{
    for(const operation of await deviceCache.get('pending-operations')||[]){
      try{await api('/messages/'+encodeURIComponent(operation.message_id)+'/thread',operation.deleted?'DELETE':'PATCH',operation.deleted?undefined:operation.patch);}
      catch(error){if(error.status!==404)throw error;}
      await deviceCache.acknowledge(operation.id);
      if(S.optimistic.get(operation.key)?.operationId===operation.id)S.optimistic.delete(operation.key);
    }
  }finally{flushingQueue=false;}
}
async function poll() {
  try {
    if(S.status?.authenticated&&!document.hidden){
      const before=JSON.stringify(S.messages);
      await refresh();await flushClientQueue();renderChrome();if(before!==JSON.stringify(S.messages))renderList();
      if(S.recapOpen&&S.recapSignature!==JSON.stringify(S.state.recap)){const result=await api('/recap');if(S.recapOpen)showRecap(result);}
      for(const draft of S.pendingDrafts.values())if(!S.draftWrites.has(draft.id)&&S.compose?.id!==draft.id)persistDraft(draft).catch(()=>{});
      if(S.readerAnchor&&(S.threadSync.phase==='downloading'||before!==JSON.stringify(S.messages))&&!S.loadingMessage)await loadThread(S.readerAnchor);
    }
  }catch(error){if(error.status===404){S.readerAnchor=null;S.selected=null;renderReading();}renderChrome();}
  finally {setTimeout(poll,(S.state.sync||[]).some(p=>['connecting','downloading','applying'].includes(p.phase))||S.threadSync.phase==='downloading'?2000:10000);}
}
setTimeout(poll,2000);
addEventListener('pagehide',()=>{const draft=captureCompose();if(draft)rememberDraft(draft);else storePendingDrafts();});
if('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js',{type:'module'}).catch(()=>{});
boot();
