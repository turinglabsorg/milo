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
const icon = (name, extra = '') => `<svg class="icon ${extra}" viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[name] || paths.mail}"/></svg>`;
const logo = () => '<div class="logo"><img src="/static/icon.svg" alt="">milo<small>MAIL</small></div>';
const S = {status:null, setupAuthorized:false, state:{accounts:[], counts:{}, ai:{}}, messages:[], selected:null, view:'inbox', category:'', account:'', search:'', settingsTab:'accounts', menu:false, syncing:false, online:true, compose:null};
const categoryNames = {people:'Persone', updates:'Notifiche', newsletters:'Newsletter'};
const viewNames = {inbox:'Smart inbox', starred:'Preferiti', drafts:'Bozze', sent:'Posta inviata', snoozed:'Per dopo', archive:'Archivio'};
let toastTimer, searchTimer;

async function api(path, method='GET', body) {
  let response;
  try { response = await fetch('/api' + path, {method, credentials:'same-origin', headers:body ? {'Content-Type':'application/json'} : {}, body:body ? JSON.stringify(body) : undefined}); }
  catch { S.online=false; throw new Error('Connessione a Milo interrotta. I dati salvati restano sul servizio.'); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && S.status?.authenticated) { S.status.authenticated=false; renderLogin(); }
    const message = Array.isArray(data.detail) ? data.detail.map(item => item.msg).join('; ') : data.detail;
    const error=new Error(message || 'Operazione non riuscita');error.status=response.status;throw error;
  }
  S.online=true;
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
  $('#overlay').innerHTML=`<div class="modal-backdrop"><section class="modal ${wide?'wide':''}" role="dialog" aria-modal="true" aria-label="${esc(title)}"><div class="modal-header"><h2>${esc(title)}</h2><button class="icon-button" data-action="close-modal" aria-label="Chiudi">${icon('close')}</button></div>${content}</section></div>`;
  setTimeout(() => $('#overlay input, #overlay select, #overlay button')?.focus(), 0);
}
function closeModal() { $('#overlay').innerHTML=''; S.compose=null; }

function renderLogin() {
  closeModal();
  const setup = !S.status.initialized;
  const form = setup && !S.setupAuthorized
    ? `<section class="login-form"><h2>Milo aspetta il primo accesso.</h2><p>Apri l’app Milo sul dispositivo su cui è stata installata per scegliere la tua password. Poi potrai accedere anche da qui.</p><button class="primary" data-action="retry-login">Riprova ${icon('arrow')}</button></section>`
    : `<form class="login-form" id="login-form"><h2>${setup?'Benvenuto a casa.':'Bentornato.'}</h2><p>${setup?'Scegli una password per Milo. Ti servirà per accedere al tuo archivio da Linux e dagli altri dispositivi.':'Accedi al tuo archivio. Account, preferenze e bozze sono già qui, come li hai lasciati.'}</p><label class="field"><span>Password di Milo</span><input type="password" name="password" minlength="12" maxlength="256" required autocomplete="${setup?'new-password':'current-password'}" placeholder="Almeno 12 caratteri"></label><div class="form-error" id="login-error" role="alert"></div><button type="submit" class="primary">${setup?'Crea il tuo Milo':'Entra in Milo'}${icon('arrow')}</button><div class="fineprint">${setup?'Conservala in un posto sicuro: ti servirà per accedere anche dagli altri dispositivi.':'Lo stesso servizio, la stessa password. Nessun account da riconfigurare.'}</div></form>`;
  $('#app').innerHTML=`<main class="login-page"><section class="login-story">${logo()}<h1>La tua posta.<br>Un po’ più leggera.</h1><p>Meno rumore, più spazio per quello che conta. Un’unica casa per le tue email, su tutti i tuoi dispositivi.</p><div class="story-features"><span>${icon('inbox')}Tutti gli account, una sola inbox</span><span>${icon('sparkle')}Un assistente che mette ordine</span><span>${icon('shield')}Il tuo archivio, sotto il tuo controllo</span></div></section><section class="login-area">${form}</section></main>`;
  $('#login-form input')?.focus();
}

