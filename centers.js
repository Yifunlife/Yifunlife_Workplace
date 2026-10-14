'use strict';
const CENTER_NAMES={marketing:'运营中心',crm:'销售中心',design:'设计中心',projects:'交付进度',quote:'核算中心',engineering:'工程中心',procurement:'采购中心',stock:'仓库中心',aftersales:'售后中心',finance:'财务中心',factory:'工厂交接'};
const CENTER_DESCRIPTIONS={marketing:'记录渠道投入，跟踪线索质量与销售承接。',crm:'围绕客户、商机、跟进和正式订单推进业务。',design:'从需求、排期、成果确认到工程接收。',projects:'同一项目下查看各部门任务与交付记录。',quote:'核对报价进展，继续使用原有产品库与报价流程。',engineering:'核对执行规格、下达工程单，跟进安装与现场问题。',procurement:'从采购需求到供应商确认、发货和验收。',stock:'共用库存账本，区分在库、占用、待检和可用数量。',aftersales:'追踪客户问题、设备保修与退换返修。',finance:'按币种核对收款与结算，沿用财务开放状态。',factory:'查看工程分派给工厂的执行需求。'};
const DESIGN_STATES={queued:'待排设计',waiting_materials:'待补资料',in_progress:'设计中',review:'内部审核',waiting_confirmation:'待客户确认',revising:'修改中',confirmed:'客户已确认',handoff:'待工程接收',accepted:'工程已接收',cancelled:'已取消'};
const DESIGN_TRANSITIONS={queued:['waiting_materials','in_progress','cancelled'],waiting_materials:['queued','in_progress','cancelled'],in_progress:['review','waiting_confirmation','waiting_materials','cancelled'],review:['in_progress','waiting_confirmation','revising','cancelled'],waiting_confirmation:['confirmed','revising','cancelled'],revising:['review','waiting_confirmation','cancelled'],confirmed:['handoff','revising'],handoff:['accepted','revising'],accepted:[],cancelled:[]};
const CENTER_CURRENCIES=['CNY','USD','EUR','SAR','AED','AUD'].map(id=>({id,name:{CNY:'人民币 CNY',USD:'美元 USD',EUR:'欧元 EUR',SAR:'沙特里亚尔 SAR',AED:'阿联酋迪拉姆 AED',AUD:'澳元 AUD'}[id]}));
const SPEND_CURRENCIES=[...CENTER_CURRENCIES.filter(c=>c.id!=='AUD'),{id:'OTHER',name:'其他币种'}];
const CENTER_CHANNELS=['抖音','小红书','视频号','YouTube','阿里巴巴国际站','独立站','Instagram','Facebook','TikTok','展会','其他渠道'];
const CENTER_EXPENSES=['广告费','平台服务费','内容制作费','达人合作费','展位费','差旅费','活动物料费','代理服务费','其他费用'];
let centerData=null,centerRecords=null,centerPage='',centerFilters={},centerQuery='',centerStatus='';
const centerCall=(name,p)=>api('/api/centers/action/'+name,p);
const centerOptions=items=>items.map(id=>({id,name:id}));
const centerMoney=(minor,currency)=>minor==null?(currency==='OTHER'?'逐笔查看':'待接入'):`${currency==='OTHER'?'其他币种':currency} ${(minor/100).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})}`;
function centerPages(id){
 const native=id=>session.modules.includes(id);
 const pages={marketing:[['center-marketing-spend','投入登记'],['center-marketing-leads','来源线索']],crm:[['connections','销售工作台资料'],['leads','线索与跟进'],['opportunities','商机管理']],design:[],projects:[['orders','订单与变更'],['home','关联业务档案']],quote:[],engineering:[],procurement:native('procurement')?[['procurement','采购工作台']]:[],stock:[['inventory','共用库存'],...(can('admin','ceo','warehouse','purchasing','engineering','aftersales')?[['warehouse','库存作业'],['counts','盘点管理'],['locations','仓库与库位']]:[])],aftersales:[...(native('aftersales')?[['aftersales','售后工作台']]:[]),['equipment','设备与保修档案'],['returns','退换返修']],finance:[['finance','收款与结算'],...(can('admin','ceo','finance')?[['costs','项目成本'],['expenses','费用登记']]:[])],factory:[['technical','工程执行需求']]};
 
 return [['center-'+id,'中心看板'],...(pages[id]||[])];
}
function centerPeriod(id){const today=opsDate();return centerFilters[id]||{from:today.slice(0,8)+'01',to:today,currency:'CNY'};}
async function renderCenter(el,id,generation){
 centerPage=id;centerData=null;pageLoading(el,CENTER_NAMES[id],CENTER_DESCRIPTIONS[id]);
 try{
  const period=centerPeriod(id),query=new URLSearchParams({center:id,...period,...(project&&!['marketing','crm','design','quote'].includes(id)?{project}:{})});
  const data=await api('/api/centers/dashboard?'+query);if(generation!==renderGeneration)return;centerData=data;if(id==='aftersales'&&data.aftersales){renderAftersalesBoard(el,data);return;}if(id==='engineering'&&data.engineering){renderEngineeringBoard(el,data);return;}if(id==='quote'&&data.costing){renderCostingBoard(el,data);return;}if(id==='design'&&data.design){renderDesignBoard(el,data);return;}if(id==='marketing'){renderTestAccountBoard(el,data);return;}if(id==='crm'&&data.sales?.lifecycle){renderSalesLifecycle(el,data);return;}
  const pages=centerPages(id).slice(1),actions=pages.map(([page,label])=>`<button class="secondary" data-view="${page}">${label}</button>`).join('');
  const scope=project&&id!=='marketing'?projectName(project):can('admin','ceo')?'全部授权业务':'我的授权业务';
  el.classList.add('department-dashboard');
  el.innerHTML=head(CENTER_NAMES[id]+(id==='design'?'':'看板'),CENTER_DESCRIPTIONS[id],actions)+`<form class="center-filters" id="center-filters"><label>开始日期<input name="from" type="date" value="${esc(data.period.from)}" required></label><label>结束日期<input name="to" type="date" value="${esc(data.period.to)}" required></label>${['marketing','crm','finance'].includes(id)?select('currency','金额币种',id==='marketing'?[...CENTER_CURRENCIES,{id:'OTHER',name:'其他币种'}]:CENTER_CURRENCIES,data.currency):`<input type="hidden" name="currency" value="${data.currency}">`}<button type="submit">应用筛选</button><button type="button" class="quiet" data-action="center-reset">本月</button><p>${esc(scope)}<small>统计区间用于本期指标；待办反映当前状态。</small></p></form>`+
   `<dl class="center-metrics">${data.metrics.map(m=>`<div><dt>${esc(m.label)}</dt><dd>${m.value==null?esc(m.empty_text||'待接入'):m.unit==='money'?centerMoney(m.value,data.currency):esc(m.value)+`<small>${esc(m.unit)}</small>`}</dd><details class="department-metric-note"><summary>统计说明</summary><p>${esc(m.hint)}</p></details></div>`).join('')}</dl>`;
  if(id==='crm'&&data.sales)el.insertAdjacentHTML('beforeend',salesBoardSections(data));
  if(data.target){const t=data.target,r=t.record;el.insertAdjacentHTML('beforeend',panel(t.definition.label,`<div class="center-target">${r?`<strong>${t.definition.kind==='money'?centerMoney(t.actual,data.currency):t.actual} / ${t.definition.kind==='money'?centerMoney(r.value,data.currency):r.value}</strong><progress max="${Math.max(r.value,1)}" value="${Math.min(t.actual||0,Math.max(r.value,1))}" aria-label="${esc(t.definition.label)}进度"></progress><span>${r.value?Math.round((t.actual||0)/r.value*100)+'%':'目标为 0，比例不适用'}</span>`:'<p>本月尚未设置目标，完成率暂不计算。</p>'}</div>`,button('center-target',r?'调整目标':'设置目标','','secondary')));}
  if(data.groups.length){
   if(id==='marketing')el.insertAdjacentHTML('beforeend',panel('各渠道本期表现',table(['渠道','登记投入（'+(data.currency==='OTHER'?'其他币种':data.currency)+'）','新增线索','其中有效'],data.groups.map(g=>`<tr><td>${esc(g.label)}</td><td class="number">${centerMoney(g.amount,data.currency)}</td><td class="number">${g.count}</td><td class="number">${g.qualified}</td></tr>`))));
   else el.insertAdjacentHTML('beforeend',panel(id==='design'?'设计进度分布':'商机当前阶段分布',`<ul class="center-distribution">${data.groups.map(g=>`<li><span>${esc(g.label)}</span><meter min="0" max="${Math.max(1,...data.groups.map(x=>x.count))}" value="${g.count}" aria-label="${esc(g.label)}"></meter><strong>${g.count}</strong></li>`).join('')}</ul>`));
  }
  const priority=r=>r.due&&r.due<data.today?0:/异常|阻碍|缺料|延期|逾期/.test(r.status+' '+r.detail)?1:2;
  const rows=data.rows.map((r,i)=>({r,i})).sort((a,b)=>priority(a.r)-priority(b.r)||(a.r.due||'9999').localeCompare(b.r.due||'9999')).map(({r,i})=>`<tr><td><strong>${esc(r.title)}</strong><small>${esc(r.project_name)}</small><details class="department-row-detail"><summary>事项说明</summary><p>${esc(r.detail)}</p></details></td><td><span class="tag ${r.due&&r.due<data.today?'pending':''}">${esc(r.status)}</span></td><td>${esc(r.owner)}</td><td>${esc(r.due||'—')}${r.due&&r.due<data.today?'<small class="error">请核对期限与进度</small>':''}</td><td>${button('center-open','查看处理',String(i))}</td></tr>`);
  el.insertAdjacentHTML('beforeend',(id==='design'?'':panel((['quote','projects','engineering','factory'].includes(id)?'业务明细与处理入口':'当前待办与重点事项')+' · '+rows.length+' 条',rows.length?table(['事项／项目','状态','负责人','相关日期','操作'],rows):empty('当前没有待处理记录','从本中心业务入口登记资料后，这里会自动汇总。')))+`<details class="center-definitions"><summary>数据来源与统计说明</summary><p>更新时间：${esc(stamp(data.updated_at))}。每个数字来自当前账号可查看的业务记录。</p>${data.notices.map(n=>`<p>${esc(n)}</p>`).join('')}<p>尚未接入的数据保留“待接入”，不同币种分别展示。部门目标仅在管理者查看完整月度范围时显示。</p></details>`);
 }catch(err){if(generation!==renderGeneration)return;el.innerHTML=head(CENTER_NAMES[id]+(id==='design'?'':'看板'),CENTER_DESCRIPTIONS[id])+empty('暂时无法读取中心数据',err.message)+button('refresh','重新加载','','secondary');}
}
function salesBoardSections(data){
 const s=data.sales;
 const rows=s.projects.sort((a,b)=>({'已报价待签单':0,'报价中':1,'设计中':2,'已签单':3}[a.stage])-({'已报价待签单':0,'报价中':1,'设计中':2,'已签单':3}[b.stage])).map(p=>`<tr><td><strong>${esc(p.name)}</strong><small>${esc(p.code)} · ${esc(p.customer)}</small></td><td>${tag(p.stage)}</td><td>${esc(p.owner)}</td><td>${p.stage==='已签单'?centerMoney(p.contract_minor,data.currency):p.quote_minor==null?'尚未形成报价':centerMoney(p.quote_minor,p.quote_currency||data.currency)}</td><td>${button('sales-project','项目详情',p.id)}</td></tr>`);
 return panel('销售项目推进',`<div class="sales-funnel">${s.funnel.map(g=>`<div><span>${esc(g.label)}</span><strong>${g.count}<small> 个项目</small></strong><small>${g.label==='已签单'?'合同明细见下方项目列表':g.amount?centerMoney(g.amount,data.currency):'尚无报价金额'}</small></div>`).join('')}</div>`)+panel('销售项目列表 · '+rows.length+' 个',rows.length?table(['项目／客户','当前阶段','负责人','报价／合同金额','操作'],rows):empty('当前没有销售项目','客户与项目登记后自动汇总。'));
}
async function renderCenterRecords(el,page,generation){
 const kind=page==='center-marketing-spend'?'spend':'design';if(centerPage!==page){centerQuery='';centerStatus='';}centerPage=page;centerRecords=null;
 const title=kind==='spend'?'平台投入登记':'设计任务与工程交接';pageLoading(el,title);
 try{const data=await api('/api/centers/records?'+new URLSearchParams({page:kind,...(project&&kind!=='spend'?{project}:{})}));if(generation!==renderGeneration)return;centerRecords={...data,kind};
  const states=kind==='spend'?{active:'有效记录',void:'已作废'}:DESIGN_STATES;
  el.innerHTML=head(title,kind==='spend'?'每笔投入只登记一次。修改保留历史，作废须填写原因；各币种分开汇总。':'销售提交需求，设计安排人员和日期，成果经客户确认后交给工程接收。',data.can_write?button('center-new',kind==='spend'?'登记投入':'提交设计需求','','secondary'):'')+`<div class="ops-toolbar"><label>搜索<input id="center-search" type="search" value="${esc(centerQuery)}" placeholder="名称、项目或负责人"></label><label>状态<select id="center-status"><option value="">全部状态</option>${Object.entries(states).map(([key,label])=>`<option value="${key}"${key===centerStatus?' selected':''}>${label}</option>`).join('')}</select></label><span id="center-count" class="ops-result-count"></span></div><div id="center-records"></div>`;drawCenterRecords();
 }catch(err){if(generation!==renderGeneration)return;el.innerHTML=head(title,'')+empty('暂时无法读取记录',err.message)+button('refresh','重新加载','','secondary');}
}
function centerEmployee(id){return centerRecords?.employees.find(e=>e.id===id)?.name||'待分配';}
function drawCenterRecords(){
 if(!centerRecords||!$('#center-records'))return;
 const {kind}=centerRecords,rows=centerRecords.items.filter(r=>(!centerStatus||r.status===centerStatus)&&(!centerQuery||[r.number,r.title,r.channel,r.activity,r.expense_type,r.currency,r.note,projectName(r.project_id),centerEmployee(r.owner_id)].join(' ').toLowerCase().includes(centerQuery.toLowerCase())));
 $('#center-count').textContent=`${rows.length} 条记录`;
 const html=rows.map(r=>kind==='spend'?`<tr><td><strong>${esc(r.channel)}</strong><small>${esc(r.activity||'未关联活动')}</small><small>${esc(r.number)}</small></td><td>${esc(r.record_date)}</td><td>${esc(r.expense_type)}<small>${esc(r.region)}</small></td><td class="number">${centerMoney(r.amount_minor,r.currency)}</td><td>${esc(centerEmployee(r.owner_id))}</td><td class="center-spend-note">${esc(r.note||'—')}</td><td>${r.status==='void'?'已作废':'有效'}</td><td>${button('center-edit',r.status==='void'?'查看历史':'查看／修改',r.id)}</td></tr>`:`<tr><td><strong>${esc(r.title)}</strong><small>${esc(projectName(r.project_id))}</small><small>${esc(r.number)} · ${esc(r.task_type)}</small></td><td><span class="tag">${DESIGN_STATES[r.status]}</span>${r.priority==='urgent'?'<small class="error">紧急</small>':''}</td><td>${esc(centerEmployee(r.owner_id))}<small>${esc(r.team)}</small></td><td>${esc(r.due_date||'待排期')}<small>希望 ${esc(r.requested_date)}</small></td><td>${esc(r.version_label||'待提交')}<small>修改 ${r.revision_count} 轮</small></td><td>${button('center-edit','查看／处理',r.id)}</td></tr>`);
 $('#center-records').innerHTML=panel(kind==='spend'?'投入明细':'设计任务',rows.length?table(kind==='spend'?['平台／活动','发生日期','投入类型','原币金额','负责人','备注','状态','操作']:['任务／项目','状态','设计师／组','承诺日期','成果版本','操作'],html):empty(centerQuery||centerStatus?'没有符合条件的记录':'尚未登记业务记录',centerQuery||centerStatus?'调整筛选后重试。':kind==='spend'?'点击“登记投入”，记录各平台实际费用。':'先建立项目并分配参与成员，再提交设计需求。'));
}
function centerHistory(r){return `<details class="center-history full"><summary>查看业务历史（${r?.events?.length||0}）</summary>${r?.events?.length?r.events.map(e=>`<p><strong>${esc(e.action)}</strong> · ${esc(centerEmployee(e.actor_id))}<small>${esc(stamp(e.created_at))}</small>${e.note?`<span>${esc(e.note)}</span>`:''}</p>${e.changes?.length?`<dl class="center-changes">${e.changes.map(change=>`<div><dt>${esc(change.label)}</dt><dd><span>原：${esc(change.before)}</span><span>现：${esc(change.after)}</span></dd></div>`).join('')}</dl>`:''}`).join(''):'<p>保存后自动记录操作时间与变更。</p>'}</details>`;}
function spendForm(r){
 const locked=r?.status==='void',data=r||{},employees=can('admin','ceo')?centerRecords.employees:centerRecords.employees.filter(e=>e.id===session.user.id);
 const options=(items,value)=>value&&!items.some(item=>item.id===value)?[...items,{id:value,name:value+'（历史记录）'}]:items;
 const fields=`<p class="form-help full">标注“必填”的项目须填写；投入金额不填写货币符号，允许为 0。</p><label class="full">投入记录编号（系统生成）<input name="number" value="${esc(data.number||'保存后自动生成')}" readonly><small class="form-help">用于更新、去重和追踪，保存后保持不变。</small></label>`+
  input('record_date','日期（必填）','date',data.record_date||opsDate(),true,'aria-describedby="spend-date-help"')+
  select('channel','平台（必填）',options(centerOptions(CENTER_CHANNELS),data.channel),data.channel)+
  select('expense_type','投入类型（必填）',options(centerOptions(CENTER_EXPENSES),data.expense_type),data.expense_type)+
  select('currency','币种（必填）',options(SPEND_CURRENCIES,data.currency),data.currency||'CNY')+
  input('amount','投入金额（必填）','number',data.amount_minor==null?'':data.amount_minor/100,true,'min="0" step="0.01" inputmode="decimal" placeholder="请输入金额"')+
  select('owner_id','负责人（必填）',employees,data.owner_id||session.user.id)+
  `<p class="form-help full" id="spend-date-help">日期填写费用实际发生日期，格式为 yyyy-mm-dd；负责人选择该笔投入的内部负责人。</p>`+
  input('activity','活动／账户（选填）','text',data.activity||'',false,'placeholder="广告账户、推广活动或展会名称" maxlength="4000"')+
  (r?select('status','记录状态',[{id:'active',name:'有效记录'},{id:'void',name:'作废，保留历史'}],r.status):'')+
  `<label class="full"><span id="spend-note-label">备注（选填）</span><textarea name="note" maxlength="4000" aria-describedby="spend-note-help" placeholder="选择其他时，请写明具体渠道、费用或币种"></textarea><small class="form-help" id="spend-note-help">选择其他渠道、其他费用或其他币种时必须写明；作废时填写原因。</small></label>`;
 modal(r?'投入记录与历史':'登记平台投入',`<fieldset class="center-form-fields full"${locked?' disabled':''}>${fields}</fieldset>${r?centerHistory(r):''}`,p=>locked?Promise.resolve():centerCall('spend',{...p,region:data.region||'',reference:data.reference||'',project_id:data.project_id||null,...(r?{id:r.id,version:r.version}:{})}),locked?'关闭':'保存投入',()=>{
  fillTextareas(data);
  const form=$('#dialog-fields'),note=form.querySelector('[name="note"]');
  const update=()=>{
   const required=form.querySelector('[name="channel"]').value==='其他渠道'||form.querySelector('[name="expense_type"]').value==='其他费用'||form.querySelector('[name="currency"]').value==='OTHER'||form.querySelector('[name="status"]')?.value==='void';
   note.required=required;$('#spend-note-label').textContent=required?'备注（必填）':'备注（选填）';
   note.setCustomValidity(required&&!note.value.trim()?'请在备注中写明具体渠道、费用、币种或作废原因':'');
  };
  form.addEventListener('change',update);note.addEventListener('input',update);update();
 });
}
function designForm(r){
 const data=r||{},locked=r&&['accepted','cancelled'].includes(r.status),editor=centerRecords.can_manage_design;
 let choices=r?[r.status,...DESIGN_TRANSITIONS[r.status]]:['queued','waiting_materials'];
 if(!editor&&r)choices=choices.filter(x=>x===r.status||['confirmed','revising','cancelled'].includes(x));
 if(!can('admin','ceo','sales'))choices=choices.filter(x=>x!=='confirmed'||x===r?.status);
 if(!can('admin','ceo','engineering'))choices=choices.filter(x=>x!=='accepted'||x===r?.status);
 const fields=select('project_id','所属项目',state.projects,data.project_id||project)+input('title','任务名称','text',data.title||'')+select('task_type','任务类型',centerOptions(['平面方案','效果图','产品建模','设计修改','其他']),data.task_type||'平面方案')+select('priority','优先级',[{id:'normal',name:'正常'},{id:'urgent',name:'紧急'}],data.priority||'normal')+input('requested_date','希望完成日期','date',data.requested_date||'')+select('status','当前处理节点',choices.map(id=>({id,name:DESIGN_STATES[id]})),data.status||'queued')+textarea('brief','需求说明、资料清单与参考文件')+select('owner_id','设计负责人',centerRecords.employees.filter(e=>e.can_design),data.owner_id||'',false)+input('team','设计组','text',data.team||'',false)+input('due_date','设计承诺日期','date',data.due_date||'',false)+`<p class="form-help">首次承诺：${esc(data.original_due_date||'尚未排期')}。修改承诺须填写原因。</p>`+input('version_label','成果版本','text',data.version_label||'',false)+textarea('result_reference','成果文件链接／共享文件位置',false)+textarea('confirmation','客户确认依据（由销售记录）',false)+textarea('change_reason','修改、调期或取消原因',false)+textarea('handoff_note','工程交接／接收意见',false);
 modal(r?'设计任务与交接':'提交设计需求',`<fieldset class="center-form-fields full"${locked?' disabled':''}>${fields}</fieldset>${centerHistory(r)}`,p=>locked?Promise.resolve():centerCall('design',{...p,...(r?{id:r.id,version:r.version}:{})}),locked?'关闭':'保存处理结果',()=>{fillTextareas(data);if(!editor&&!locked)for(const key of ['owner_id','due_date','version_label','result_reference']){const field=$(`#dialog-fields [name="${key}"]`);field.disabled=true;const hidden=document.createElement('input');hidden.type='hidden';hidden.name=key;hidden.value=data[key]||'';field.after(hidden);}});
}
async function centerAction(name,id){
 if(!name.startsWith('center-')&&name!=='sales-project')return false;
 if(name==='sales-project'){view='home';routeRecord=id;await chooseProject(id);return true;}
 if(name==='center-reset'){delete centerFilters[centerPage];await render();return true;}
 if(name==='center-new'||name==='center-edit'){const r=centerRecords?.items.find(r=>r.id===id);if(name==='center-edit'&&!r)throw Error('记录已更新，请刷新');centerRecords.kind==='spend'?spendForm(r):designForm(r);return true;}
 if(name==='center-open'){
  const row=centerData?.rows[Number(id)];if(!row)return true;
  const target=centerPage==='marketing'&&row.page==='leads'?'center-marketing-leads':row.page;
  if(!workplaceCenters().some(c=>c.pages.some(([page])=>page===target))){notify('当前岗位请联系对应中心负责人处理');return true;}
  view=target;routeRecord=row.id;moduleLink='';
  if(target==='procurement')moduleLink='&view=orders&order='+encodeURIComponent(row.id);
  if(target==='aftersales')moduleLink='#ticket-detail/'+encodeURIComponent(row.id);
  if(row.project_id)await chooseProject(row.project_id);else await render();
  if(target==='center-design-records'&&centerRecords?.items.some(r=>r.id===row.id))designForm(centerRecords.items.find(r=>r.id===row.id));
  else if((OPS_LABELS[target]||target==='center-marketing-leads')&&opsData?.items.some(r=>r.id===row.id))await operationsAction('ops-detail',row.id);
  return true;
 }
 if(name==='center-target'){
  const target=centerData.target,r=target.record,money=target.definition.kind==='money';
  modal(target.definition.label,`<p class="full">${esc(centerData.period.from.slice(0,7))} · ${money?esc(centerData.currency):'数量目标'}。目标适用于整个中心。</p>`+input('value','目标值','number',r?(money?r.value/100:r.value):'',true,`min="0" step="${money?'0.01':'1'}"`)+textarea('note',r?'调整原因':'目标说明',Boolean(r)),p=>centerCall('target',{...p,center:centerData.center,month:centerData.period.from,currency:centerData.currency,...(r?{version:r.version}:{})}));return true;
 }
 if(name==='center-members'){
  const employee=state.employees.find(e=>e.id===id);
  modal('分配运营／设计职责',`<p class="full">${esc(employee.name)}。增加中心职责，原岗位与项目成员权限继续保留。</p><fieldset class="member-list full"><legend>业务中心职责</legend>${['marketing','design'].map(key=>`<label><input type="checkbox" name="${key}"${employee.centers?.includes(key)?' checked':''}><span>${CENTER_NAMES[key]}</span></label>`).join('')}</fieldset><p class="form-help full">设计任务仍需加入对应项目后才能查看。管理员和 CEO 默认可查看各中心。</p>`,p=>centerCall('members',{employee_id:id,centers:['marketing','design'].filter(key=>p[key]==='on')}));return true;
 }
 if(name==='center-followup'||name==='center-followup-history'){
  const r=opsData?.items.find(r=>r.id===id);if(!r)throw Error('请刷新业务记录');
  if(name==='center-followup-history'){
   const data=await api('/api/centers/followups?'+new URLSearchParams({entity:opsPage,id}));
   modal('跟进历史',`<div class="full">${data.items.length?data.items.map(f=>`<article class="center-followup"><strong>${esc(f.contact_date)} · ${esc(f.actor_name)}</strong><p>${esc(f.result)}</p><p>下一步：${esc(f.next_action)} · ${esc(f.next_date)}</p></article>`).join(''):empty('暂无独立跟进记录','原有备注保留在业务详情中；新跟进将逐次保存。')}</div>`,async()=>{},'关闭');return true;
  }
  modal('记录客户跟进',`<p class="full">${esc(r.name)}</p>`+input('contact_date','沟通日期','date',opsDate())+textarea('result','沟通结果')+input('next_action','下一步行动','text',r.next_action||'')+input('next_date','下次跟进日期','date',r.latest_followup?.next_date||r.next_date||opsDate()),p=>centerCall('followup',{...p,entity:opsPage,entity_id:r.id,version:r.version}),'保存跟进记录');return true;
 }
 return false;
}
document.addEventListener('submit',async e=>{if(e.target.id!=='center-filters')return;e.preventDefault();const p=Object.fromEntries(new FormData(e.target));if(p.from>p.to){notify('开始日期不能晚于结束日期');return;}centerFilters[centerPage]=p;await render();});
document.addEventListener('input',e=>{if(e.target.id==='center-search'){centerQuery=e.target.value;drawCenterRecords();}});
document.addEventListener('change',async e=>{if(e.target.id==='center-status'){centerStatus=e.target.value;drawCenterRecords();}if(e.target.id==='center-switch'){view=e.target.value;moduleLink='';routeRecord='';await render();}});

