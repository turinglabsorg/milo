// Device-local, origin-isolated cache. Provider tokens never enter this database.
// Ask the browser to keep this origin's storage instead of treating it as
// evictable: granted to installed/high-engagement apps on Chromium and to
// home-screen apps on iOS, where IndexedDB is the shared local store.
if (typeof navigator !== 'undefined' && navigator.storage?.persist) {
  navigator.storage.persist().catch(() => {});
}
const memory=new Map();
const sizes=new Map(),versions=new Map();
let memoryBytes=0,generation=0;
function remember(id,value,size){
  memoryBytes-=sizes.get(id)||0;memory.delete(id);sizes.delete(id);
  if(size>16*1024*1024)return;
  memory.set(id,value);sizes.set(id,size);memoryBytes+=size;
  while(memoryBytes>16*1024*1024){const oldest=memory.keys().next().value;memoryBytes-=sizes.get(oldest)||0;memory.delete(oldest);sizes.delete(oldest);}
}
let opening,keyPromise;
function database(){
  return opening??=new Promise((resolve,reject)=>{
    const request=indexedDB.open('milo-device-cache',1);
    request.onupgradeneeded=()=>request.result.createObjectStore('records',{keyPath:'id'});
    request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);
  });
}
async function rawGet(id){
  const db=await database();
  return new Promise((resolve,reject)=>{const request=db.transaction('records').objectStore('records').get(id);request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});
}
async function encryptionKey(){
  return keyPromise??=(async()=>{
    const existing=await rawGet('crypto-key');if(existing)return existing.key;
    const proposed=await crypto.subtle.generateKey({name:'AES-GCM',length:256},false,['encrypt','decrypt']);
    const db=await database();
    return new Promise((resolve,reject)=>{
      const tx=db.transaction('records','readwrite'),store=tx.objectStore('records'),request=store.get('crypto-key');let saved;
      request.onsuccess=()=>{saved=request.result?.key||proposed;if(!request.result)store.put({id:'crypto-key',key:saved});};
      tx.oncomplete=()=>resolve(saved);tx.onabort=()=>reject(tx.error);
    });
  })();
}
async function get(id){
  if(memory.has(id)){const value=memory.get(id);memory.delete(id);memory.set(id,value);return value;}
  const epoch=generation,version=versions.get(id)||0;
  try{
    const record=await rawGet(id);
    if(epoch!==generation)return null;
    if(version!==(versions.get(id)||0))return get(id);
    if(!record?.data)return null;
    const bytes=await crypto.subtle.decrypt({name:'AES-GCM',iv:record.iv},await encryptionKey(),record.data);
    if(epoch!==generation)return null;
    if(version!==(versions.get(id)||0))return get(id);
    const value=JSON.parse(new TextDecoder().decode(bytes));remember(id,value,bytes.byteLength);return value;
  }catch{return null;}
}
async function set(id,value){
  const epoch=generation,version=(versions.get(id)||0)+1;versions.set(id,version);
  const plain=new TextEncoder().encode(JSON.stringify(value));remember(id,value,plain.byteLength);
  try{
    const db=await database(),iv=crypto.getRandomValues(new Uint8Array(12));
    const data=await crypto.subtle.encrypt({name:'AES-GCM',iv},await encryptionKey(),plain);
    if(epoch!==generation)return false;
    if(version!==versions.get(id))return true;
    return await new Promise((resolve,reject)=>{const tx=db.transaction('records','readwrite');tx.objectStore('records').put({id,data,iv,updated:Date.now()});tx.oncomplete=()=>resolve(true);tx.onabort=()=>reject(tx.error);});
  }catch{return false;}
}
async function remove(id){
  versions.set(id,(versions.get(id)||0)+1);
  memoryBytes-=sizes.get(id)||0;sizes.delete(id);memory.delete(id);
  try{const db=await database();await new Promise((resolve,reject)=>{const tx=db.transaction('records','readwrite');tx.objectStore('records').delete(id);tx.oncomplete=resolve;tx.onabort=()=>reject(tx.error);});}catch{}
}
async function clear(){
  generation++;memory.clear();sizes.clear();versions.clear();memoryBytes=0;keyPromise=null;
  try{const db=await database();await new Promise((resolve,reject)=>{const tx=db.transaction('records','readwrite');tx.objectStore('records').clear();tx.oncomplete=resolve;tx.onabort=()=>reject(tx.error);});}catch{}
}
async function has(id){
  if(memory.has(id))return true;
  try{const db=await database();return await new Promise((resolve,reject)=>{const r=db.transaction('records').objectStore('records').count(id);r.onsuccess=()=>resolve(r.result>0);r.onerror=()=>reject(r.error);});}catch{return false;}
}
async function keys(prefix){
  try{
    const db=await database();
    return await new Promise((resolve,reject)=>{const r=db.transaction('records').objectStore('records').getAllKeys();r.onsuccess=()=>resolve(r.result.filter(id=>id.startsWith(prefix)));r.onerror=()=>reject(r.error);});
  }catch{return [];}
}
async function setAsset(id,response){
  if(Number(response.headers.get('content-length'))>16*1024*1024){response.body?.cancel().catch(()=>{});return;}
  const source=await response.arrayBuffer();if(source.byteLength>16*1024*1024)return;
  const headers=Object.fromEntries(['content-type','content-disposition'].map(name=>[name,response.headers.get(name)]).filter(([,value])=>value));
  const encoded=new TextEncoder().encode(JSON.stringify(headers)),plain=new Uint8Array(4+encoded.length+source.byteLength);
  new DataView(plain.buffer).setUint32(0,encoded.length);plain.set(encoded,4);plain.set(new Uint8Array(source),4+encoded.length);
  const iv=crypto.getRandomValues(new Uint8Array(12)),data=await crypto.subtle.encrypt({name:'AES-GCM',iv},await encryptionKey(),plain);
  const db=await database();await new Promise((resolve,reject)=>{const tx=db.transaction('records','readwrite');tx.objectStore('records').put({id:'asset:'+id,data,iv,updated:Date.now()});tx.oncomplete=resolve;tx.onabort=()=>reject(tx.error);});
}
async function getAsset(id){
  try{
    const record=await rawGet('asset:'+id);if(!record)return null;
    const plain=await crypto.subtle.decrypt({name:'AES-GCM',iv:record.iv},await encryptionKey(),record.data),length=new DataView(plain).getUint32(0);
    const headers=JSON.parse(new TextDecoder().decode(plain.slice(4,4+length)));
    return new Response(plain.slice(4+length),{status:200,headers});
  }catch{return null;}
}
let operations=Promise.resolve();
function enqueue(operation){
  const next=operations.then(async()=>{const queue=await get('pending-operations')||[];const nextQueue=queue.filter(item=>!item.error||item.key!==operation.key);nextQueue.push(operation);if(!await set('pending-operations',nextQueue))throw new Error('Impossibile salvare la modifica sul dispositivo. Mantieni Milo aperto e riconnettiti.');});
  operations=next.catch(()=>{});return next;
}
function acknowledge(id){
  const next=operations.then(async()=>{const queue=await get('pending-operations')||[];if(!await set('pending-operations',queue.filter(item=>item.id!==id)))throw new Error('Impossibile confermare la modifica sul dispositivo.');});
  operations=next.catch(()=>{});return next;
}
function markFailed(id,error){
  const next=operations.then(async()=>{const queue=await get('pending-operations')||[];if(!await set('pending-operations',queue.map(item=>item.id===id?{...item,error}:item)))throw new Error('Impossibile salvare lo stato della sincronizzazione.');});
  operations=next.catch(()=>{});return next;
}
function retryOperations(){
  const next=operations.then(async()=>{const queue=await get('pending-operations')||[];if(!await set('pending-operations',queue.map(({error,...item})=>item)))throw new Error('Cache locale non disponibile.');});
  operations=next.catch(()=>{});return next;
}
export const deviceCache={get,set,remove,clear,keys,has,enqueue,acknowledge,markFailed,retryOperations,setAsset,getAsset};