function accountMarkup() {
  return `<div class="nav-label">Account</div>${S.state.accounts.map(a=>`<button class="account-button ${S.account===a.id?'active':''}" data-account="${esc(a.id)}"><span class="dot" style="${a.enabled?'':'opacity:.4'}"></span>${esc(a.name)}${S.account===a.id?icon('check'):''}</button>`).join('')}<button class="account-button plus-account" data-action="add-account">${icon('plus')}Aggiungi account</button>`;
}
function renderChrome() {
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
  $('#app').innerHTML=`<main class="shell ${S.selected?'has-selection':''} ${S.menu?'menu-open':''}"><aside class="sidebar">${logo()}<button class="primary compose-button" data-action="compose">${icon('plus')}Nuovo messaggio</button><div class="nav-label">La tua posta</div><nav class="nav">${folders.map(([view,name])=>`<button class="nav-button ${S.view===view?'active':''}" data-view="${view}">${icon(name)}${viewNames[view]}${counts[view]?`<span class="count">${counts[view]}</span>`:''}</button>`).join('')}</nav><div class="account-section">${accountMarkup()}</div><div class="sidebar-bottom"><div class="ai-card"><div class="mini-heading">${icon('sparkle')}Un po’ di intelligenza.</div><p>Recap, priorità e meno rumore.<br>Milo ti aiuta a fare spazio.</p><button data-action="settings-ai">Scopri Milo AI ${icon('arrow')}</button></div><div class="sidebar-footer"><div class="user-avatar">${esc(initials(S.state.accounts[0]?.name || 'Tu'))}</div><span>Il tuo spazio</span><button data-action="settings" aria-label="Impostazioni">${icon('settings')}</button></div>${S.status.demo?'<div class="demo-label">DEMO · messaggi fittizi</div>':''}</div></aside><header class="topbar"><button class="icon-button mobile-menu" data-action="menu" aria-label="Apri menu">${icon('menu')}</button><div class="breadcrumbs">Il tuo spazio ${icon('arrow')}<strong>${viewNames[S.view]}</strong></div><div class="top-tools"><label class="search">${icon('search')}<input id="search-input" placeholder="Cerca nella tua posta" value="${esc(S.search)}" aria-label="Cerca nella tua posta"><kbd>/</kbd></label><button class="icon-button ${S.syncing?'spinner':''}" data-action="sync" aria-label="Sincronizza" title="Sincronizza">${icon('refresh')}</button><span class="sync-indicator ${!S.online||S.state.accounts.some(a=>a.error)?'offline':''}" title="${S.online?'Servizio connesso':'Servizio non raggiungibile'}"></span><button class="icon-button" data-action="settings" aria-label="Impostazioni">${icon('settings')}</button></div></header><section class="list-panel" id="list-panel"></section><section class="reading-panel" id="reading-panel"></section></main>`;
  renderList(); renderReading();
}

function renderList() {
  if (!$('#list-panel')) return;
  const inbox = S.view==='inbox';
  const count = S.messages.length;
  $('#list-panel').innerHTML=`<div class="list-heading"><div class="eyebrow">${new Date().toLocaleDateString('it-IT',{weekday:'long',day:'numeric',month:'long'})}</div><div class="title-row"><h1>${viewNames[S.view]}</h1><span class="badge">${S.view==='drafts'?S.drafts?.length||0:count} ${count===1?'messaggio':'messaggi'}</span></div><p class="subheading">${inbox?`${S.state.counts.unread||0} email da leggere. Facciamo un po’ di spazio.`:({starred:'Le conversazioni a cui vuoi tornare.',drafts:'Le parole giuste, con i tuoi tempi.',sent:'I messaggi che hai inviato.',snoozed:'Al momento giusto, di nuovo nella tua inbox.',archive:'Tutto conservato, niente in mezzo.'}[S.view])}</p></div>${inbox?`<button class="recap-card" data-action="recap"><span class="recap-symbol">${icon('sparkle')}</span><span><strong>La tua inbox, in un minuto.</strong><p>Lascia che Milo prepari il tuo recap.</p></span>${icon('arrow')}</button><div class="tabs">${[['','Tutte'],['people','Persone'],['updates','Notifiche'],['newsletters','Newsletter']].map(([category,name])=>`<button class="tab ${S.category===category?'active':''}" data-category="${category}">${name}</button>`).join('')}</div>`:''}${!S.online?'<div class="offline-note">Servizio non raggiungibile. Riprovo a collegarmi.</div>':''}${S.state.accounts.some(a=>a.error)?`<div class="error-banner">${esc(S.state.accounts.find(a=>a.error).error)} <button data-action="settings">Apri account</button></div>`:''}${S.state.pending?.some(p=>p.error)?'<div class="error-banner">Alcune modifiche aspettano il server. Puoi controllarle nelle impostazioni.</div>':''}<div id="message-list"></div>`;
  const container=$('#message-list');
  if (S.view==='drafts') {
    container.innerHTML=(S.drafts?.length?S.drafts.map(d=>`<button class="draft-row" data-draft="${esc(d.id)}"><small>${esc(d.to||'Nessun destinatario')}</small><strong>${esc(d.subject||'Senza oggetto')}</strong><p>${esc(d.body.slice(0,100))}</p></button>`).join(''):emptyMarkup('edit','Un pensiero da scrivere.','Le bozze salvate appariranno qui, anche sugli altri dispositivi.'));
    return;
  }
  if (!count) {
    container.innerHTML=emptyMarkup('inbox',S.state.accounts.length?'Un po’ di spazio.':'Cominciamo dalla tua posta.',S.state.accounts.length?'Qui non ci sono messaggi. Le email arriveranno con la sincronizzazione.':'Collega il tuo primo account. Al resto pensiamo insieme.',!S.state.accounts.length);
    return;
  }
  let lastDay='';
  container.innerHTML=S.messages.map(m=>{
    const day=isToday(m.date)?'Oggi':new Date(m.date*1000).toLocaleDateString('it-IT',{day:'numeric',month:'long'});
    const heading=day!==lastDay?`<div class="day-heading">${esc(day)}<span class="right">${S.search?'Risultati di ricerca':'Le tue conversazioni'}</span></div>`:'';
    lastDay=day;
    return heading+`<button class="message-row ${m.read?'':'unread'} ${S.selected?.id===m.id?'selected':''}" data-message="${esc(m.id)}">${avatar(m)}<span class="message-content"><span class="sender-line"><strong>${esc(m.sender)}</strong>${!m.read?'<span class="unread-dot"></span>':''}<time>${dateLabel(m.date)}</time></span><span class="row-subject">${esc(m.subject)}</span><span class="row-preview">${esc(m.preview)}</span></span>${m.starred?`<span class="row-star">${icon('star')}</span>`:''}</button>`;
  }).join('');
}
function emptyMarkup(symbol,title,description,add=false) {
  return `<div class="empty">${icon(symbol)}<h3>${esc(title)}</h3><p>${esc(description)}</p>${add?'<button class="primary" data-action="add-account">Collega un account</button>':''}</div>`;
}

