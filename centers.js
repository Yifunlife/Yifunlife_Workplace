let aftercareSharedTaskId=new URLSearchParams(location.search).get('sharedTask')==='1'?new URLSearchParams(location.search).get('record')||'':'';
'use strict';
const CENTER_NAMES={marketing:'运营中心',crm:'销售中心',design:'设计中心',projects:'交付进度',quote:'核算中心',engineering:'工程中心',procurement:'采购中心',stock:'仓库中心',aftersales:'售后中心',product_rd:'产品研发中心',software:'软件中心',brand_visual:'品牌视觉中心',finance:'财务中心',factory:'生产中心'};
const CENTER_DESCRIPTIONS={product_rd:'产品研发、样品验证与产品改进。',software:'软件开发、版本交付与系统维护。',brand_visual:'品牌形象、视觉设计与品牌物料。',marketing:'记录渠道投入，跟踪线索质量与销售承接。',crm:'围绕客户、商机、跟进和正式订单推进业务。',design:'从需求、排期、成果确认到工程接收。',projects:'同一项目下查看各部门任务与交付记录。',quote:'核对报价进展，继续使用原有产品库与报价流程。',engineering:'核对执行规格、下达工程单，跟进安装与现场问题。',procurement:'从采购需求到供应商确认、发货和验收。',stock:'共用库存账本，区分在库、占用、待检和可用数量。',aftersales:'追踪客户问题、设备保修与退换返修。',finance:'按币种核对收款与结算，沿用财务开放状态。',factory:'查看工程分派的生产需求与交接记录。'};
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
 const pages={marketing:[['center-marketing-spend','投入登记'],['center-marketing-leads','来源线索']],crm:[['connections','销售工作台资料'],['leads','线索与跟进'],['opportunities','商机管理']],design:[],projects:[['orders','订单与变更'],['home','关联业务档案']],quote:[],engineering:[],procurement:[],stock:[['inventory','共用库存'],...(can('admin','ceo','warehouse','purchasing','engineering','aftersales')?[['warehouse','库存作业'],['counts','盘点管理'],['locations','仓库与库位']]:[])],aftersales:[['center-aftersales-workflow','售后工作台'],['center-aftersales-issues','问题统计']],finance:[['finance','收款与结算'],...(can('admin','ceo','finance')?[['costs','项目成本'],['expenses','费用登记']]:[])],factory:[['production-wood','木工车间'],['production-upholstery','软包车间'],['production-paint','油漆车间'],['production-metal','铁车间']]};
 
 return [['center-'+id,id==='factory'?'生产中心总看板':'中心看板'],...(pages[id]||[])];
}
function centerPeriod(id){const today=opsDate();return centerFilters[id]||{from:today.slice(0,8)+'01',to:today,currency:'CNY'};}
async function renderCenter(el,id,generation){
 centerPage=id;centerData=null;
 const period=centerPeriod(id),query=new URLSearchParams({center:id,...period,...(project&&!['marketing','crm','design','quote'].includes(id)?{project}:{})});
 pageLoading(el,CENTER_NAMES[id],CENTER_DESCRIPTIONS[id],['/api/centers/dashboard?'+query]);
 try{
  const data=await api('/api/centers/dashboard?'+query);if(generation!==renderGeneration)return;centerData=data;const showSharedTasks=()=>{if(generation===renderGeneration)renderSharedAftersalesTasks(el,data.aftersales_tasks||[]);};queueMicrotask(showSharedTasks);if(id==='factory'&&data.production){renderProductionBoard(el,data.production);return;}if(id==='procurement'&&data.procurement){renderProcurementBoard(el,data);return;}if(id==='aftersales'&&data.aftersales){renderAftersalesBoard(el,data);return;}if(id==='engineering'&&data.engineering){renderEngineeringBoard(el,data);return;}if(id==='quote'&&data.costing){renderCostingBoard(el,data);return;}if(id==='design'&&data.design){renderDesignBoard(el,data);return;}if(id==='marketing'){renderTestAccountBoard(el,data);return;}if(id==='crm'&&data.sales?.lifecycle){renderSalesLifecycle(el,data);return;}
  if(['product_rd','software','brand_visual'].includes(id)){
   el.classList.add('department-dashboard');
   const members=data.members||[];
   el.innerHTML=head(CENTER_NAMES[id]+'总看板',CENTER_DESCRIPTIONS[id],can('admin')?button('center-manage-members','分配中心成员','','secondary'):'')+panel('中心成员 · '+members.length+' 人',members.length?table(['员工姓名','岗位'],members.map(m=>`<tr><td>${esc(m.name)}</td><td>${esc(roles[m.role]||m.role)}</td></tr>`)):empty('尚未分配中心成员','管理员可在“人员与权限 → 中心职责”中分配员工。'))+panel('业务工作区',empty('中心已建立','本中心业务流程待补充。员工姓名与集团账号保持同步。'));return;
  }
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
 const title=kind==='spend'?'平台投入登记':'设计任务与工程交接';pageLoading(el,title,'',['/api/centers/records?'+new URLSearchParams({page:kind,...(project&&kind!=='spend'?{project}:{})})]);
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
 if(name==='center-asexpense-new'){
  const r=centerData?.aftersales;if(!r)return true;
  const tickets=r.orders.filter(o=>!['客户承担','供应商承担'].includes(o.cost_responsibility));
  if(!tickets.length){notify('请先建立售后工单，并核对费用承担方');return true;}
  modal('登记公司承担的售后费用',`<p class="full">只填写公司实际承担部分；客户或供应商承担金额不计入。登记后自动汇总到 CEO 年度及月度售后金额。</p>`+select('ticket_id','关联售后工单',tickets.map(o=>({id:o.id,name:o.name+' · '+o.id})))+select('category','费用类别',[{id:'parts',name:'配件'},{id:'freight',name:'运输'},{id:'labor',name:'人工'},{id:'travel',name:'差旅'},{id:'other',name:'其他'}])+input('amount','公司承担金额','number','',true,'min="0.01" step="0.01"')+select('currency','币种',CENTER_CURRENCIES,'CNY')+input('record_date','实际费用日期','date',r.today)+input('reference','费用编号／凭证号（不可重复）')+textarea('note','费用说明',false),p=>centerCall('aftersales-expense',p),'保存费用');return true;
 }
 if(name==='center-asexpense-void'){
  const r=centerData?.aftersales?.expenses?.records.find(r=>r.id===id&&r.source==='aftersales_expenses');if(!r)return true;
  modal('作废售后费用',`<p class="full">${esc(r.reference)} · ${centerMoney(r.minor,r.currency)}。作废后不再计入年度及月度合计，原记录与操作历史会保留。</p>`+textarea('reason','作废原因'),p=>centerCall('aftersales-expense-void',{...p,id}),'确认作废');return true;
 }
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
 if(name==='center-manage-members'){view='employees';await render();return true;}
 if(name==='center-members'){
  const employee=state.employees.find(e=>e.id===id);
  modal('分配中心职责',`<p class="full">${esc(employee.name)}。增加中心职责，原岗位与项目成员权限继续保留。</p><fieldset class="member-list full"><legend>业务中心职责</legend>${['marketing','design','product_rd','software','brand_visual'].map(key=>`<label><input type="checkbox" name="${key}"${employee.centers?.includes(key)?' checked':''}><span>${CENTER_NAMES[key]}</span></label>`).join('')}</fieldset><p class="form-help full">设计任务仍需加入对应项目后才能查看。管理员和 CEO 默认可查看各中心。</p>`,p=>centerCall('members',{employee_id:id,centers:['marketing','design','product_rd','software','brand_visual'].filter(key=>p[key]==='on')}));return true;
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


function renderEngineeringBoard(el,data,options={}){
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
  if(options.embedded){board.querySelector(':scope > .page-head')?.remove();board.querySelectorAll(':scope > .panel')[1]?.remove();board.querySelector(':scope > .center-definitions')?.remove();}
 }
 board.onclick=e=>{const filter=e.target.closest('[data-eng-filter]');if(filter){selected=filter.dataset.engFilter;draw();return;}const edit=e.target.closest('[data-eng-edit]');if(!edit)return;const r=report.orders.find(r=>r.id===edit.dataset.engEdit);if(!r)return;
 const opts=(items,value)=>items.map(x=>`<option value="${esc(x)}" ${value===x?'selected':''}>${esc(x)}</option>`).join('');
 const ownerOptions='<option value="">待分配</option>'+report.employees.map(e=>`<option value="${esc(e.id)}" ${r.owner_id===e.id?'selected':''}>${esc(e.name)}</option>`).join('');
 modal(r.name+' · 工程进度与问题反馈',`<label>工程负责人<select name="owner_id">${ownerOptions}</select></label><label>交货期<input type="date" name="delivery_date" value="${esc(r.delivery_date||'')}"></label><label>当前阶段<select name="stage">${opts(r.stage==='未来订单'?['未来订单']:stages.filter(s=>s!=='未来订单'),r.stage)}</select></label>${depts.map((d,i)=>`<label>${d}进度（%）<input name="progress_${i}" type="number" min="0" max="100" step="1" value="${r.progress[d]??''}" placeholder="待登记"></label>`).join('')}<label>卡点部门<select name="blocker_dept"><option value="">待登记 / 无卡点</option>${opts(['工程部','设计部','核算部','商务部','木工部','软包部','油漆部','铁车间','采购部','安装部','其他'],r.blocker_dept)}</select></label><label class="full">卡点原因<textarea name="blocker_reason">${esc(r.blocker_reason)}</textarea></label><label class="full">问题反馈<textarea name="issue">${esc(r.issue)}</textarea></label>`,p=>centerCall('engineering-progress',{...p,id:r.id,project_id:r.project_id,version:r.version,progress:Object.fromEntries(depts.map((d,i)=>[d,p['progress_'+i]]))}));
 };
 draw();
}

function aftersalesExpensePanel(r){
 const cost=r.expenses;if(!cost)return '';
 const money=items=>items.length?items.map(a=>centerMoney(a.minor,a.currency)).join(' / '):'尚无登记';
 const canWrite=r.can_edit&&!session.read_only;
 return `<section class="as-section aftersales-cost-panel"><div class="as-toolbar"><div><h3>售后总金额 · 公司承担</h3><p class="as-footnote">年度已登记：${money(cost.annual)}　·　本月：${money(cost.monthly)}</p></div>${canWrite?button('center-asexpense-new','登记售后费用','','secondary'):''}</div>${cost.records.length?table(['费用日期','项目／工单','费用类别','公司承担金额','费用编号／凭证号','操作'],cost.records.map(item=>`<tr><td>${esc(item.date)}</td><td>${esc(item.project_name)}<small>${esc(item.ticket_id||'原费用登记')}</small></td><td>${esc(item.category_label)}</td><td>${centerMoney(item.minor,item.currency)}</td><td>${esc(item.reference)}</td><td>${canWrite&&item.source==='aftersales_expenses'?button('center-asexpense-void','作废',item.id,'quiet'):'—'}</td></tr>`)):'<p class="as-footnote">尚未登记费用，暂无可汇总金额。</p>'}<p class="as-footnote">${esc(cost.note)}</p></section>`;
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
   aftersalesExpensePanel(r)+
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

const AFTERSALES_ANALYSIS_MARKUP="<header class=\"rc-heading\"><div><h1>售后问题分析与改善</h1><p>找到反复出问题的设备，从根源减少下一次售后。</p></div><span class=\"rc-demo\">集团记录 · 售后工作台已接通</span></header><section class=\"rc-annual\" aria-label=\"年度问题总计\" id=\"ra-annual\"></section><div class=\"rc-scope\" id=\"ra-scope\"></div><div class=\"rc-grid\" style=\"margin-bottom:16px\"><section class=\"rc-panel\"><div class=\"rc-panelhead\"><h2>问题集中在哪里</h2><span class=\"rc-caption\">区域 × 设备款式 · 点击查看</span></div><div id=\"rc-matrix\" class=\"rc-matrix\"></div><p class=\"rc-focus\">单元格为问题记录数；“—”仅表示暂无问题记录，不能据此判断区域或款式更可靠。</p></section><section class=\"rc-panel\"><div class=\"rc-panelhead\"><h2>常见问题集中在哪些款</h2><span class=\"rc-caption\">按问题记录数排序</span></div><div id=\"rc-ranking\"></div></section></div>\n<section class=\"rc-panel\"><div class=\"rc-panelhead\"><h2>设备用了多久首次出问题</h2><span class=\"rc-caption\">每台故障设备只计首次故障</span></div><div id=\"rc-age-bands\" class=\"rc-age-bands\"></div><p id=\"rc-age-note\" class=\"rc-foot\"></p></section><section class=\"rc-panel\"><div class=\"rc-panelhead\"><h2>需要重点解决的问题</h2><span class=\"rc-caption\">优先关注维修后复发及跨设备同类问题</span></div><div class=\"rc-scroll\"><table><thead><tr><th>设备款式 / 区域</th><th>主要问题</th><th>问题 / 复发</th><th>已关联设备</th><th>首次故障用时</th><th>维修后复发间隔</th><th>根因进度</th><th>改善进度</th></tr></thead><tbody id=\"rc-cases\"></tbody></table></div><p class=\"rc-foot\">设备编号未关联时不推断台数；完整交付基数接通前不计算设备发生率。</p></section>\n<section class=\"rc-panel\" id=\"rc-case-detail\" aria-live=\"polite\"></section><details><summary>数据来源与统计说明</summary><div id=\"ra-notices\"></div></details><section class=\"rc-panel rr-center\" aria-label=\"售后分析报告\"><div class=\"rc-panelhead\"><div><h2>售后分析报告</h2><p class=\"rc-caption\">月度发现问题 · 季度检验改善 · 年度推动产品调整</p></div><span class=\"rc-tag rc-wait\">售后网站待接通</span></div><div class=\"rr-toolbar\"><div class=\"rr-period\" aria-label=\"报告类型\"><button type=\"button\" data-report-type=\"month\" aria-pressed=\"true\">月报</button><button type=\"button\" data-report-type=\"quarter\" aria-pressed=\"false\">季报</button><button type=\"button\" data-report-type=\"year\" aria-pressed=\"false\">年报</button></div><label class=\"rr-field\">报告期间<select id=\"rr-period\" aria-label=\"报告期间\"></select></label><button type=\"button\" id=\"rr-preview\">预览报告</button><button type=\"button\" class=\"rr-download\" disabled aria-describedby=\"rr-status\">下载 PPT</button></div><p id=\"rr-status\" class=\"rc-caption\">当前展示示例报告；接通售后网站后，下载可编辑 PPT。</p><div class=\"rr-preview\"><div class=\"rr-outline\" id=\"rr-outline\" aria-label=\"报告目录\"></div><div class=\"rr-stage\"><div class=\"rr-slide\" id=\"rr-slide\" aria-live=\"polite\"></div><div class=\"rr-pager\"><button type=\"button\" id=\"rr-prev\" aria-label=\"上一页报告\">上一页</button><span id=\"rr-page\"></span><button type=\"button\" id=\"rr-next\" aria-label=\"下一页报告\">下一页</button></div></div></div><p id=\"rr-cutoff\" class=\"rc-foot\"></p></section>";
async function renderAftersalesAnalysis(el,generation){
 pageLoading(el,'售后问题分析与改善','正在汇总授权范围内的售后记录。',['/api/centers/dashboard?'+new URLSearchParams({center:'aftersales',...(project?{project}:{})})]);
 try{const data=await api('/api/centers/dashboard?'+new URLSearchParams({center:'aftersales',...(project?{project}:{})}));if(generation!==renderGeneration)return;
 const analysis=data.aftersales.analysis,records=analysis.records,today=analysis.today;
 el.innerHTML='<div id="aftersales-analysis">'+AFTERSALES_ANALYSIS_MARKUP+'</div>';const root=el.firstElementChild,q=s=>root.querySelector(s);
 const text=v=>esc(v??''),distinct=a=>[...new Set(a.filter(Boolean))];
 const dayGap=(a,b)=>a&&b?Math.round((Date.parse(b+'T00:00:00Z')-Date.parse(a+'T00:00:00Z'))/86400000):null;
 const join=(items,fallback)=>distinct(items).join('；')||fallback;
 const deviceKey=r=>r.device?r.project_id+':'+r.device:null;
 const firstByDevice=new Map();
 for(const row of records){if(!row.device||!row.fault||row.fault>today)continue;const key=deviceKey(row),old=firstByDevice.get(key);if(!old||row.fault<old.fault)firstByDevice.set(key,row);}
 const firstDevices=[...firstByDevice.values()].map(r=>({...r,age:dayGap(r.activation,r.fault),deliveryAge:dayGap(r.delivery,r.fault)}));
 const deviceRows=rows=>{const keys=new Set(rows.map(deviceKey).filter(Boolean));return firstDevices.filter(r=>keys.has(deviceKey(r)));};
 const range=(values,empty='待补日期')=>{const a=values.filter(v=>Number.isFinite(v)&&v>=0);return a.length?(Math.min(...a)===Math.max(...a)?Math.min(...a):Math.min(...a)+'–'+Math.max(...a))+' 天':empty;};
 const map=new Map();for(const r of records){const key=JSON.stringify([r.model,r.region,r.problem]);if(!map.has(key))map.set(key,[]);map.get(key).push(r);}
 const groups=[...map.values()].map((rows,i)=>({id:'group-'+i,rows,model:rows[0].model,region:rows[0].region,problem:rows[0].problem,n:rows.length,devices:distinct(rows.map(deviceKey)).length,repeat:rows.filter(r=>r.recurrence).length})).sort((a,b)=>b.repeat-a.repeat||b.n-a.n);
 let selected=groups[0]?.id||'',reportType='month',reportPeriod=today.slice(0,7),reportSlide=0;
 const groupCurrent=()=>groups.find(g=>g.id===selected);
 const known=firstDevices.filter(d=>d.age!==null&&d.age>=0);
 function draw(){
 const annual=records.filter(r=>r.date&&r.date>=analysis.year+'-01-01'&&r.date<=today);
 q('#ra-annual').innerHTML='<div><h2>'+analysis.year+' 年度问题总计</h2><p>1 月 1 日至 '+text(today)+' · 含已关闭记录 · '+annual.filter(r=>r.date_basis==='反馈日期').length+' 条暂按反馈日期</p></div><div><strong>'+annual.length+'</strong><span> 条问题</span></div>';
 q('#ra-scope').innerHTML='<span>全部历史 · 含已关闭记录</span><span><strong>'+records.length+'</strong> 条问题</span><span><strong>'+distinct(records.map(deviceKey)).length+'</strong> 台已关联设备</span><span><strong>'+records.filter(r=>r.recurrence).length+'</strong> 次已核实维修后复发</span>';
 const regions=distinct(records.map(r=>r.region)),models=distinct(records.map(r=>r.model));const matrix=q('#rc-matrix');matrix.style.gridTemplateColumns='minmax(85px,1fr) repeat('+Math.max(models.length,1)+',minmax(100px,1fr))';matrix.style.minWidth=(100*Math.max(models.length,1)+95)+'px';if(!matrix.parentElement.classList.contains('rc-scroll')){const wrap=document.createElement('div');wrap.className='rc-scroll';matrix.before(wrap);wrap.append(matrix);}
 matrix.innerHTML=!records.length?'<p class="rc-caption">暂无售后问题记录</p>':'<div></div>'+models.map(m=>'<div class="rc-col">'+text(m)+'</div>').join('')+regions.map(region=>'<div class="rc-region">'+text(region)+'</div>'+models.map(model=>{const pair=groups.filter(g=>g.model===model&&g.region===region),rows=pair.flatMap(g=>g.rows),n=rows.length;return n?'<button type="button" class="rc-cell '+(n>=5?'rc-high':'')+'" data-analysis-case="'+pair[0].id+'" aria-pressed="'+pair.some(g=>g.id===selected)+'"><strong>'+n+'</strong><small>'+distinct(rows.map(deviceKey)).length+' 台已关联</small></button>':'<div class="rc-empty">—</div>';}).join('')).join('');
 q('#rc-ranking').innerHTML=[...groups].sort((a,b)=>b.n-a.n).slice(0,6).map(g=>'<div class="rc-rankrow"><div><strong>'+text(g.problem)+'</strong><small>'+text(g.model)+' · '+text(g.region)+'</small><div class="rc-bar"><i data-analysis-percent="'+g.n/Math.max(records.length,1)*100+'"></i></div></div><span>'+g.n+' 条</span></div>').join('')||'<p>暂无问题记录</p>';
 q('#rc-cases').innerHTML=groups.map(g=>{const ds=deviceRows(g.rows),ages=ds.map(d=>d.age);const confirmed=g.rows.every(r=>r.cause_status==='已验证')&&distinct(g.rows.map(r=>r.cause)).length===1;return '<tr class="'+(g.id===selected?'rc-chosen':'')+'"><td><button type="button" class="rc-case" data-analysis-case="'+g.id+'">'+text(g.model)+'</button><small>'+text(g.region)+'</small></td><td>'+text(g.problem)+'<small>'+text(join(g.rows.map(r=>r.part),'待登记'))+'</small></td><td>'+g.n+' 条 / '+g.repeat+' 次<small>'+g.rows.filter(r=>r.repeat_marked&&!r.recurrence).length+' 条重复标记待核实</small></td><td>'+g.devices+' 台<small>'+g.rows.filter(r=>!r.device).length+' 条设备待关联</small></td><td>'+range(ages)+'<small>按实际启用日</small></td><td>'+range(g.rows.filter(r=>r.recurrence).map(r=>dayGap(r.repair,r.fault)),'待补复发日期')+'</td><td><span class="rc-tag '+(confirmed?'rc-confirmed':'rc-wait')+'">'+(confirmed?'已验证':'待逐项验证')+'</span></td><td>'+text(join(g.rows.map(r=>r.validation_status),'待验证'))+'</td></tr>';}).join('')||'<tr><td colspan="8">暂无问题记录，专门售后网站接通后将按实际资料分析。</td></tr>';
 const bands=[['30 天以内',d=>d.age<=30],['31–90 天',d=>d.age>30&&d.age<=90],['91–180 天',d=>d.age>90&&d.age<=180],['181 天及以上',d=>d.age>180]];
 q('#rc-age-bands').innerHTML=bands.map(([label,test])=>{const n=known.filter(test).length;return '<div class="rc-age-band"><span>'+label+'</span><strong>'+n+' 台</strong><div class="rc-bar"><i data-analysis-percent="'+n/Math.max(known.length,1)*100+'"></i></div></div>';}).join('');
 q('#rc-age-note').textContent='有完整首次故障与启用日期 '+known.length+' 台；'+records.filter(r=>!r.device).length+' 条记录待关联设备，'+records.filter(r=>!r.fault).length+' 条待补故障日期。交付后天数不混入使用时长分布。';
 const g=groupCurrent();const detail=q('#rc-case-detail');if(!g){detail.innerHTML='<h2>问题追踪 · 从现象到验证</h2><p class="rc-foot">暂无可追踪记录</p>';return;}
 const rows=g.rows;detail.innerHTML='<div class="rc-panelhead"><h2>问题追踪 · 从现象到验证</h2><select class="rc-select" id="ra-case" aria-label="选择重点问题">'+groups.map(x=>'<option value="'+x.id+'"'+(x.id===g.id?' selected':'')+'>'+text(x.model)+' · '+text(x.region)+' · '+text(x.problem)+'</option>').join('')+'</select></div><div class="rc-casehead"><div><strong>'+text(g.problem)+'</strong><small>'+text(g.model)+' · '+text(g.region)+'</small></div></div><div class="rc-chain"><section><span class="rc-kicker">01 发现问题</span><h3>'+g.n+' 条记录 · '+g.devices+' 台已关联设备</h3><div class="rc-item"><b>故障现象</b>'+text(join(rows.map(r=>r.description),'待补故障描述'))+'</div><div class="rc-item"><b>证据 / 待补资料</b>'+text(join(rows.map(r=>r.evidence),'待补证据'))+'</div></section><section><span class="rc-kicker">02 找到根因并整改</span><h3>原因逐项验证</h3><div class="rc-item"><b>记录中的原因 · 不自动判定根因</b>'+text(join(rows.map(r=>r.cause),'原因待排查'))+'</div><div class="rc-item"><b>措施</b>'+text(join(rows.map(r=>r.action),'待制定'))+'</div><div class="rc-item"><b>责任人</b>'+text(join(rows.map(r=>r.owner),'待分配'))+'</div></section><section><span class="rc-kicker">03 验证是否真正解决</span><h3>'+text(join(rows.map(r=>r.validation_status),'待验证'))+'</h3><p class="rc-evidence">'+text(join(rows.map(r=>r.validation),'待登记'))+'</p><div class="rc-validate"><strong>以证据和观察结果确认</strong>工单关闭不等于整改已经验证有效；待补复发、运行时长和新批次表现。</div></section></div><details><summary>原始售后记录 · '+rows.length+' 条</summary>'+rows.map(r=>'<div class="rc-record"><span>'+text(r.id)+' · '+text(r.project)+(r.shared_test?' · 测试数据':'')+'<small> · '+text(r.description)+'</small></span><span>'+text(r.date||'日期待补')+' · '+text(r.date_basis)+'</span></div>').join('')+'</details><section class="rc-device-times"><h3>设备交付与故障时间</h3><div class="rc-scroll"><table><thead><tr><th>记录 / 设备</th><th>交付日期</th><th>启用日期</th><th>首次故障日期</th><th>首次故障用时</th><th>本次故障日期</th><th>上次维修完成</th><th>复发间隔</th></tr></thead><tbody>'+rows.map(r=>{const first=firstByDevice.get(deviceKey(r));const age=first?dayGap(first.activation,first.fault):null,deliveryAge=first?dayGap(first.delivery,first.fault):null;return '<tr><td>'+text(r.id)+'<small>'+text(r.device||'设备待关联')+'</small></td><td>'+text(r.delivery||'待补')+'</td><td>'+text(r.activation||'待补')+'</td><td>'+text(first?.fault||'待补')+'</td><td>'+(age!==null&&age>=0?age+' 天':deliveryAge!==null&&deliveryAge>=0?'交付后 '+deliveryAge+' 天<small>非实际使用时长</small>':'待补日期')+'</td><td>'+text(r.fault||'待补')+'</td><td>'+text(r.repair||'待补')+'</td><td>'+(r.recurrence?dayGap(r.repair,r.fault)+' 天':'待核实')+'</td></tr>';}).join('')+'</tbody></table></div></section>';
 }
 const drawUnstyled=draw;draw=()=>{drawUnstyled();root.querySelectorAll('[data-analysis-percent]').forEach(mark=>{const value=Number(mark.dataset.analysisPercent);mark.style.width=(Number.isFinite(value)?Math.max(0,Math.min(100,value)):0)+'%';});};
 const reportTypes={month:'月报',quarter:'季报',year:'年报'};
 const titles=['报告封面','问题与复发概况','款式与区域集中点','首次故障与使用时长','根因与整改进展','验证结果与下期行动'];
 const years=distinct([today.slice(0,4),...records.map(r=>r.date?.slice(0,4))]).filter(y=>y<=today.slice(0,4)).sort().reverse();
 function options(){return years.flatMap(y=>reportType==='year'?[[y,y+' 年']]:reportType==='quarter'?[1,2,3,4].map(n=>[y+'-Q'+n,y+' 年第 '+n+' 季度']):Array.from({length:12},(_,i)=>[y+'-'+String(i+1).padStart(2,'0'),y+' 年 '+(i+1)+' 月'])).filter(([v])=>v.slice(0,4)<today.slice(0,4)||reportType==='year'||reportType==='month'&&v<=today.slice(0,7)||reportType==='quarter'&&Number(v.slice(-1))<=Math.ceil(Number(today.slice(5,7))/3));}
 function periodRange(){let start,end;if(reportType==='month'){start=reportPeriod+'-01';const [y,m]=reportPeriod.split('-').map(Number);end=new Date(Date.UTC(y,m,0)).toISOString().slice(0,10);}else if(reportType==='quarter'){const y=Number(reportPeriod.slice(0,4)),n=Number(reportPeriod.slice(-1));start=y+'-'+String(n*3-2).padStart(2,'0')+'-01';end=new Date(Date.UTC(y,n*3,0)).toISOString().slice(0,10);}else{start=reportPeriod+'-01-01';end=reportPeriod+'-12-31';}return {start,end:end>today?today:end,partial:end>today};}
 function drawReport(){q('#rr-status').textContent='当前预览汇总集团原记录与新售后工作台已提交的问题；可编辑 PPT 下载功能尚未开放。';root.querySelectorAll('[data-report-type]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.reportType===reportType)));const opts=options();if(!opts.some(p=>p[0]===reportPeriod))reportPeriod=opts[0]?.[0]||today.slice(0,4);q('#rr-period').innerHTML=opts.map(([id,name])=>'<option value="'+id+'"'+(id===reportPeriod?' selected':'')+'>'+text(name)+'</option>').join('');const {start,end,partial}=periodRange(),rows=records.filter(r=>r.date&&r.date>=start&&r.date<=end),knownFirst=known.filter(r=>r.fault>=start&&r.fault<=end),label=opts.find(p=>p[0]===reportPeriod)?.[1]||reportPeriod;
 const relevant=groups.map(g=>({...g,rows:g.rows.filter(r=>rows.includes(r))})).filter(g=>g.rows.length).sort((a,b)=>b.rows.length-a.rows.length);
 const stats='<div class="rr-report-stats"><div><strong>'+rows.length+'</strong><span>本期问题记录</span></div><div><strong>'+distinct(rows.map(deviceKey)).length+'</strong><span>已关联设备</span></div><div><strong>'+rows.filter(r=>r.recurrence).length+'</strong><span>已核实维修后复发</span></div></div>';
 const slideRows=relevant.map(g=>'<div class="rr-row"><span>'+text(g.model)+' · '+text(g.region)+'<br><small>'+text(g.problem)+'</small></span><span>'+g.rows.length+' 条</span></div>').join('')||'<p>本期暂无已登记日期的问题记录。</p>';
 const contents=[
 '<div class="rr-eyebrow">YIFUN LIFE / 售后分析'+reportTypes[reportType]+'</div><h3>'+text(label)+'<br>售后问题分析与改善报告</h3><p class="rr-subtitle">哪些设备反复出问题，怎样减少下一次售后</p><p>统计期间：'+start+' 至 '+end+(partial?'（本期未结束）':'')+'</p>'+stats,
 '<h3>问题与复发概况</h3>'+stats+'<p>其中 '+rows.filter(r=>!r.device).length+' 条设备待关联，'+rows.filter(r=>r.date_basis==='反馈日期').length+' 条暂按反馈日期归期；全部历史中 '+records.filter(r=>!r.date).length+' 条日期缺失，未混入期间统计。</p><footer>专门售后网站与完整历史资料接通前，不生成无依据的同比或环比。</footer>',
 '<h3>款式与区域集中点</h3>'+slideRows+'<footer>交付基数尚未完整接通，不计算设备发生率；投诉少不等于设备更可靠。</footer>',
 '<h3>首次故障与使用时长</h3>'+[['30 天以内',d=>d.age<=30],['31–90 天',d=>d.age>30&&d.age<=90],['91–180 天',d=>d.age>90&&d.age<=180],['181 天及以上',d=>d.age>180]].map(([label,f])=>'<div class="rr-row"><span>'+label+'</span><span>'+knownFirst.filter(f).length+' 台</span></div>').join('')+'<footer>仅计本期首次故障且有启用日期的设备；交付后天数不作为实际使用时长。</footer>',
 '<h3>根因与整改进展</h3>'+(relevant.map(g=>'<div class="rr-row"><span>'+text(g.model)+' · '+text(g.region)+'<br><small>'+text(join(g.rows.map(r=>r.cause),'原因待排查'))+'</small></span><span>'+text(join(g.rows.map(r=>r.cause_status),'待验证'))+'</span></div>').join('')||'<p>暂无本期关联资料。</p>')+'<footer>截至 '+today+' 的状态快照；原因有证据且登记已验证时才标为已验证。</footer>',
 '<h3>验证结果与下一步</h3>'+(relevant.map(g=>'<div class="rr-row"><span>'+text(g.model)+' · '+text(g.region)+'<br><small>'+text(join(g.rows.map(r=>r.action),'待制定措施'))+'<br>'+text(join(g.rows.map(r=>r.validation),'待验证'))+'</small></span><span>'+text(join(g.rows.map(r=>r.owner),'待分配'))+'</span></div>').join('')||'<p>等待本期问题资料。</p>')+'<footer>工单关闭与整改验证分别记录；待补观察时长、新批次与复发证据。</footer>'
 ];q('#rr-outline').innerHTML=titles.map((t,i)=>'<button type="button" data-ra-slide="'+i+'" aria-pressed="'+(i===reportSlide)+'">'+String(i+1).padStart(2,'0')+' '+t+'</button>').join('');q('#rr-slide').innerHTML=contents[reportSlide];q('#rr-page').textContent=(reportSlide+1)+' / 6 页 · 现有资料预览';q('#rr-prev').disabled=reportSlide===0;q('#rr-next').disabled=reportSlide===5;q('#rr-cutoff').textContent='规划文件名：售后分析_'+reportPeriod+'_'+reportTypes[reportType]+'.pptx · '+(partial?'本期未结束，截至 '+today:'完整期间')+' · PPT 下载待售后网站接通后启用。';}
 root.addEventListener('click',e=>{const item=e.target.closest('[data-analysis-case]');if(item){selected=item.dataset.analysisCase;draw();}const type=e.target.closest('[data-report-type]');if(type){reportType=type.dataset.reportType;reportPeriod=reportType==='year'?today.slice(0,4):reportType==='quarter'?today.slice(0,4)+'-Q'+Math.ceil(Number(today.slice(5,7))/3):today.slice(0,7);reportSlide=0;drawReport();}const slide=e.target.closest('[data-ra-slide]');if(slide){reportSlide=Number(slide.dataset.raSlide);drawReport();}if(e.target.closest('#rr-next')){reportSlide=Math.min(5,reportSlide+1);drawReport();}if(e.target.closest('#rr-prev')){reportSlide=Math.max(0,reportSlide-1);drawReport();}if(e.target.closest('#rr-preview')){reportSlide=0;drawReport();}});
 root.addEventListener('change',e=>{if(e.target.id==='ra-case'){selected=e.target.value;draw();}if(e.target.id==='rr-period'){reportPeriod=e.target.value;reportSlide=0;drawReport();}});
 q('#ra-notices').innerHTML=analysis.notices.map(n=>'<p>'+text(n)+'</p>').join('');draw();drawReport();
 }catch(error){if(generation===renderGeneration)el.innerHTML=head('售后问题统计','读取失败，请刷新重试。')+'<p class="error">'+esc(error.message)+'</p>';}
}

function renderProcurementBoard(el,data){
 const d=data.procurement;let tab='overview',expanded=null;
 const table=(headers,rows)=>`<div class="table-wrap"><table><thead><tr>${headers.map(h=>`<th scope="col">${h}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
 const money=v=>v==null?'待核实':centerMoney(v,'CNY');
 const qty=o=>Object.entries(o.units).map(([u,q])=>`${q} ${esc(u)}`).join(' / ')||'—';
 const count=(o,key)=>{const a={};o.items.forEach(i=>a[i.unit]=(a[i.unit]||0)+i[key]);return Object.entries(a).map(([u,q])=>`${q} ${esc(u)}`).join(' / ')||'—'};
 const stages=['待确认','待报价','待下单','待到货','待验收','待对账'];
 const detail=o=>{const related=d.orders.filter(x=>o.project_id?x.project_id===o.project_id:x.id===o.id);const items=related.flatMap(x=>x.items.map(i=>({...i,order:x}))).sort((a,b)=>(a.received>=a.quantity)-(b.received>=b.quantity));return `<div class="pc-detail"><div class="pc-row"><h3>${esc(o.project)} · 全部采购物品</h3><button type="button" data-pc-close>收起详情</button></div>${table(['项目','采购物品','业务员','工程师','采购数量','已下单数量','已发货数量','已完成数量','到货情况','预计到货时间','卡点'],items.map(i=>`<tr><td>${esc(i.order.project)}</td><td>${esc(i.name)}<small>${esc(i.order.number)}</small></td><td>${esc(i.order.sales)}</td><td>${esc(i.order.engineer)}</td><td>${i.quantity} ${esc(i.unit)}</td><td>${i.ordered}</td><td>${i.shipped}</td><td>${i.completed}</td><td>${i.received>=i.quantity?'已到货':i.received?'部分到货':'未到货'}<small>已到 ${i.received}/${i.quantity}${i.actual?' · '+esc(i.actual.slice(0,10)):''}</small></td><td>待登记${i.order.estimated_ship?`<small>预计发货 ${esc(i.order.estimated_ship)}</small>`:''}</td><td class="pc-note">${esc(i.issue)}</td></tr>`))}<p class="pc-muted">未齐货在前，已到货在后。已完成为入库数量；尚无采购单的工程需求仍需在原工作台登记。</p></div>`};
 const orderTable=rows=>rows.length?table(['采购单 / 项目','采购总数量','已下单数量','已发货数量','已完成数量','预计采购完成时间','跟进'],rows.map(o=>`<tr><td>${esc(o.number)}<small>${esc(o.project)}</small></td><td>${qty(o)}</td><td>${qty(o)}</td><td>${count(o,'shipped')}</td><td>${count(o,'completed')}</td><td>待登记</td><td><button type="button" class="quiet" data-pc-order="${esc(o.id)}" aria-expanded="${expanded===o.id}">${expanded===o.id?'收起':'详情'}</button></td></tr>${tab==='orders'&&expanded===o.id?`<tr><td colspan="7" class="pc-expanded">${detail(o)}</td></tr>`:''}`)):empty('暂无当前采购订单','采购工作台中的授权订单会自动汇总。');
 const issues=d.orders.filter(o=>o.late||o.rejected).sort((a,b)=>Number(b.late)-Number(a.late));
 function draw(){
 el.classList.add('department-dashboard');
 let html=head('采购中心','从采购需求到供应商确认、发货和验收。')+`<div id="pc-board"><div class="pc-tabs">${[['overview','采购驾驶舱'],['orders','采购跟进'],['suppliers','供应商'],['payments','付款与对账']].map(([id,name])=>`<button type="button" data-pc-tab="${id}" aria-pressed="${tab===id}">${name}</button>`).join('')}</div>`;
 if(tab==='overview'){
 html+=`<p class="pc-muted">${esc(d.today)} · 当前账号授权数据 · 金额：人民币</p><dl class="center-metrics">${[['年总采购金额',money(d.year_amount),d.year+'年度累计'],['本月采购金额',money(d.month_amount),'本月累计'],['供应商付款率',d.paid_rate==null?'待核实':d.paid_rate+'%','剩余应付 '+money(d.remaining)],['未来7天待付款','待登记','尚无结构化付款到期计划']].map(([label,value,note])=>`<div><dt>${label}</dt><dd>${value}</dd><p>${note}</p></div>`).join('')}</dl>`;
 html+=panel('采购流程',`<div class="pc-flow">${['总采购订单',...stages].map(s=>`<button type="button" data-pc-tab="orders">${s}<strong>${s==='总采购订单'?d.orders.length:['待报价','待下单'].includes(s)?'待接入':d.orders.filter(o=>o.stage===s).length}</strong></button>`).join('')}</div>`);
 html+=panel('近期交付跟进',orderTable(d.orders.slice(0,5)));
 html+=`<div class="pc-bottom">${panel('优先处理',issues.length?issues.slice(0,5).map(o=>`<p>${esc(o.project)} · ${o.late?'发货逾期':'验收异常'} <button type="button" class="quiet" data-pc-order="${esc(o.id)}">查看采购单</button></p>`).join(''):empty('暂无延期与验收异常','按当前采购记录统计。'))}${panel('本月采购结构',(()=>{const groups={};d.orders.filter(o=>o.order_date.startsWith(d.today.slice(0,7))&&o.currency==='CNY').forEach(o=>groups[o.supplier]=(groups[o.supplier]||0)+o.subtotal);return Object.keys(groups).length?table(['供应商','本月在手订单物料小计'],Object.entries(groups).map(([s,v])=>`<tr><td>${esc(s)}</td><td>${money(v)}</td></tr>`)):empty('暂无本月采购结构','按本月在手采购单物料金额展示，不代替含税应付金额。')})())}</div>`;
 }
 if(tab==='orders')html+=panel('采购跟进',orderTable(d.orders));
 if(tab==='suppliers'){
 html+=panel('供应商延期与问题跟进',issues.length?table(['供应商','项目 / 采购单','问题','约定发货','最新预计发货','当前进展 / 卡点','跟进人','跟进'],issues.map(o=>`<tr><td>${esc(o.supplier)}</td><td>${esc(o.project)}<small>${esc(o.number)}</small></td><td>${o.late?'发货逾期':''}${o.rejected?' 验收异常':''}</td><td>${esc(o.due||'待登记')}</td><td>${esc(o.estimated_ship||'待登记')}</td><td class="pc-note">${esc(o.note||'待补充处理进展')}</td><td>${esc(o.owner)}</td><td><button type="button" class="quiet" data-pc-order="${esc(o.id)}">查看项目</button></td></tr>`)):empty('暂无供应商延期与验收问题','按授权范围内当前采购订单统计。'));
 const units=[...new Set(d.annual_suppliers.flatMap(s=>Object.keys(s.units)))];
 const ranked=units.length===1?[...d.annual_suppliers].sort((a,b)=>(b.units[units[0]]||0)-(a.units[units[0]]||0)):d.annual_suppliers;
 html+=panel('供应商采购量排名 · '+d.year+'年度',table(['排名','供应商','年度采购量（分单位）','年度采购订单数','年度确认应付金额'],ranked.map((s,i)=>`<tr><td>${i+1}</td><td>${esc(s.name)}</td><td>${qty(s)}</td><td>${s.orders}</td><td>${!d.finance||s.unknown_amount?'待核实':money(s.amount)}</td></tr>`))+`<p class="pc-muted">${units.length>1?'单位不同不混加，按订单笔数排序；采购量按单位展示。':'按年度采购数量降序。'}</p>`);
 const known=d.orders.filter(o=>o.amount!=null).sort((a,b)=>b.amount-a.amount);
 html+=panel('订单采购金额排名 · 当前采购订单',known.length?table(['排名','采购单 / 项目','供应商','确认应付金额','阶段','跟进'],known.map((o,i)=>`<tr><td>${i+1}</td><td>${esc(o.number)}<small>${esc(o.project)}</small></td><td>${esc(o.supplier)}</td><td>${money(o.amount)}</td><td>${esc(o.stage)}</td><td><button type="button" class="quiet" data-pc-order="${esc(o.id)}">查看项目</button></td></tr>`)):empty('暂无可排名的确认金额','金额尚未确认或当前账号没有财务权限。'));
 }
 if(tab==='payments')html+=panel('付款与对账',`<p>未来7天付款计划：待登记付款到期日期后汇总。</p>`+table(['采购单 / 项目','供应商','确认应付','已付款','剩余应付'],d.orders.map(o=>`<tr><td>${esc(o.number)}<small>${esc(o.project)}</small></td><td>${esc(o.supplier)}</td><td>${money(o.amount)}</td><td>${money(o.paid)}</td><td>${money(o.amount==null||o.paid==null?null:Math.max(o.amount-o.paid,0))}</td></tr>`)));
 html+=`<details class="center-definitions"><summary>数据来源与统计说明</summary>${d.notices.map(n=>`<p>${esc(n)}</p>`).join('')}</details></div>`;el.innerHTML=html;
 }
 el.onclick=event=>{const b=event.target.closest('[data-pc-tab],[data-pc-order],[data-pc-close]');if(!b)return;if(b.dataset.pcTab){tab=b.dataset.pcTab;expanded=null}else if(b.hasAttribute('data-pc-close'))expanded=null;else{const id=b.dataset.pcOrder;expanded=tab==='orders'&&expanded===id?null:id;tab='orders'}draw()};draw();
}
async function renderProductionWorkshop(el,key,generation){
 pageLoading(el,'生产中心','正在读取车间登记进度。',['/api/centers/dashboard?'+new URLSearchParams({center:'factory',...(project?{project}:{})})]);
 try{const data=await api('/api/centers/dashboard?'+new URLSearchParams({center:'factory',...(project?{project}:{})}));if(generation!==renderGeneration)return;renderProductionBoard(el,data.production,key);}
 catch(error){if(generation===renderGeneration)el.innerHTML=head('车间看板','读取失败，请刷新重试。')+'<p class="error">'+esc(error.message)+'</p>';}
}
function renderProductionBoard(el,report,key='all'){
 const workshop=report.workshops.find(w=>w.id===key),all=report.orders,rows=workshop?workshop.orders:all;
 const labels=report.workshops;
 el.innerHTML='<div class="department-dashboard production-dashboard"></div>';const board=el.firstElementChild;
 const dateText=r=>r.days==null?'交货期待登记':r.days<0?'已逾期 '+(-r.days)+' 天':r.days===0?'今天交货':'距交货 '+r.days+' 天';
 const pct=(v,label)=>v==null?'<span class="muted">待登记</span>':`<div class="production-progress"><span>${v}%</span><progress max="100" value="${v}" aria-label="${esc(label)}进度 ${v}%"></progress></div>`;
 const notice=`<details class="center-definitions"><summary>数据来源与统计说明</summary>${report.notices.map(n=>'<p>'+esc(n)+'</p>').join('')}</details>`;
 if(!workshop){
  board.innerHTML=head('生产中心总看板','木工 · 软包 · 油漆 · 铁车间，统一查看订单、登记进度与卡点。')+'<div class="production-lifecycle"></div>'+
   panel('各车间登记情况',`<div class="production-workshops">${labels.map(w=>`<button type="button" class="production-workshop" data-view="production-${w.id}"><strong>${esc(w.name)}</strong><span>进行中 <b>${w.active}</b> 单 · 未开始 ${w.not_started} 单</span><span>进度100% ${w.complete} 单 · 卡点 ${w.blocked} 单</span><small>另有 ${w.unknown} 单进度待登记</small></button>`).join('')}</div>`)+
   panel('生产订单与各车间进度 · '+all.length+' 单',`<div class="department-table-wrap"><table><thead><tr>${['订单 / 项目','交货期','工程负责人',...labels.map(w=>w.name),'卡点 / 问题'].map(h=>'<th>'+h+'</th>').join('')}</tr></thead><tbody>${all.map(r=>`<tr><td><strong>${esc(r.name)}</strong><small>${esc(r.number)}${r.shared_test?' · 测试数据':''}</small><small>${esc(r.stage)}</small></td><td>${esc(r.delivery_date||'待登记')}<small>${esc(dateText(r))}</small></td><td>${esc(r.engineering_owner)}</td>${labels.map(w=>'<td>'+pct(r.progress[w.department],w.name)+'</td>').join('')}<td class="production-issue">${esc(r.blocker_dept||'未登记卡点')}<small>${esc(r.blocker_reason||r.issue||'暂无问题反馈')}</small></td></tr>`).join('')||'<tr><td colspan="8">暂无生产范围订单；已登记生产中或明确分派工厂后在此汇总。</td></tr>'}</tbody></table></div>`)+notice;
  if(report.engineering)renderEngineeringBoard(board.querySelector('.production-lifecycle'),{engineering:{...report.engineering,can_edit:report.engineering.can_edit&&!session.read_only}},{embedded:true});
 }else{
  board.innerHTML=head(workshop.name+'看板','进度读取工程登记；未登记不计为未开始，100%进度不代替质检确认。')+
   `<dl class="center-metrics production-status">${[['已登记车间进度',workshop.registered],['进行中',workshop.active],['未开始',workshop.not_started],['进度100%',workshop.complete],['车间卡点',workshop.blocked],['进度待登记',workshop.unknown]].map(([label,n])=>'<div><dt>'+label+'</dt><dd>'+n+'<small>单</small></dd></div>').join('')}</dl>`+
   panel(workshop.name+'关联订单 · '+rows.length+' 单',`<div class="department-table-wrap"><table><thead><tr>${['订单 / 项目','交货期','工程负责人','车间登记进度','登记状态','卡点 / 问题'].map(h=>'<th>'+h+'</th>').join('')}</tr></thead><tbody>${rows.map(r=>`<tr><td><strong>${esc(r.name)}</strong><small>${esc(r.number)}${r.shared_test?' · 测试数据':''}</small></td><td>${esc(r.delivery_date||'待登记')}<small>${esc(dateText(r))}</small></td><td>${esc(r.engineering_owner)}</td><td>${pct(r.workshop_progress,workshop.name)}</td><td>${esc(r.workshop_state)}</td><td class="production-issue">${r.workshop_blocked?esc(r.blocker_reason):'未登记本车间卡点'}<small>${esc(r.issue||'暂无反馈')}</small></td></tr>`).join('')||'<tr><td colspan="6">暂无关联生产订单</td></tr>'}</tbody></table></div>`)+notice;
 }
}

function renderAftersalesWorkflow(el){
 el.classList.add('aftersales-original-workspace');el.innerHTML='<iframe title="售后工作台" src="/aftercare/workspace?record='+encodeURIComponent(routeRecord||'')+'&project='+encodeURIComponent(project||'')+(aftercareSharedTaskId===routeRecord&&routeRecord?'&mode=task':'')+'" class="aftercare-workflow-frame"></iframe>';
}

window.addEventListener('message',event=>{if(event.origin!==location.origin||event.data?.type!=='yifun-aftercare-height'||!Number.isFinite(event.data.height))return;const frame=document.querySelector('.aftercare-workflow-frame');if(frame&&event.source===frame.contentWindow)frame.style.height=Math.max(600,Math.min(20000,event.data.height))+'px';});

function renderSharedAftersalesTasks(el,rows){
 if(!rows.length)return;
 el.insertAdjacentHTML('beforeend',panel('售后协同任务 · '+rows.length+' 条',`<p>与售后工作台共用同一工单，处理结果、负责人和进度同步显示。</p><div class="department-table-wrap"><table><thead><tr><th>项目／工单</th><th>设备／问题</th><th>当前环节</th><th>负责人</th><th>计划完成</th><th>操作</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.project)}<small>${esc(r.work_no)}</small></td><td>${esc(r.product)}<small>${esc(r.issue)}</small></td><td>${esc(r.stage)}</td><td>${esc(r.owner)}</td><td>${esc(r.due||'待排期')}</td><td><button type="button" data-af-shared="${esc(r.id)}" data-af-project="${esc(r.project_id)}">${r.can_handle?'查看／处理售后任务':'查看售后进度'}</button></td></tr>`).join('')}</tbody></table></div>`));
}

document.addEventListener('click',async e=>{const b=e.target.closest('[data-af-shared]');if(!b)return;aftercareSharedTaskId=b.dataset.afShared;routeRecord=aftercareSharedTaskId;view='center-aftersales-workflow';await chooseProject(b.dataset.afProject);});
