import {deviceCache} from './cache.js';

const rows=new Map(),searches=new Map(),changes=new Map(),pending=new Map(),indexing=new Set(),observed=new Map();
const key=m=>m.account_id+':'+(m.thread_id||m.id);
let ready,timer,worker,available=false,writing=Promise.resolve();
let revision=0;
let changed=()=>{};
const versions=new Map();
function persist(){
  clearTimeout(timer);timer=setTimeout(commit,100);
}
function commit(){clearTimeout(timer);return writing=writing.catch(()=>{}).then(()=>deviceCache.set('mailbox-replica',{rows:[...rows.values()],searches:[...searches]}));}
function normalize(row,view='all'){
  const previous=rows.get(key(row));
  return {...previous,...row,
    has_inbox:row.has_inbox??(view==='inbox'||previous?.has_inbox||!row.sent&&!row.archived),
    has_archive:row.has_archive??(view==='archive'||previous?.has_archive||!row.sent&&row.archived),
    has_sent:row.has_sent??(view==='sent'||row.sent||previous?.has_sent||row.replied),
    deleted:false,search_terms:previous?.search_terms||[],search_entries:previous?.search_entries||{}};
}
async function init(){
  return ready??=(async()=>{
    const saved=await deviceCache.get('mailbox-replica');
    if(saved){available=true;for(const row of saved.rows)rows.set(key(row),row);for(const [path,ids] of saved.searches||[])searches.set(path,ids);}
    else for(const path of await deviceCache.keys('api:/messages?')){
      const cached=await deviceCache.get(path);if(!cached?.messages)continue;
      const query=new URLSearchParams(path.split('?')[1]);merge(cached.messages,query.get('view')||'all');
      if(query.get('search'))searches.set(path.slice(4),cached.messages.map(key));
    }
    startWorker();
  })();
}
function merge(messages,view='all',started=revision,ticket=0){
  available=true;
  for(const row of messages){const id=key(row);if(pending.has(id)||(changes.get(id)||0)>started||(observed.get(id)||0)>ticket)continue;observed.set(id,ticket);rows.set(id,normalize(row,view));observe([row]);}
  persist();
}
function patchRow(row,patch,deleted){
  const next={...row,...patch};
  if(deleted)next.deleted=true;
  const received=row.received_count??Number(Boolean(row.has_inbox||row.has_archive));
  if('archived' in patch){next.has_archive=Boolean(patch.archived)&&received>0;next.has_inbox=!patch.archived&&received>0&&!(next.snoozed_until>Date.now()/1000);}
  if('snoozed_until' in patch)next.has_inbox=!next.archived&&received>0&&!(patch.snoozed_until>Date.now()/1000);
  if('read' in patch)next.unread_count=patch.read?0:(row.received_count||row.message_count||1);
  if('read' in patch)next.inbox_unread_count=patch.read?0:(row.inbox_count||0);
  return next;
}
function apply(operation){
  revision++;
  pending.set(operation.key,operation.id);
  const row=rows.get(operation.key);if(row)rows.set(operation.key,patchRow(row,operation.patch||{},operation.deleted));
  changes.set(operation.key,revision);persist();
}
function confirm(operation){revision++;changes.set(operation.key,revision);if(pending.get(operation.key)===operation.id)pending.delete(operation.key);}
function rememberQuery(path,messages){if(new URLSearchParams(path.split('?')[1]).get('search'))searches.set(path,messages.map(key));persist();}
function select(query,path,optimistic){
  const term=query.search.trim().toLowerCase(),known=new Set(searches.get(path)||[]),now=Date.now()/1000;
  const words=term.match(/[\p{L}\p{N}@._-]+/gu)||[];
  return [...rows.values()].map(row=>{const op=optimistic.get(key(row));return op?patchRow(row,op.patch||{},op.deleted):row;}).filter(row=>{
    if(row.deleted||query.account&&row.account_id!==query.account)return false;
    if(query.category&&query.view==='inbox'&&row.category!==query.category)return false;
    if(query.view==='inbox'&&(!(row.has_inbox||row.snoozed_until&&row.snoozed_until<=now&&!row.archived&&row.received_count)||row.snoozed_until>now))return false;
    if(query.view==='archive'&&!row.has_archive)return false;
    if(query.view==='sent'&&!row.has_sent)return false;
    if(query.view==='starred'&&!row.starred)return false;
    if(query.view==='snoozed'&&!(row.snoozed_until>now))return false;
    return !term||known.has(key(row))||[row.sender,row.sender_email,row.subject,row.preview].join(' ').toLowerCase().includes(term)
      ||words.length>0&&words.every(word=>(row.search_terms||[]).some(token=>token.includes(word)));
  }).sort((a,b)=>(b.pinned||0)-(a.pinned||0)||b.date-a.date).slice(0,100);
}
function startWorker(){
  if(worker)return worker;
  try{
    worker=new Worker('/static/search-worker.js',{type:'module'});
    worker.onmessage=async event=>{
      indexing.delete(event.data.id+':'+event.data.version);
      const row=rows.get(event.data.key);if(!row||row.deleted)return;
      const expected=versions.get(event.data.id)??(row.id===event.data.id?row.content_version:null);
      if(expected&&expected!==event.data.version)return;
      const entries={...row.search_entries,[event.data.id]:{version:event.data.version,terms:event.data.terms}};
      rows.set(event.data.key,{...row,search_entries:entries,search_terms:[...new Set(Object.values(entries).flatMap(value=>value.terms))]});
      await commit();changed();
    };
    worker.onerror=()=>{worker?.terminate();worker=null;};
    worker.postMessage({action:'scan'});
  }catch{worker=null;}
  return worker;
}
function observe(messages){
  for(const message of messages){
    if(!message.content_version)continue;
    versions.set(message.id,message.content_version);
    const row=rows.get(key(message)),entry=row?.search_entries?.[message.id];
    if(entry&&entry.version!==message.content_version){
      const entries={...row.search_entries};delete entries[message.id];
      rows.set(key(message),{...row,search_entries:entries,search_terms:[...new Set(Object.values(entries).flatMap(value=>value.terms))]});persist();
    }
  }
}
function body(message){
  if(!message.body)return;
  const tag=message.id+':'+message.content_version,row=rows.get(key(message));
  observe([message]);
  if(indexing.has(tag)||row?.search_entries?.[message.id]?.version===message.content_version)return;
  const active=startWorker();if(active){indexing.add(tag);active.postMessage({key:key(message),id:message.id,version:message.content_version,body:message.body});}
}
function remove(id){const row=rows.get(id);if(row&&!pending.has(id)){revision++;rows.set(id,{...row,deleted:true});changes.set(id,revision);persist();}}
function clear(){rows.clear();searches.clear();changes.clear();pending.clear();indexing.clear();observed.clear();versions.clear();available=false;revision++;clearTimeout(timer);worker?.terminate();worker=null;}
export const replica={init,merge,apply,confirm,commit,select,rememberQuery,body,observe,clear,remove,find:id=>rows.get(id),keys:()=>[...rows.keys()].filter(id=>!rows.get(id).deleted),
  get revision(){return revision;},get size(){return rows.size;},get available(){return available;},onChange(callback){changed=callback;}};