function renderReading() {
  if (!$('#reading-panel')) return;
  const m=S.selected;
  if (!m) { $('#reading-panel').innerHTML=emptyMarkup('mail','Spazio per una conversazione.','Scegli un’email e prenditi il tempo per leggerla.'); return; }
  const analysis=m.analysis;
  $('#reading-panel').innerHTML=`<div class="reading-toolbar"><button class="icon-button back-button" data-action="back" aria-label="Torna alla lista">${icon('back')}</button><button class="icon-button" data-action="archive" aria-label="${m.archived?'Sposta in inbox':'Archivia'}" title="${m.archived?'Sposta in inbox':'Archivia'}">${icon('archive')}</button><button class="icon-button" data-action="snooze" aria-label="Posticipa" title="Posticipa">${icon('clock')}</button><button class="icon-button" data-action="read" aria-label="${m.read?'Segna da leggere':'Segna come letta'}" title="${m.read?'Segna da leggere':'Segna come letta'}">${icon('mail')}</button><span class="separator"></span><button class="icon-button" data-action="star" aria-label="${m.starred?'Rimuovi dai preferiti':'Aggiungi ai preferiti'}" title="Preferiti" style="${m.starred?'color:#a78dc9':''}">${icon('star')}</button><div class="right"><span class="dot"></span>${esc(S.state.accounts.find(a=>a.id===m.account_id)?.name||'Account')}</div></div><article class="mail-content"><span class="mail-label">${icon('people')}${categoryNames[m.category]||'Email'}</span><select class="category-select" id="message-category" aria-label="Categoria della email">${Object.entries(categoryNames).map(([key,name])=>`<option value="${key}" ${key===m.category?'selected':''}>${name}</option>`).join('')}</select><h2>${esc(m.subject)}</h2><div class="sender-detail">${avatar(m)}<div><strong>${esc(m.sender)}</strong><span class="address">&lt;${esc(m.sender_email)}&gt;</span><small>a ${esc(m.recipients)}</small></div><time>${dateLabel(m.date,true)}</time></div><section class="ai-summary"><div class="ai-summary-title">${icon('sparkle')}${analysis?'Il punto, secondo Milo':'Un aiuto per leggere tra le righe'}<button data-action="analyze">${analysis?'Rianalizza':'Analizza'}${icon('arrow')}</button></div><p>${analysis?esc(analysis.summary):'Una sintesi, le cose da fare e la priorità. Quando vuoi, con il modello che hai scelto.'}</p>${analysis?.action_items?.length?`<ul>${analysis.action_items.map(item=>`<li>${esc(item)}</li>`).join('')}</ul>`:''}${analysis?`<p>${esc(analysis.model)} · ${analysis.priority==='high'?'Priorità alta':analysis.priority==='low'?'Priorità bassa':'Priorità normale'}</p>`:''}</section><div class="mail-body">${esc(m.body)}</div>${m.attachments?.length?`<div class="attachments">${m.attachments.map(a=>`<a class="attachment" href="/api/messages/${encodeURIComponent(m.id)}/attachments/${a.index}">${icon('paperclip')}${esc(a.name)}</a>`).join('')}</div>`:''}<div class="reply-actions"><button data-action="reply">${icon('reply')}Rispondi</button><button data-action="forward">${icon('forward')}Inoltra</button><button data-action="ai-reply">${icon('sparkle')}Una mano con la risposta</button></div></article><footer class="mail-footer">${icon('shield')}La tua posta resta nel tuo archivio. Le analisi seguono le tue impostazioni.</footer>`;
}