setInterval(()=>{
 if(!view.startsWith('center-')||!CENTER_NAMES[view.slice(7)]||document.hidden)return;
 if(document.querySelector('dialog[open],#content details[open]')||document.activeElement?.closest('form'))return;
 const position=window.scrollY;
 render().then(()=>window.scrollTo(0,position));
},60000);

const TEST_BOARD_MARKUP="<div id=\"dept-life\">\n\n<header><div class=\"muted\">亦玩 Workplace / 部门 / 运营部</div><h2>运营与 CEO 联调测试版</h2><div class=\"muted\">共用测试项目 · 与销售、设计、核算同步</div></header>\n<main>\n<div class=\"bar\"><h3>运营汇总</h3><label class=\"push\">统计范围 <select id=\"life-period\"><option value=\"today\">今日</option><option value=\"month\">本月</option><option value=\"custom\">自选日期</option></select></label><div id=\"life-dates\" class=\"dates closed\"><label>开始日期<input id=\"life-start\" type=\"date\" ></label><label>结束日期<input id=\"life-end\" type=\"date\" ></label></div></div>\n<div id=\"life-error\" role=\"alert\"></div><div id=\"life-stats\" class=\"summary-groups\" aria-live=\"polite\"></div>\n<section class=\"panel\"><h3>运营平台总览</h3><div id=\"life-inventory\"></div></section>\n<section class=\"panel operations-domestic\" id=\"operations-domestic\"><div class=\"bar\"><h3>内贸平台账号运营</h3><span id=\"life-range-domestic\" class=\"muted push\"></span></div><div id=\"operations-summary-domestic\" class=\"muted operation-summary\"></div><div class=\"scroll\"><table><thead><tr><th>平台</th><th>运营账号</th><th>负责人</th><th>总粉丝</th><th>本月增加粉丝</th><th>当天增加粉丝量</th><th>本月总发布条数</th><th id=\"life-cost-title-domestic\">今日花销</th><th id=\"life-sales-title-domestic\">今日成交金额</th><th>投入产出比</th></tr></thead><tbody id=\"life-rows-domestic\"></tbody></table></div></section>\n<section class=\"panel operations-foreign\" id=\"operations-foreign\"><div class=\"bar\"><h3>外贸平台账号运营</h3><span id=\"life-range-foreign\" class=\"muted push\"></span></div><div id=\"operations-summary-foreign\" class=\"muted operation-summary\"></div><div class=\"scroll\"><table><thead><tr><th>平台</th><th>运营账号</th><th>负责人</th><th>总粉丝</th><th>本月增加粉丝</th><th>当天增加粉丝量</th><th>本月总发布条数</th><th id=\"life-cost-title-foreign\">今日花销</th><th id=\"life-sales-title-foreign\">今日成交金额</th><th>投入产出比</th></tr></thead><tbody id=\"life-rows-foreign\"></tbody></table></div></section>\n<section id=\"life-detail\" class=\"panel\" hidden aria-live=\"polite\"></section>\n</main></div>";
function renderTestAccountBoard(el,data){
 el.innerHTML=TEST_BOARD_MARKUP;
 const root=el.querySelector('#dept-life'),q=s=>root.querySelector(s),initial=data.account_reporting;
 const money=n=>`${initial.currency} ${(n/100).toLocaleString('zh-CN',{minimumFractionDigits:2})}`,number=n=>n==null?'待补期初记录':n.toLocaleString('zh-CN'),ratio=n=>n==null?'—':n.toFixed(2)+' 倍';
 q('#life-start').value=data.period.from;q('#life-end').value=data.period.to;q('#life-period').value=data.period.from===initial.today.slice(0,7)+'-01'?'month':'custom';
 function paint(r){const label=q('#life-period').value==='today'?'今日':q('#life-period').value==='month'?'本月':'区间';q('#life-dates').classList.toggle('closed',q('#life-period').value!=='custom');
 q('#life-stats').innerHTML=r.markets.map(m=>`<section class="summary-market ${m.market==='外贸'?'summary-foreign':''}"><h3>${m.market}平台汇总 · 测试数据</h3><div class="summary-metrics">${[['已列账号数',m.account_count+' 个'],[label+'总花销',money(m.cost)],[label+'成交金额',money(m.sales)],['本月投入产出比',ratio(m.month_ratio)],['年度总广告支出',money(m.annual_ads)],['月度总广告支出',money(m.monthly_ads)]].map(([l,v])=>`<div class="stat"><div class="muted">${l}</div><div class="value">${v}</div></div>`).join('')}</div></section>`).join('');
 q('#life-inventory').innerHTML=r.markets.map(m=>{const aa=r.accounts.filter(a=>a.market===m.market),ps=[...new Set(aa.map(a=>a.platform))];return `<div class="market-block ${m.market==='外贸'?'foreign':''}"><div class="market-head"><strong>${m.market}平台</strong><span>${ps.length} 个平台 · ${aa.length} 个账号</span></div><div class="platform-cards">${ps.map(pl=>`<section class="platform-card"><h3>${esc(pl)}</h3><div class="platform-accounts">${aa.filter(a=>a.platform===pl).map(a=>`<button type="button" data-test-account="${a.id}">${esc(a.name)}</button>`).join('')}</div></section>`).join('')}</div></div>`}).join('');
 for(const m of r.markets){const k=m.market==='内贸'?'domestic':'foreign';q('#life-range-'+k).textContent=r.period.from+' 至 '+r.period.to;q('#life-cost-title-'+k).textContent=label+'花销';q('#life-sales-title-'+k).textContent=label+'成交金额';q('#operations-summary-'+k).textContent='独立测试数据 · '+r.currency+' · 与 CEO 读取同一账号台账';q('#life-rows-'+k).innerHTML=r.accounts.filter(a=>a.market===m.market).map(a=>`<tr><td>${esc(a.platform)}</td><td><button type="button" data-test-account="${a.id}">${esc(a.name)}</button></td><td>${esc(a.owner||'待分配')}</td><td>${number(a.fans)}</td><td>${number(a.month_gain)}</td><td>${number(a.today_gain)}</td><td>${a.month_posts} 条</td><td>${money(a.cost)}</td><td>${money(a.sales)}</td><td>${ratio(a.ratio)}</td></tr>`).join('');}
 root.querySelectorAll('table').forEach(t=>{const labels=Array.from(t.querySelectorAll('th'),x=>x.textContent);t.querySelectorAll('tbody tr').forEach(tr=>Array.from(tr.children).forEach((td,i)=>td.dataset.label=labels[i]));});
 root.onclick=e=>{const b=e.target.closest('[data-test-account]');if(!b)return;const a=r.accounts.find(x=>x.id===b.dataset.testAccount);q('#life-detail').hidden=false;q('#life-detail').innerHTML=`<h3>${esc(a.platform)} / ${esc(a.name)}</h3><p>稳定账号编号：${esc(a.id)} · 总粉丝 ${number(a.fans)} · 月发布 ${a.month_posts} 条</p><p>区间花销 ${money(a.cost)} · 归属测试成交 ${money(a.sales)} · 投产比 ${ratio(a.ratio)}</p><p>共享测试成交读取同一项目的正式订单记录，按来源账号归属。</p>`;q('#life-detail').scrollIntoView({block:'nearest'});};
 }
 root.addEventListener('change',async()=>{const p=q('#life-period').value,t=initial.today;const from=p==='today'?t:p==='month'?t.slice(0,7)+'-01':q('#life-start').value,to=p==='custom'?q('#life-end').value:t;if(from>to){q('#life-error').textContent='开始日期不能晚于结束日期';return}try{const d=await api('/api/centers/dashboard?'+new URLSearchParams({center:'marketing',from,to,currency:initial.currency}));q('#life-error').textContent='';paint(d.account_reporting);}catch(e){q('#life-error').textContent=e.message}});paint(initial);
}

