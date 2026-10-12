import {deviceCache} from './cache.js';

function index(data){
  const terms=[...new Set(data.body.toLowerCase().match(/[\p{L}\p{N}@._-]+/gu)||[])];
  self.postMessage({key:data.key,id:data.id,version:data.version,terms});
}
self.addEventListener('message',async event=>{
  if(event.data.action==='scan'){
    for(const path of await deviceCache.keys('api:/messages/')){
      if(!/^api:\/messages\/[^/?]+(?:\?.*)?$/.test(path))continue;
      const message=await deviceCache.get(path);if(!message?.body)continue;
      index({key:message.account_id+':'+(message.thread_id||message.id),id:message.id,version:message.content_version,body:message.body});
    }
  }else index(event.data);
});