async function refresh(resetSelection=false) {
  if (!S.status?.authenticated) return;
  S.state=await api('/state');
  if (S.view==='drafts') { S.drafts=(await api('/drafts')).drafts; S.messages=[]; }
  else {
    const params=new URLSearchParams({view:S.view,search:S.search});
    if(S.category && S.view==='inbox') params.set('category',S.category);
    if(S.account) params.set('account',S.account);
    S.messages=(await api('/messages?'+params)).messages;
  }
  if(resetSelection) S.selected=null;
}
async function selectMessage(id,markRead=true) {
  S.selected=await api('/messages/'+encodeURIComponent(id));
  if(markRead && !S.selected.read) {
    await api('/messages/'+id,'PATCH',{read:true}); S.selected.read=1;
    await refresh();
  }
  S.menu=false;
  $('.shell')?.classList.add('has-selection'); $('.shell')?.classList.remove('menu-open');
  renderList();renderReading();
}
async function mutate(patch) {
  if(!S.selected) return;
  const id=S.selected.id;
  const updated=await api('/messages/'+id,'PATCH',patch);
  S.selected={...S.selected,...updated};
  await refresh();
  if ('archived' in patch || 'snoozed_until' in patch) { S.selected=null; $('.shell')?.classList.remove('has-selection'); }
  renderShell();
}

function showSettings(tab=S.settingsTab) {
  S.settingsTab=tab;
  const tabs=`<div class="modal-tabs">${[['accounts','Account'],['ai','Milo AI'],['rules','Filtri'],['devices','Dispositivi']].map(([id,name])=>`<button data-settings-tab="${id}" class="${id===tab?'active':''}">${name}</button>`).join('')}</div>`;
  let body='';
  if(tab==='accounts') {
    body=`<p>Collegali una volta. Gli account sono conservati sul tuo servizio Milo e disponibili agli altri dispositivi.</p>${S.state.accounts.map(a=>`<div class="settings-account"><span class="dot"></span><div><strong>${esc(a.name)}</strong><small>${esc(a.email)}</small></div><span class="health ${a.error?'error':''}">${!a.enabled?'In pausa':a.error?'Da controllare':a.last_sync?'Sincronizzato':'In attesa'}</span><button class="secondary" data-edit-account="${esc(a.id)}">Gestisci</button></div>${a.error?`<p class="form-error">${esc(a.error)}</p>`:''}`).join('')}<div class="form-actions"><button class="primary" data-action="add-account">${icon('plus')}Collega un account</button></div>${S.state.pending?.length?`<div class="notice" style="margin-top:20px">${S.state.pending.map(p=>`${p.count} modifiche ${esc(p.kind)}: ${esc(p.error||'in attesa della prossima sincronizzazione')}`).join('<br>')}</div>`:''}`;
  } else if(tab==='ai') {
    const ai=S.state.ai;
    body=`<form id="ai-form"><p>Analisi, recap e risposte proposte passano da Ollama. Le risposte restano bozze da rivedere e inviare personalmente.</p><label class="field"><span>Modello Ollama</span><input name="model" value="${esc(ai.model)}" required></label><div class="notice"><strong>Mistral Large 4 usa Ollama Cloud.</strong><br>Con <code>mistral-large-4:cloud</code>, il contenuto delle email selezionate viene elaborato nel cloud di Ollama. Puoi scegliere un modello locale già installato.</div><label class="check-field"><input type="checkbox" name="cloud_consent" ${ai.cloud_consent?'checked':''}><span>Consento l’elaborazione delle email con modelli cloud.</span></label><label class="check-field"><input type="checkbox" name="automatic" ${ai.automatic?'checked':''}><span>Analizza automaticamente le nuove email e organizza l’inbox in Persone, Notifiche e Newsletter.</span></label>${S.state.ai_error?`<p class="form-error">${esc(S.state.ai_error)}</p>`:''}<div class="form-actions"><button class="primary" type="submit">Salva preferenze</button></div></form>`;
  } else if(tab==='rules') {
    body=`<p>I tuoi filtri hanno precedenza sulla classificazione AI e vengono applicati anche alle email già salvate.</p>${S.state.rules.map(r=>`<div class="rule-row"><div><strong>${esc(r.name)}</strong>${esc(r.contains)} → ${categoryNames[r.category]}</div><button class="icon-button" data-delete-rule="${esc(r.id)}" aria-label="Elimina filtro">${icon('trash')}</button></div>`).join('')}<form id="rule-form" style="margin-top:22px"><div class="form-grid"><label class="field full"><span>Nome del filtro</span><input name="name" placeholder="Le notifiche di GitHub" required></label><label class="field"><span>Quando</span><select name="field"><option value="sender">Il mittente contiene</option><option value="subject">L’oggetto contiene</option><option value="body">Il testo contiene</option></select></label><label class="field"><span>Questo testo</span><input name="contains" placeholder="github.com" required></label><label class="field full"><span>Sposta nella categoria</span><select name="category">${Object.entries(categoryNames).map(([key,name])=>`<option value="${key}">${name}</option>`).join('')}</select></label></div><div class="form-actions"><button class="primary" type="submit">Crea filtro</button></div></form>`;
  } else {
    body=`<p>Questa è la casa del tuo archivio. Un altro dispositivo che accede allo stesso indirizzo trova account, email, preferenze e bozze già configurati.</p><div class="notice"><strong>Indirizzo del servizio</strong><br>${esc(location.origin)}</div><p>Per accedere da iPhone servirà un indirizzo HTTPS raggiungibile dal telefono. La versione nativa iOS e le notifiche push sono i prossimi passi; questa prima versione parte da Linux.</p><div class="notice">L’archivio email vive sul servizio. Per ora, la lettura richiede la connessione a Milo; la cache offline delle email sul dispositivo è ancora da costruire.</div>${!S.status.demo?'<div class="form-actions"><button class="secondary" data-action="logout">Esci da questo dispositivo</button></div>':''}`;
  }
  showModal('Il tuo Milo',tabs+body);
}