function renderCostingBoard(el,data){
 const d=data.costing,t=d.totals;
 el.classList.add('department-dashboard','costing-dashboard');
 const sample=d.shared_test_count>0;
 const metric=(label,value,hint)=>`<div><dt>${esc(label)}</dt><dd>${value==null?'—':esc(value)}</dd><p>${esc(hint)}</p></div>`;
 const rows=d.projects.map(r=>`<tr><td><strong>${esc(r.name)}</strong><small>${esc(r.code)}${r.shared_test?' · 共享测试':''}</small></td><td>${esc(r.sales_owner)}</td><td>${esc(r.design_owner)}</td><td>${esc(r.costing_owner)}</td><td><span class="tag ${['待接收','待核算','待报价审核'].includes(r.state)?'pending':''}">${esc(r.state)}</span></td><td class="number">${r.count} 次</td><td class="number">${Object.entries(r.amounts).map(([c,v])=>centerMoney(v,c)).join('<br>')||(r.count?'待成交':'—')}</td><td>${esc(r.due||'待登记')}</td><td>${esc(r.progress)}</td></tr>`);
 el.innerHTML=head('核算部看板','设计资料 · 核算记录 · 报价与成交'+(sample?' · 共享测试数据':''),'')+
 `<div class="center-filters"><label>统计截止日期<input id="costing-date" type="date" value="${esc(data.period.to)}" required></label></div>`+
 `<dl class="center-metrics">${metric('待接收资料',t.pending,'等待接收核算资料')}${metric('核算进行中',t.active,'成本与报价核算中')}${metric('待报价审核',t.review,sample?'等待负责人确认':'审核记录待接入')}${metric('本月已完成',t.monthly,'本月核算项目数，不含修订')}${metric('年核算总数量',t.annual,data.period.to.slice(0,4)+' 年累计，不含修订')}</dl>`+
 panel('全部任务 '+rows.length,rows.length?`<div class="department-table-wrap">${table(['项目名称','商务负责人','设计负责人','核算负责人','状态','核算次数','成交金额','截止时间','当前进展'],rows)}</div>`:empty('暂无核算任务','设计资料确认或关联报价记录后自动显示。'))+
 `<details class="center-definitions"><summary>数据来源与统计说明</summary>${d.notices.map(n=>`<p>${esc(n)}</p>`).join('')}</details>`;
 el.querySelector('#costing-date').addEventListener('change',e=>{if(!e.target.value||!e.target.checkValidity())return;const to=e.target.value;centerFilters.quote={from:to.slice(0,7)+'-01',to,currency:'CNY'};render();});
}

