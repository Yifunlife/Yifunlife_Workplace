(()=>{
 const root=document.getElementById('yw-after-sales');if(!root)return;
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const fields=[['model','设备款式'],['region','问题发生区域'],['deviceId','设备编号 / 序列号'],['faultDate','故障发生日期','date'],['activationDate','投入使用日期','date'],['lastRepairCompletedDate','上次维修完成日期','date'],['problemPart','问题部位'],['rootCause','根因分析'],['rootCauseEvidence','根因验证依据'],['correctiveAction','改善措施'],['validationResult','改善验证结果']];
 let items=new Map(),loading=false;
 async function load(){if(loading)return;loading=true;try{const r=await fetch('/api/aftercare/work-items');const j=await r.json();if(r.ok)items=new Map(j.items.map(d=>[d.id,d]));}finally{loading=false;}}
 root.addEventListener('click',async e=>{
  const b=e.target.closest('[data-af-analysis],[data-id],[data-review-id],[data-operation-id],[data-engineering-id]');if(!b)return;
  await load();const id=b.dataset.afAnalysis||b.dataset.id||b.dataset.reviewId||b.dataset.operationId||b.dataset.engineeringId;const d=items.get(id);if(!d)return;
  root.querySelectorAll('.aftercare-analysis').forEach(x=>x.remove());
  const form=document.createElement('form');form.className='aftercare-analysis';form.innerHTML='<h3>故障与根因追踪</h3><p>记录实际故障日期和设备编号，区分使用时长与交付时长。已确认的根因须填写验证依据。</p><div class="fields">'+fields.map(([key,label,type])=>'<label>'+label+'<input name="'+key+'" type="'+(type||'text')+'" value="'+esc(d[key])+'"></label>').join('')+'<label>根因进度<select name="rootCauseStatus">'+['待分析','待验证','已验证'].map(x=>'<option '+(d.rootCauseStatus===x?'selected':'')+'>'+x+'</option>').join('')+'</select></label><label>改善进度<select name="validationStatus">'+['待改善','验证中','已验证'].map(x=>'<option '+(d.validationStatus===x?'selected':'')+'>'+x+'</option>').join('')+'</select></label></div><p class="aftercare-analysis-message" role="status"></p><button type="submit">保存分析记录</button>';
  const target=b.closest('details')||root.querySelector('.detail:not([hidden]),#yw-review-editor:not(:empty),#yw-operation-editor:not(:empty),#yw-engineering-editor:not(:empty)')||b.closest('section');target?.append(form);
  form.addEventListener('submit',async event=>{event.preventDefault();event.stopImmediatePropagation();const message=form.querySelector('[role=status]');message.textContent='正在保存…';const snapshot={...d,...Object.fromEntries(new FormData(form))};try{const r=await fetch('/api/aftercare/work-items',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({items:[snapshot]})});const j=await r.json();if(!r.ok)throw Error(j.error);message.textContent='已保存，正在刷新最新记录…';location.reload();}catch(err){message.textContent=err.message;}},true);
 });
})();

if(window.parent!==window){const root=document.getElementById('yw-after-sales');let timer;new ResizeObserver(()=>{clearTimeout(timer);timer=setTimeout(()=>window.parent.postMessage({type:'yifun-aftercare-height',height:Math.ceil(root.getBoundingClientRect().height)+24},location.origin),100)}).observe(root);}