function showAccountForm() {
  if(S.status.demo) { toast('Apri il servizio Milo per collegare la tua posta.'); return; }
  const google=S.state.google;
  const setup=google?.configured?'':`<details class="oauth-help" open><summary>Configura Google una volta per il tuo servizio</summary><ol><li>In <a href="https://console.cloud.google.com/apis/library/gmail.googleapis.com" target="_blank" rel="noopener">Google Cloud</a> abilita Gmail API e configura il consenso OAuth per Milo.</li><li>Crea un client di tipo <strong>Applicazione web</strong> con questo URI di reindirizzamento:<div class="notice callback-url">${esc(google?.redirect_uri||'')}</div></li><li>Scarica il JSON delle credenziali e importalo qui. Se l’app è in Testing, aggiungi i tuoi indirizzi come utenti di test.</li></ol><form id="google-config-form"><label class="field"><span>Credenziali OAuth Google (.json)</span><input type="file" name="credentials" accept=".json,application/json" required></label><div class="form-error" role="alert"></div><div class="form-actions"><button class="primary" type="submit">Configura Google</button></div></form></details>`;
  showModal('Collega la tua posta',`<p>Accedi al tuo account Google e autorizza Milo a leggere, organizzare e inviare la tua posta. Il collegamento resta sul servizio e vale per tutti i tuoi dispositivi.</p><button class="primary google-connect" data-action="google-connect" ${google?.configured?'':'disabled'}>Continua con Google ${icon('arrow')}</button>${setup}<div class="form-actions"><button class="secondary" data-action="imap-account">Collega iCloud o un account IMAP</button></div>`);
}

