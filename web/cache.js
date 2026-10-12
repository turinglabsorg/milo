// Device-local, origin-isolated cache. Provider tokens never enter this database.
const memory=new Map();
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
  if(memory.has(id))return memory.get(id);
  try{
    const record=await rawGet(id);if(!record?.data)return null;
    const bytes=await crypto.subtle.decrypt({name:'AES-GCM',iv:record.iv},await encryptionKey(),record.data);
    const value=JSON.parse(new TextDecoder().decode(bytes));memory.set(id,value);return value;
  }catch{return null;}
}
async function set(id,value){
  memory.set(id,value);
  try{
    const db=await database(),iv=crypto.getRandomValues(new Uint8Array(12));
    const data=await crypto.subtle.encrypt({name:'AES-GCM',iv},await encryptionKey(),new TextEncoder().encode(JSON.stringify(value)));
    return await new Promise((resolve,reject)=>{const tx=db.transaction('records','readwrite');tx.objectStore('records').put({id,data,iv,updated:Date.now()});tx.oncomplete=()=>resolve(true);tx.onabort=()=>reject(tx.error);});
  }catch{return false;}
}
async function remove(id){
  memory.delete(id);
  try{const db=await database();await new Promise((resolve,reject)=>{const tx=db.transaction('records','readwrite');tx.objectStore('records').delete(id);tx.oncomplete=resolve;tx.onabort=()=>reject(tx.error);});}catch{}
}
async function clear(){
  memory.clear();keyPromise=null;
  try{const db=await database();await new Promise((resolve,reject)=>{const tx=db.transaction('records','readwrite');tx.objectStore('records').clear();tx.oncomplete=resolve;tx.onabort=()=>reject(tx.error);});}catch{}
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
  const next=operations.then(async()=>{const queue=await get('pending-operations')||[];queue.push(operation);if(!await set('pending-operations',queue))throw new Error('Impossibile salvare la modifica sul dispositivo. Mantieni Milo aperto e riconnettiti.');});
  operations=next.catch(()=>{});return next;
}
function acknowledge(id){
  const next=operations.then(async()=>{const queue=await get('pending-operations')||[];await set('pending-operations',queue.filter(item=>item.id!==id));});
  operations=next.catch(()=>{});return next;
}
export const deviceCache={get,set,remove,clear,enqueue,acknowledge,setAsset,getAsset};
