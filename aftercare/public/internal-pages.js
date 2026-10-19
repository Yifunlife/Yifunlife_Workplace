(()=>{
 const ctx=window.__AFTERCARE_CONTEXT__,source=ctx.internal||{items:[],records:[]};
 const scope=new Set(ctx.projects.map(p=>p.id)),items=source.items.filter(d=>scope.has(d.projectId));
 const records=source.records.filter(r=>scope.has(r.projectId)),versions=new Map(records.map(r=>[r.kind+':'+r.id,r.version]));
 const baseline=new Map(),providers=new Map();let timer,saving=false,blocked=false;
 const copy=v=>JSON.parse(JSON.stringify(v));
 const state={installation:[],finance:{orders:[],services:[],rows:[]},warehouse:[]};
 const key=d=>d.projectId+'::'+(d.order||'');
 const tickets=()=>{const live=window.__yifunWorkflow?.records?.()||[];return [...new Map([...items,...live].map(d=>[d.id,d])).values()].filter(d=>scope.has(d.projectId)&&d.submitted!==false)};
 function ticket(id){return tickets().find(d=>d.id===id||d.workNo===id)}
 function ensure(d){
  if(d.submitted===false)return;
  let index=state.finance.orders.findIndex(o=>o.id===key(d));if(index<0){index=state.finance.orders.length;state.finance.orders.push({id:key(d),displayNo:d.order||'原订单待关联',name:d.project,status:'处理中',missing:[],projectId:d.projectId})}
  if(!state.finance.services.some(s=>s.ticketId===d.id))state.finance.services.push({id:d.workNo||d.id,ticketId:d.id,order:index,date:d.reported||'',reason:d.issue,person:d.trackingOwner||d.owner||'',status:d.stage==='已关闭'?'售后结束':d.stage,missing:[],projectId:d.projectId});
  const stored=records.find(r=>r.kind==='installation'&&r.id===d.id);
  if(!state.installation.some(o=>o.id===d.id)&&(stored||['现场处理','客户验收','负责人复核','已关闭'].includes(d.stage))){
   const install=d.method!=='客户自行处理';
   const defaults={id:d.id,ticketId:d.id,projectId:d.projectId,orderId:key(d),project:d.project,customer:d.customer,kind:'售后上门',install,status:install?'待排期':'待收货登记',owner:d.installer||'',team:'',servicePerson:d.trackingOwner||d.owner||'',servicePhone:'',contact:d.contact||'',customerPhone:d.phone||'',address:d.address||'',sales:d.sales||'',engineer:d.engineer||'',start:'',end:'',mode:'all',from:'',to:'',overnight:false,scope:d.review?.method||d.issue||'',ready:false,goods:'到货及进场条件待核对',eta:'',presence:'absent',signer:'',absentReason:'',actual:'',notes:'',finished:false,receiver:'',received:'',method:'',receiptNotes:'',items:[{id:'ITEM-'+d.id,name:d.product||'售后处理',content:d.review?.method||d.issue||'',state:'待处理',note:'',samples:[]}],photos:{},signature:{strokes:[]}};
   state.installation.push({...defaults,...copy(stored?.value||{}),projectId:d.projectId,ticketId:d.id});
  }
 }
 items.forEach(ensure);
 for(const r of records.filter(r=>r.kind==='finance')){
  const d=ticket(r.ticketId);if(!d)continue;const index=state.finance.orders.findIndex(o=>o.id===key(d));const service=state.finance.services.find(s=>s.ticketId===d.id);
  state.finance.rows.push({...copy(r.value),id:r.id,order:index,service:service.id,ticketId:d.id,projectId:d.projectId});
 }
 // Existing procurement and production declarations already live in the service record.
 // Show those declarations as pending checks; no group finance ledger is modified.
 for(const d of items)for(const [cat,p]of [['采购',d.purchase],['生产',d.production]]){
  if(!Number.isSafeInteger(p?.amountCents)||state.finance.rows.some(r=>r.id==='DEPT-'+cat+'-'+d.id))continue;
  const service=state.finance.services.find(s=>s.ticketId===d.id);if(!service)continue;
  state.finance.rows.push({id:'DEPT-'+cat+'-'+d.id,order:service.order,service:service.id,ticketId:d.id,projectId:d.projectId,date:p.completedAt||d.reported,cat,name:d.product||d.issue,basis:cat==='采购'?'采购处理填报':'新增生产加工费',amount:p.amountCents,paid:0,payer:'公司',person:p.buyer||d.owner||'待登记',source:cat+'/'+(d.workNo||d.id),review:'待核对',voucher:'部门填报 · 凭证待补充'});
 }
 function status(text,error=false){let el=document.getElementById('aftersales-internal-status');if(!el){el=document.createElement('div');el.id='aftersales-internal-status';el.setAttribute('role','status');document.getElementById('yw-after-sales')?.querySelector('main')?.prepend(el);}el.textContent=text;el.dataset.error=String(error);}
 function normalize(value){const v=copy(value);delete v.order;delete v.service;delete v.cloudVersion;return v;}
 function register(kind,id,get,set){const k=kind+':'+id;providers.set(k,{kind,id,get,set});if(!baseline.has(k))baseline.set(k,JSON.stringify(normalize(get())));}
 function track(kind,id,get,set){const k=kind+':'+id;if(!providers.has(k)){providers.set(k,{kind,id,get,set});baseline.set(k,'');}else providers.set(k,{kind,id,get,set});clearTimeout(timer);timer=setTimeout(flush,300);}
 async function upload(wid,file){const form=new FormData();form.append('files',file,file.name||'现场照片.png');const r=await fetch('/api/aftercare/internal-files/'+encodeURIComponent(wid),{method:'POST',body:form});const j=await r.json();if(!r.ok)throw Error(j.error||'附件未上传');return j.files[0];}
 async function media(wid,value){if(Array.isArray(value)){for(let i=0;i<value.length;i++)value[i]=await media(wid,value[i]);return value;}if(value&&typeof value==='object'){
  if(typeof value.url==='string'&&value.url.startsWith('blob:')){const blob=await(await fetch(value.url)).blob();return {...value,...await upload(wid,new File([blob],value.name||'现场照片.png',{type:blob.type}))};}
  for(const k of Object.keys(value))value[k]=await media(wid,value[k]);
 }return value;}
 async function flush(){if(saving||blocked||ctx.readOnly||ctx.user.role==='负责人')return;saving=true;let failed=false;try{
  for(const [k,p]of providers){let v=normalize(p.get());const submitted=JSON.stringify(v);if(submitted===baseline.get(k))continue;
   const d=ticket(v.ticketId||p.id);if(!d)throw Error('请先保存关联售后工单，再登记内部处理资料。');
   status('售后内部资料正在保存…');v=await media(d.id,v);
   const r=await fetch('/api/aftercare/internal-pages',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:p.kind,id:p.id,ticketId:d.id,version:versions.get(k)||0,value:v})});const j=await r.json();if(!r.ok){if(r.status===409)blocked=true;throw Error(j.error||'资料未保存');}
   versions.set(k,j.version);baseline.set(k,JSON.stringify(normalize(j.value)));if(JSON.stringify(normalize(p.get()))===submitted)p.set(j.value);
   if(p.kind==='installation'&&j.value.status==='售后结束'){const updated=await(await fetch('/api/aftercare/work-items')).json();const row=updated.items?.find(d=>d.id===p.id);if(row)window.__yifunWorkflow?.syncRecord?.(row);}
  }
  status('售后内部资料已保存至云端');
 }catch(e){failed=true;status(e.message+' 当前更改尚未保存，请勿关闭页面。',true);}finally{saving=false;if(!failed&&[...providers].some(([k,p])=>JSON.stringify(normalize(p.get()))!==baseline.get(k)))timer=setTimeout(flush,300);}}
 function financeTicket(r,services){return ticket(r.ticketId)||ticket(services.find(s=>s.id===r.service)?.ticketId)||ticket(r.service)}
 function financeValue(r,services){const d=financeTicket(r,services);return {...r,ticketId:d?.id,projectId:d?.projectId};}
 window.__AFTERCARE_INTERNAL__={state,
  registerInstallation(get,set){for(const o of state.installation)register('installation',o.id,()=>get(o.id),v=>set(o.id,v));},
  saveInstallation(get,set){for(const o of state.installation)track('installation',o.id,()=>get(o.id),v=>set(o.id,v));},
  registerFinance(get){const s=get();for(const r of s.rows)register('finance',r.id,()=>financeValue(r,get().services),v=>Object.assign(r,v,{order:r.order,service:r.service}));},
  saveFinance(get){const s=get();for(const r of s.rows)track('finance',r.id,()=>financeValue(r,get().services),v=>Object.assign(r,v,{order:r.order,service:r.service}));},
  canonicalCost(entry){const d=ticket(entry.serviceId);if(!d)return entry;ensure(d);return {...entry,orderId:key(d),serviceId:d.workNo||d.id,source:entry.source+'/'+entry.category};},
  refresh(){tickets().forEach(ensure);window.__yifunHub?.shared?.finance?.refresh?.();},
  upload,flush,status
 };
 document.addEventListener('submit',async e=>{const form=e.target;if(!form.matches('#finance-v1 [data-form="entry"]')||form.dataset.cloudVoucherReady)return;const f=form.elements.voucher.files[0];if(!f)return;e.preventDefault();e.stopImmediatePropagation();try{const r={order:Number(form.dataset.order),service:form.dataset.service};const d=financeTicket(r,state.finance.services);if(!d)throw Error('找不到关联售后单');status('正在保存售后费用凭证…');const file=await upload(d.id,f);form.dataset.cloudVoucherUrl=file.url;form.dataset.cloudVoucherReady='1';form.requestSubmit();}catch(err){form.querySelector('[data-error]').textContent=err.message;status(err.message,true);}},true);
 document.addEventListener('change',e=>{if(e.target.matches('#finance-v1 [name="voucher"]')){delete e.target.form.dataset.cloudVoucherReady;delete e.target.form.dataset.cloudVoucherUrl;}});
 window.addEventListener('beforeunload',e=>{if(saving||[...providers].some(([k,p])=>JSON.stringify(normalize(p.get()))!==baseline.get(k))){e.preventDefault();e.returnValue='';}});
})();