function showIMAPForm() {
  showModal('Collega un account IMAP',`<form id="account-form"><label class="field"><span>Provider</span><select id="provider"><option value="icloud">iCloud Mail</option><option value="other">Altro account IMAP</option></select></label><div class="notice" id="provider-notice">Usa una password specifica per app generata nel tuo account Apple. Il nome utente IMAP può essere la parte prima di @icloud.com.</div><div class="form-grid"><label class="field"><span>Nome dell’account</span><input name="name" value="Personale" required maxlength="80"></label><label class="field"><span>Indirizzo email</span><input name="email" type="email" required autocomplete="email"></label><label class="field"><span>Nome utente</span><input name="username" placeholder="Di solito l’indirizzo email" required></label><label class="field"><span>Password per app</span><input name="password" type="password" required autocomplete="off"></label><label class="field"><span>Server IMAP</span><input name="imap_host" value="imap.mail.me.com" required></label><label class="field"><span>Porta IMAP (TLS)</span><input name="imap_port" type="number" value="993" min="1" max="65535" required></label><label class="field"><span>Server SMTP</span><input name="smtp_host" value="smtp.mail.me.com" required></label><label class="field"><span>Porta SMTP</span><input name="smtp_port" type="number" value="587" min="1" max="65535" required></label><label class="field full"><span>Sicurezza SMTP</span><select name="smtp_security"><option value="tls">TLS</option><option value="starttls" selected>STARTTLS</option></select></label></div><div class="form-error" role="alert"></div><div class="form-actions"><button class="secondary" type="button" data-action="close-modal">Annulla</button><button class="primary" type="submit">Collega e sincronizza ${icon('arrow')}</button></div></form>`);
}

function showAccountSettings(accountId) {
  const a=S.state.accounts.find(account=>account.id===accountId);
  if(!a) return;
  const imap=a.provider==='imap';
  const connection=imap?`<div class="form-grid"><label class="field"><span>Nome utente</span><input name="username" value="${esc(a.username)}" required></label><label class="field"><span>Nuova password per app</span><input name="password" type="password" autocomplete="new-password" placeholder="Lascia vuoto per conservarla"></label><label class="field"><span>Server IMAP</span><input name="imap_host" value="${esc(a.imap_host)}" required></label><label class="field"><span>Porta IMAP (TLS)</span><input name="imap_port" type="number" value="${a.imap_port}" min="1" max="65535" required></label><label class="field"><span>Server SMTP</span><input name="smtp_host" value="${esc(a.smtp_host)}" required></label><label class="field"><span>Porta SMTP</span><input name="smtp_port" type="number" value="${a.smtp_port}" min="1" max="65535" required></label><label class="field full"><span>Sicurezza SMTP</span><select name="smtp_security"><option value="tls" ${a.smtp_security==='tls'?'selected':''}>TLS</option><option value="starttls" ${a.smtp_security==='starttls'?'selected':''}>STARTTLS</option></select></label></div>`:`<p>L’accesso Google è conservato sul servizio. Se Google lo revoca o scade, ricollega questa casella.</p><button class="secondary" type="button" data-action="google-connect" data-reconnect-account="${esc(a.id)}">Ricollega ${esc(a.email)}</button>`;
  showModal('Gestisci account',`<form id="account-settings-form" data-account-id="${esc(a.id)}"><div class="notice">${esc(a.email)} · ${imap?'IMAP':'Google'}</div><label class="field"><span>Nome dell’account</span><input name="name" value="${esc(a.name)}" required maxlength="80"></label><label class="check-field"><input type="checkbox" name="enabled" ${a.enabled?'checked':''}><span>Sincronizza questa casella. In pausa, le email e le bozze salvate restano disponibili; le modifiche aspettano la ripresa.</span></label>${connection}<div class="form-error" role="alert"></div><div class="form-actions"><button class="secondary" type="button" data-action="close-modal">Annulla</button><button class="primary" type="submit">Salva account</button></div></form>`);
}

function showCompose(draft={}) {
  if(!S.state.accounts.length) { showAccountForm(); return; }
  S.compose=draft;
  showModal(draft.reply_to_id?'Rispondi, con i tuoi tempi.':'Le parole giuste.',`<form id="compose-form"><label class="field"><span>Da</span><select name="account_id">${S.state.accounts.map(a=>`<option value="${esc(a.id)}" ${draft.account_id===a.id?'selected':''}>${esc(a.name)} · ${esc(a.email)}</option>`).join('')}</select></label><label class="field"><span>A</span><input name="to" value="${esc(draft.to)}" placeholder="nome@example.com" maxlength="2000"></label><label class="field"><span>Oggetto</span><input name="subject" value="${esc(draft.subject)}" placeholder="Di cosa parliamo?" maxlength="998"></label><label class="field"><span>Messaggio</span><textarea class="composer-body" name="body" placeholder="Ciao…" maxlength="100000">${esc(draft.body)}</textarea></label><div class="form-error" role="alert"></div><div class="form-actions">${draft.id?'<button class="secondary" type="button" data-action="delete-draft">Elimina bozza</button>':''}<button class="secondary" type="button" data-action="save-draft">Salva bozza</button><button class="primary" type="submit">${icon('sent')}Invia messaggio</button></div><div class="fineprint">La bozza si conserva quando premi Salva o chiudi questa finestra. L’invio avviene solo con il pulsante Invia.</div></form>`,true);
}
async function saveCompose() {
  const form=$('#compose-form'); if(!form) return null;
  const data=Object.fromEntries(new FormData(form));
  if(!data.to && !data.subject && !data.body) return null;
  data.id=S.compose?.id||null; data.reply_to_id=S.compose?.reply_to_id||null;
  const result=await api('/drafts','PUT',data);
  S.compose={...data,id:result.id}; return result.id;
}

