'use strict';
// Tab-local read cache. Never persist business data or authentication credentials.
class YifunReadCache {
 constructor({freshMs=30000,staleMs=120000,maxEntries=80,now=()=>Date.now()}={}){Object.assign(this,{freshMs,staleMs,maxEntries,now});this.entries=new Map();this.pending=new Map();this.epoch=0;}
 clear(){this.epoch++;this.entries.clear();this.pending.clear();}
 load(key,loader){
  if(this.pending.has(key))return this.pending.get(key);
  const epoch=this.epoch;
  const task=Promise.resolve().then(loader).then(value=>{if(epoch===this.epoch){this.entries.delete(key);this.entries.set(key,{at:this.now(),value:structuredClone(value)});while(this.entries.size>this.maxEntries)this.entries.delete(this.entries.keys().next().value);}return value;}).finally(()=>{if(this.pending.get(key)===task)this.pending.delete(key);});
  this.pending.set(key,task);return task;
 }
 async read(key,loader,{onUpdate,onError}={}){
  const cached=this.entries.get(key),age=cached?this.now()-cached.at:Infinity;
  if(age<this.staleMs){
   if(age>=this.freshMs){const epoch=this.epoch;this.load(key,loader).then(()=>{if(epoch===this.epoch)onUpdate?.();}).catch(error=>{if(epoch===this.epoch){this.entries.delete(key);onError?.(error);}});}
   return structuredClone(cached.value);
  }
  return structuredClone(await this.load(key,loader));
 }
}
globalThis.YifunReadCache=YifunReadCache;