function renderDesignBoard(el,data){
 const d=data.design,t=d.totals;
 el.classList.add('department-dashboard','design-dashboard');
 const money=amounts=>Object.entries(amounts).map(([currency,value])=>centerMoney(value,currency)).join('<br>')||'待确认';
 const summary=(label,value)=>`<div><dt>${esc(label)}</dt><dd>${value}<small> 单</small></dd></div>`;
 const groupRows=d.groups.map(g=>`<tr><td><strong>${esc(g.name)}</strong></td>${[g.annual,g.monthly,g.active,...g.stages,g.overdue].map(v=>`<td class="design-number">${v}</td>`).join('')}</tr>`);
 groupRows.push(`<tr class="design-total"><th>合计</th>${[t.annual,t.monthly,t.active,...t.stages,t.overdue].map(v=>`<th class="design-number">${v}</th>`).join('')}</tr>`);
 const orders=d.orders.map(r=>`<tr><td><strong>${esc(r.name)}</strong><small>${esc(r.order_numbers.join('、')||r.code+' · 未签单')}</small></td><td class="design-number">${money(r.amounts)}</td><td class="design-number">${esc(r.customer_grade)}</td><td>${esc(r.project_type)}</td><td>${esc(r.sales_owner)}</td><td>${esc(r.design_owner)}</td><td><span class="tag">${esc(r.stage)}</span></td><td class="design-number">${esc(r.expected_date||'待排期')}</td><td class="design-number">${esc(r.actual_date||'—')}</td><td class="${r.overdue?'error':''}">${esc(r.alerts.join('；')||'—')}</td></tr>`);
 el.innerHTML=head('设计部看板','项目方案 · 效果图 · 深化图纸 · 报价与生产交接','')+
 `<form class="center-filters" id="center-filters"><label>统计截止日期<input name="to" type="date" value="${esc(data.period.to)}" required></label><input type="hidden" name="from" value="${esc(data.period.to.slice(0,7)+'-01')}"><input type="hidden" name="currency" value="CNY"><button type="submit">应用</button><button type="button" class="quiet" data-action="center-reset">本月</button><p>完成订单按截止日期汇总；在手订单反映当前状态。</p></form>`+
 `<dl class="center-metrics design-completed">${summary('年设计完成总订单',t.annual)}${summary('月设计完成总订单',t.monthly)}</dl><dl class="center-metrics design-current">${['设计排单','设计中','报价交接中','生产交接中','当前逾期'].map((label,i)=>summary(label,i===4?t.overdue:t.stages[i])).join('')}</dl>`+
 panel('各设计组订单情况',`<div class="design-table-wrap department-table-wrap">${table(['设计组','年完成订单','月完成订单','在手订单','设计排单','设计中','报价交接中','生产交接中','当前逾期'],groupRows)}</div>`)+
 panel('设计订单推进 · '+d.orders.length+' 单',orders.length?`<div class="design-table-wrap department-table-wrap">${table(['订单','订单金额','客户等级','项目类型','商务负责人','设计负责人','当前阶段','预计完成时间','实际完成时间','重点关注'],orders)}</div>`:empty('暂无设计订单','关联设计记录后自动汇总。'))+
 `<details class="center-definitions"><summary>数据来源与统计说明</summary>${d.notices.map(n=>`<p>${esc(n)}</p>`).join('')}</details>`;
 $('#center-filters').addEventListener('submit',e=>{e.preventDefault();const p=Object.fromEntries(new FormData(e.currentTarget));p.from=p.to.slice(0,7)+'-01';centerFilters.design=p;render();});
}