async function runAI(action,button) {
  if(S.status.demo) { toast('Le funzioni AI si attivano sulla tua posta reale. Questa demo non simula analisi.'); return; }
  if(!S.state.ai.cloud_consent && S.state.ai.model?.includes('cloud')) { showSettings('ai'); toast('Scegli come elaborare la tua posta prima di attivare l’AI.'); return; }
  const id=S.selected?.id;
  if(action==='recap') showModal('La tua inbox, in un minuto.',`<div class="loading spinner">${icon('refresh')}<p>Milo sta leggendo le conversazioni recenti…</p></div>`);
  else if(button) { button.disabled=true; }
  try {
    if(action==='recap') {
      const result=await api('/recap','POST');
      showModal('Il punto della tua inbox',`<p class="recap-overview">${esc(result.overview)}</p>${result.priorities.map(p=>`<button class="priority-item" data-recap-message="${esc(p.message_id)}">${icon('check')}<span>${esc(p.action)}</span>${icon('arrow')}</button>`).join('')}<p class="fineprint">${result.message_ids.length} email recenti · ${esc(result.model||'')} · Verifica sempre le indicazioni sulle email originali.</p>`);
    } else if(action==='analyze') {
      await api('/messages/'+id+'/analyze','POST');
      if(S.selected?.id===id) { S.selected=await api('/messages/'+id); renderReading(); }
      await refresh();renderList();
    } else {
      const m=S.selected;
      const result=await api('/messages/'+id+'/reply','POST');
      showCompose({account_id:m.account_id,to:m.sender_email,subject:/^re:/i.test(m.subject)?m.subject:'Re: '+m.subject,body:result.body,reply_to_id:id});
    }
  } catch(error) { if(action==='recap') closeModal(); toast(error.message); }
  finally { if(button) button.disabled=false; }
}

document.addEventListener('click', async event => {
  const target=event.target.closest('button,a'); if(!target) return;
  try {
    if(target.dataset.view) {
      S.view=target.dataset.view; S.category=''; S.selected=null; S.menu=false;
      await refresh(true); renderShell(); return;
    }
    if('category' in target.dataset) { S.category=target.dataset.category; S.selected=null; await refresh(true);renderShell();return; }
    if(target.dataset.account) { S.account=S.account===target.dataset.account?'':target.dataset.account; await refresh(true);renderShell();return; }
    if(target.dataset.message) { await selectMessage(target.dataset.message); return; }
    if(target.dataset.draft) { showCompose(S.drafts.find(d=>d.id===target.dataset.draft)); return; }
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
    if(action==='back') { S.selected=null;$('.shell').classList.remove('has-selection');renderList();renderReading(); }
    if(action==='star') await mutate({starred:!S.selected.starred});
    if(action==='read') await mutate({read:!S.selected.read});
    if(action==='archive') { await mutate({archived:!S.selected.archived});toast('Modifica salvata. Milo la sincronizza con il provider.'); }
    if(action==='snooze') showModal('Un momento migliore.',`<p>La conversazione torna nella tua inbox quando arriva il momento.</p><div class="form-actions"><button class="secondary" data-snooze="${Date.now()/1000+3600}">Tra un’ora</button><button class="primary" data-snooze="${Date.now()/1000+86400}">Domani</button></div>`);
    if(target.dataset.snooze) { await mutate({snoozed_until:Number(target.dataset.snooze)});closeModal();toast('Email messa da parte.'); }
    if(action==='reply') { const m=S.selected;showCompose({account_id:m.account_id,to:m.sender_email,subject:/^re:/i.test(m.subject)?m.subject:'Re: '+m.subject,reply_to_id:m.id}); }
    if(action==='forward') { const m=S.selected;showCompose({account_id:m.account_id,subject:'Fwd: '+m.subject,body:`\n\n---------- Messaggio inoltrato ----------\nDa: ${m.sender} <${m.sender_email}>\nOggetto: ${m.subject}\n\n${m.body}`}); }
    if(action==='save-draft') { if(await saveCompose()) { await refresh();renderList();toast('Bozza salvata nel tuo archivio.'); } }
    if(action==='delete-draft') { await api('/drafts/'+S.compose.id,'DELETE');closeModal();await refresh();renderShell();toast('Bozza eliminata.'); }
    if(action==='close-modal') { if($('#compose-form')) await saveCompose();closeModal();await refresh();renderList(); }
    if(action==='sync') {
      if(S.syncing) return;S.syncing=true;target.classList.add('spinner');target.disabled=true;
      try { const result=await api('/sync','POST');await refresh();renderShell();toast(result.results.some(r=>!r.ok)?'Sincronizzazione incompleta. Controlla gli account.':S.status.demo?'Demo aggiornata.':!result.results.length?'Nessuna casella attiva da sincronizzare.':'Posta sincronizzata.'); }
      finally { S.syncing=false;target.classList.remove('spinner');target.disabled=false; }
    }
    if(action==='retry-login') { await boot(); }
    if(action==='logout') { await api('/logout','POST');S.status.authenticated=false;S.selected=null;S.messages=[];renderLogin(); }
  } catch(error) { toast(error.message); }
});