function renderEngineeringBoard(el,data){
 const report=data.engineering,stages=['未排期','下单中','生产中','待安装','安装中','售后','未来订单'],depts=['下单','木工部','软包部','油漆部','铁车间','采购部','安装'];
 let selected='总订单';
 el.innerHTML='<div class="department-dashboard engineering-dashboard"></div>';const board=el.firstElementChild;
 const metricNames=['总订单','未来订单','未排期订单','下单中订单','生产中订单','待安装中订单','安装中订单','售后订单'];
 const stageFor={'未来订单':'未来订单','未排期订单':'未排期','下单中订单':'下单中','生产中订单':'生产中','待安装中订单':'待安装','安装中订单':'安装中','售后订单':'售后'};
 const subset=label=>report.orders.filter(r=>label==='总订单'?r.stage!=='未来订单':r.stage===stageFor[label]);
 const pct=v=>v==null?'<span class="muted">待登记</span>':`<div class="engineering-progress"><span>${v}%</span><progress max="100" value="${v}" aria-label="完成进度 ${v}%"></progress></div>`;
 function draw(){
  const rows=subset(selected);
  board.innerHTML=head('工程部看板','订单排期 · 工程下单 · 生产安装 · 售后跟进')+`<dl class="center-metrics engineering-metrics">${metricNames.map(label=>`<div><button type="button" data-eng-filter="${label}" aria-pressed="${selected===label}"><dt>${label}</dt><dd>${subset(label).length}</dd></button></div>`).join('')}</dl>`+
   panel(selected+' · '+rows.length,`<div class="department-table-wrap"><table><thead><tr>${['项目名称','商务负责人','设计负责人','核算负责人','工程负责人','下单进度','木工部','软包部','油漆部','铁车间','采购部','安装进度','问题反馈'].map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr><td><strong>${esc(r.name)}</strong><small>${esc(r.number)}${r.shared_test?' · 测试数据':''}</small><small>交货期：${esc(r.delivery_date||'待登记')}</small></td><td>${esc(r.sales_owner)}</td><td>${esc(r.design_owner)}</td><td>${esc(r.costing_owner)}</td><td>${esc(r.engineering_owner)}</td>${depts.map(d=>`<td>${pct(r.progress[d])}</td>`).join('')}<td class="engineering-feedback">${esc(r.issue||'暂无反馈')}${report.can_edit?`<small><button type="button" class="quiet" data-eng-edit="${esc(r.id)}">反馈 / 更新进度</button></small>`:''}</td></tr>`).join('')||'<tr><td colspan="13">当前没有此类订单</td></tr>'}</tbody></table></div>`)+
   panel('交货重点提醒 · '+report.alerts.length+' 单',`<p class="engineering-alert-note">统计基准：${esc(report.today)} · 交货期10天以内及逾期未交付订单</p>${report.alerts.map(r=>`<div class="engineering-alert"><div><strong>${esc(r.name)}</strong><small>${esc(r.number)} · 交货期：${esc(r.delivery_date)}</small></div><span class="tag pending">${r.days<0?'已逾期 '+(-r.days)+' 天':r.days===0?'今天交货':'距交货 '+r.days+' 天'}</span><div>卡点部门：${esc(r.blocker_dept||'待登记')}<small>${esc(r.blocker_reason||'尚未登记卡点原因')}</small></div>${report.can_edit?`<button type="button" class="quiet" data-eng-edit="${esc(r.id)}">跟进</button>`:''}</div>`).join('')||'<p class="engineering-alert-note">暂无交货期10天以内的未交付订单</p>'}`)+`<details class="center-definitions"><summary>数据来源与统计说明</summary>${report.notices.map(n=>`<p>${esc(n)}</p>`).join('')}</details>`;
 }
 board.onclick=e=>{const filter=e.target.closest('[data-eng-filter]');if(filter){selected=filter.dataset.engFilter;draw();return;}const edit=e.target.closest('[data-eng-edit]');if(!edit)return;const r=report.orders.find(r=>r.id===edit.dataset.engEdit);if(!r)return;
 const opts=(items,value)=>items.map(x=>`<option value="${esc(x)}" ${value===x?'selected':''}>${esc(x)}</option>`).join('');
 const ownerOptions='<option value="">待分配</option>'+report.employees.map(e=>`<option value="${esc(e.id)}" ${r.owner_id===e.id?'selected':''}>${esc(e.name)}</option>`).join('');
 modal(r.name+' · 工程进度与问题反馈',`<label>工程负责人<select name="owner_id">${ownerOptions}</select></label><label>交货期<input type="date" name="delivery_date" value="${esc(r.delivery_date||'')}"></label><label>当前阶段<select name="stage">${opts(r.stage==='未来订单'?['未来订单']:stages.filter(s=>s!=='未来订单'),r.stage)}</select></label>${depts.map((d,i)=>`<label>${d}进度（%）<input name="progress_${i}" type="number" min="0" max="100" step="1" value="${r.progress[d]??''}" placeholder="待登记"></label>`).join('')}<label>卡点部门<select name="blocker_dept"><option value="">待登记 / 无卡点</option>${opts(['工程部','设计部','核算部','商务部','木工部','软包部','油漆部','铁车间','采购部','安装部','其他'],r.blocker_dept)}</select></label><label class="full">卡点原因<textarea name="blocker_reason">${esc(r.blocker_reason)}</textarea></label><label class="full">问题反馈<textarea name="issue">${esc(r.issue)}</textarea></label>`,p=>centerCall('engineering-progress',{...p,id:r.id,project_id:r.project_id,version:r.version,progress:Object.fromEntries(depts.map((d,i)=>[d,p['progress_'+i]]))}));
 };
 draw();
}

function renderAftersalesBoard(el,data){
 const r=data.aftersales;let selected='open';
 el.innerHTML='<div class="department-dashboard aftersales-dashboard"></div>';const board=el.firstElementChild;
 const active=r.orders.filter(o=>!o.closed);
 const filters=[['open','进行中工单',r.open_total],['审核','待审核',r.pending_review],['overdue','当前超期',r.overdue_total],['客户验收','待客户验收',r.pending_acceptance],['risk','安全风险',r.risk_total]];
 const subset=key=>r.orders.filter(o=>key==='annual'?o.created_date&&r.year+'-01-01'<=o.created_date&&o.created_date<=r.today:key==='monthly'?o.created_date&&r.month+'-01'<=o.created_date&&o.created_date<=r.today:!o.closed&&(key==='open'||key==='overdue'&&o.overdue||key==='risk'&&o.risk||key==='safety_s'&&o.safety_level==='S级安全问题'||o.stage===key));
 const filterLabel=key=>({open:'进行中',annual:'年度全部',monthly:'月度全部',overdue:'超期',risk:'安全风险',safety_s:'S级安全问题'}[key]||key);
 const filterButton=(key,label,count,cls='')=>`<button type="button" class="${cls}" data-as-filter="${esc(key)}" aria-pressed="${selected===key}"><span>${esc(label)}</span><strong>${count}</strong></button>`;
 function draw(){const rows=subset(selected);
  board.innerHTML=`<header class="as-heading"><div><h2>售后驾驶舱</h2><p>一单到底 · 全程追踪 · 责任到人 · 验收闭环</p></div><span class="as-date">${esc(r.month.replace('-',' 年 '))} 月 · 截至 ${esc(r.today.slice(5).replace('-',' 月 '))} 日</span></header>`+
   `<div class="as-totals">${[['annual','年度售后总订单',r.annual_total,r.year+' 年累计新建'],['monthly','月度售后总订单',r.monthly_total,r.month+' 新建']].map(([key,label,count,note])=>`<button type="button" class="as-total" data-as-filter="${key}" aria-pressed="${selected===key}"><div><span>${label}</span><small>${esc(note)} · 含已关闭工单</small></div><strong>${count}<small> 单</small></strong></button>`).join('')}</div>`+
   `<div class="as-metrics">${filters.map(([key,label,count])=>`<div>${filterButton(key,label,count,'as-metric '+(['overdue','risk'].includes(key)?'as-warning':''))}<small>查看相关工单</small></div>`).join('')}</div>`+
   `<section class="as-section as-flow"><h3>全流程进度</h3>${r.stages.map(s=>filterButton(s.label,s.label,s.count,'as-step')).join('')}${r.unclassified_stage?`<p class="as-footnote">另有 ${r.unclassified_stage} 单流程待核对</p>`:''}</section>`+
   `<section class="as-section"><div class="as-toolbar"><h3 id="as-live-count" aria-live="polite">售后工单跟踪 · ${rows.length} 单${selected==='open'?'':' · '+esc(filterLabel(selected))}</h3><div class="as-tabs">${[['open','全部'],['overdue','超期'],['risk','安全风险']].map(([key,label])=>`<button type="button" data-as-filter="${key}" aria-pressed="${selected===key}">${label}</button>`).join('')}</div></div><div class="as-table-wrap"><table><thead><tr>${['工单 / 项目名称','合同期限','商务','设计师','工程师','当前阶段','负责人','操作'].map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.map(o=>`<tr><td><strong>${esc(o.name)}</strong><small>${esc(o.id)}${o.shared_test?' · 测试数据':''}</small><small>${esc(o.product)}</small></td><td>${esc(o.contract_deadline||'待登记')}<small class="${o.overdue?'as-warning-text':''}">预计完成：${esc(o.due_date||'待登记')}${o.overdue?' · 已超期':''}</small></td><td>${esc(o.sales_owner)}</td><td>${esc(o.design_owner)}</td><td>${esc(o.engineering_owner)}</td><td>${esc(o.stage)}${o.risk?`<small class="as-warning-text">${esc(o.safety_level)}</small>`:''}</td><td>${esc(o.owner)}</td><td>${session.modules.includes('aftersales')?`<button type="button" class="quiet" data-as-open="${esc(o.id)}">查看工单</button>`:''}${r.can_edit&&!session.read_only&&!o.closed?`<button type="button" class="quiet" data-as-edit="${esc(o.id)}">流程 / 风险登记</button>`:''}</td></tr>`).join('')||'<tr><td colspan="8">当前没有此类工单</td></tr>'}</tbody></table></div></section>`+
   `<div class="as-bottom"><section class="as-section"><h3>售后执行方式</h3>${r.methods.map(m=>`<div class="as-method"><div><span>${esc(m.label)}</span><span>${m.count} 单</span></div><progress max="${Math.max(active.length,1)}" value="${m.count}" aria-label="${esc(m.label)} ${m.count} 单"></progress></div>`).join('')}<p class="as-footnote">${r.unregistered_method} 单执行方式待登记</p></section><section class="as-section"><h3>风险与闭环提醒</h3><button type="button" class="as-risk" data-as-filter="safety_s">S级安全问题 ${r.safety_s} 项</button><p class="as-warning-text">费用承担待确认：${r.cost_pending} 项</p><p class="as-footnote">安全等级待登记 ${r.unregistered_risk} 单 · 费用承担待登记 ${r.unregistered_cost} 单</p><p>客户验收 → 负责人复核 → 工单关闭</p><p>产品改善任务独立跟踪至验证完成</p></section></div>`+
   `<details class="center-definitions"><summary>数据来源与统计说明</summary>${r.notices.map(n=>`<p>${esc(n)}</p>`).join('')}</details>`;
 }
 board.onclick=async e=>{const filter=e.target.closest('[data-as-filter]');if(filter){selected=filter.dataset.asFilter;draw();return;}
  const open=e.target.closest('[data-as-open]');if(open){const o=r.orders.find(o=>o.id===open.dataset.asOpen);if(!o)return;view='aftersales';routeRecord=o.id;moduleLink='#ticket-detail/'+encodeURIComponent(o.id);if(o.project_id)await chooseProject(o.project_id);else await render();return;}
  const edit=e.target.closest('[data-as-edit]');if(!edit)return;const o=r.orders.find(o=>o.id===edit.dataset.asEdit);if(!o)return;
  const opts=(items,value)=>'<option value="">待登记</option>'+items.map(x=>`<option value="${esc(x)}"${value===x?' selected':''}>${esc(x)}</option>`).join('');
  modal(o.name+' · 流程与风险登记',`<p class="full">${esc(o.id)} · 原工作节点：${esc(o.native_stage)}。登记不代替实际采购、物流、客户验收或关闭操作。</p><label>合同期限<input type="date" name="contract_deadline" value="${esc(o.contract_deadline||'')}"></label><label>驾驶舱当前阶段<select name="dashboard_stage">${opts(r.stages.map(s=>s.label),o.stage)}</select></label><label>执行方式<select name="execution_method">${opts(r.methods.map(m=>m.label),o.execution_method)}</select></label><label>安全等级<select name="safety_level">${opts(['无安全风险','一般安全风险','S级安全问题'],o.safety_level)}</select></label><label>费用承担<select name="cost_responsibility">${opts(['待确认','公司承担','客户承担','供应商承担','共同承担'],o.cost_responsibility)}</select></label>`,p=>centerCall('aftersales-progress',{...p,id:o.id,version:o.version}));
 };
 draw();
}