document.addEventListener('submit', async event => {
  event.preventDefault(); const form=event.target;
  const button=form.querySelector('button[type="submit"]'); if(button) button.disabled=true;
  const errorBox=form.querySelector('.form-error');if(errorBox) errorBox.textContent='';
  try {
    const data=Object.fromEntries(new FormData(form));
    if(form.id==='login-form') {
      await api(S.status.initialized?'/login':'/setup','POST',data);S.status=await api('/status');await refresh();renderShell();
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
      await refresh();renderShell();showSettings('accounts');toast('Account aggiornato su Milo.');
    }
    if(form.id==='ai-form') {
      data.automatic=form.elements.automatic.checked;data.cloud_consent=form.elements.cloud_consent.checked;
      await api('/settings/ai','PUT',data);await refresh();closeModal();toast('Preferenze AI salvate.');
    }
    if(form.id==='rule-form') { await api('/rules','POST',data);await refresh();showSettings('rules');renderList();toast('Filtro creato e applicato.'); }
    if(form.id==='compose-form') {
      const id=await saveCompose();if(!id) throw new Error('Scrivi prima il tuo messaggio.');
      await api('/drafts/'+id+'/send','POST');closeModal();await refresh();renderShell();toast('Messaggio inviato.');
    }
  } catch(error) { if(errorBox) errorBox.textContent=error.message;else toast(error.message); }
  finally { if(button) button.disabled=false; }
});

document.addEventListener('input', event => {
  if(event.target.id==='search-input') {
    S.search=event.target.value;clearTimeout(searchTimer);
    searchTimer=setTimeout(async()=>{try{await refresh();renderList();}catch(error){toast(error.message);}},200);
  }
  if(event.target.name==='email' && $('#account-form')) $('#account-form').elements.username.value=event.target.value;
});
document.addEventListener('change', async event => {
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
    try { if($('#compose-form')) await saveCompose();closeModal();S.menu=false;$('.shell')?.classList.remove('menu-open'); }
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
    S.status=await api('/status');
    if(!S.status.initialized) {
      if(ownerToken) {
        try { await api('/setup/authorize','POST',{token:ownerToken}); }
        catch(error) { if(error.status!==403) throw error;toast(error.message); }
      }
      S.setupAuthorized=(await api('/setup/status')).authorized;
    }
    if(oauthError) toast(oauthError);
    if(connected) toast('Casella Google collegata. Sto sincronizzando la tua posta.');
    if(!S.status.authenticated) { renderLogin();return; }
    await refresh();renderShell();
    if(S.status.demo && S.messages.length && innerWidth>900) await selectMessage(S.messages[0].id,false);
  } catch(error) { $('#app').innerHTML=`<div class="empty" style="min-height:100vh">${icon('mail')}<h3>Milo non è raggiungibile.</h3><p>${esc(error.message)}</p></div>`; }
}
setInterval(async()=>{
  if(!S.status?.authenticated || S.syncing || document.hidden) return;
  try {
    await refresh();renderChrome();renderList();
    const id=S.selected?.id;
    if(id) {
      try {
        const selected=await api('/messages/'+encodeURIComponent(id));
        if(S.selected?.id===id && JSON.stringify(selected)!==JSON.stringify(S.selected)) {
          S.selected=selected;renderReading();
        }
      } catch(error) {
        if(error.status===404 && S.selected?.id===id) {
          S.selected=null;$('.shell')?.classList.remove('has-selection');renderReading();
        } else throw error;
      }
    }
  }
  catch { renderList(); }
},30000);
if('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(()=>{});
boot();
