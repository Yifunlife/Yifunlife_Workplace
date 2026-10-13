'use strict';
const OPS_LABELS={tasks:'我的待办',technical:'工程下单',warehouse:'库存作业',counts:'盘点管理',installation:'安装任务与验收',issues:'现场问题',equipment:'设备与保修档案',returns:'退换返修',leads:'线索与跟进',opportunities:'商机管理',costs:'项目成本',expenses:'费用登记',locations:'仓库与库位',migration:'数据导入与核对'};
const OPS_STATUS={planned:'待开始',in_progress:'处理中',blocked:'有阻碍',done:'已完成',awaiting_acceptance:'待验收',accepted:'已验收',open:'待处理',resolved:'待现场确认',closed:'已关闭',new:'新线索',contacting:'跟进中',qualified:'已确认意向',lost:'已终止',discovery:'需求沟通',solution:'方案确认',quotation:'报价中',negotiation:'商务洽谈',won:'已成交',draft:'草稿',released:'已下达',posted:'已入账',requested:'待销售确认',confirmed:'待退回',received:'已退回待处理'};
const OPS_STATES={tasks:['planned','in_progress','blocked','done'],installation:['planned','in_progress','awaiting_acceptance','accepted'],issues:['open','in_progress','resolved','closed'],leads:['new','contacting','qualified','lost'],opportunities:['discovery','solution','quotation','negotiation','won','lost']};
const OPS_DESCRIPTIONS={tasks:'查看负责人、期限和下一步；项目成员范围沿用统一权限。',technical:'销售确认后，由工程核对规格、图纸和执行去向，再下达工程单。',warehouse:'采购、售后和工厂库存共用账本，按实际仓库及库位区分。',counts:'记录实盘数量，核对差异后入账；盘点期间库存变化会提示重新核对。',installation:'从派工、安装到客户验收，保留负责人、时间和签收记录。',issues:'现场提交问题，分派处理，最后由现场提交人确认解决。',equipment:'从实际交付记录建立设备档案，保留安装位置和保修期限。',returns:'销售确认退换要求，仓库收回实物，售后或采购记录处理结果。',leads:'记录客户来源、联系人、跟进内容和下一步。',opportunities:'跟进客户需求，从商机直接进入报价，确认下单后继续跟进交付。',costs:'按项目和币种核对采购金额、费用及预算；资料未齐时不计算利润。',expenses:'按项目保留运输、安装、差旅、返工和售后费用凭证。',locations:'维护仓库和存放位置。待检、不良品库位不计入可用库存。',migration:'先核对编号和关联，再正式导入。保留来源和旧编号，逐行显示核对结果。'};
const OPS_WRITE={tasks:['admin','ceo','sales','purchasing','engineering','warehouse','installation','aftersales'],installation:['engineering','installation'],issues:['engineering','installation','purchasing','warehouse','aftersales','sales'],equipment:['installation','engineering','aftersales'],leads:['sales'],opportunities:['sales'],expenses:['finance','ceo'],budgets:['finance','ceo']};
let opsData=null,opsLookups=null,opsPage='',opsQuery='',opsStatus='',opsImport=null;
const opsKey=page=>page==='technical'?'engineering':page;
const opsCall=(name,p)=>api('/api/ops/action/'+name,p);
const opsDate=()=>new Date().toLocaleDateString('en-CA');
const opsTag=s=>`<span class="tag ${['done','accepted','released','posted','closed','won'].includes(s)?'done':'pending'}">${esc(OPS_STATUS[s]||s)}</span>`;
const opsEmployee=id=>opsLookups?.employees.find(e=>e.id===id)?.name||'待分配';
const opsLocation=id=>{const l=opsLookups?.locations.find(l=>l.id===id);return l?`${l.warehouse} · ${l.name}`:'—';};
const opsProduct=id=>state.products.find(p=>p.id===id)?.name||'待核对产品';
const opsMoney=(value,currency)=>value==null?'暂未接入':amount(value,currency);
const opsOption=(id,name)=>({id,name});
function workplaceCenters(){
 if(can('supplier'))return [{id:'procurement',name:'采购中心',pages:[['procurement','采购工作台']]}];
 const available=session.centers||[];
 return [...new Set(available.map(id=>id==='projects'?'crm':id).filter(id=>id!=='factory'))].map(id=>{
  if(id==='crm'){
   const groups=[...(available.includes('crm')?[{name:'客户与商机',pages:[['center-crm','销售看板'],['customers','客户档案'],...centerPages('crm').slice(1)]}]:[]),...(available.includes('projects')?[{name:'订单与交付',pages:[['center-projects','交付进度'],['orders','订单与变更'],['home','关联业务档案']]}]:[])];
   return {id,name:'销售中心',groups,pages:groups.flatMap(group=>group.pages)};
  }
  if(id==='quote')return {id,name:'核算中心',pages:centerPages('quote').map(([page,label])=>[page,page==='center-quote'?'核算看板':label])};
  return {id,name:CENTER_NAMES[id],pages:centerPages(id)};
 });
}

function sectionForView(page){
 if(['tasks','releases'].includes(page)&&!can('supplier'))return {id:'tasks',name:'我的待办',pages:[['tasks','待办事项'],...(!can('finance')?[['releases','特殊放行']]:[])]};
 return workplaceCenters().find(center=>center.pages.some(([id])=>id===page));
}
async function renderOperations(el,page,generation){
 const changed=opsPage!==page;opsPage=page;if(changed){opsQuery='';opsStatus='';}
 pageLoading(el,OPS_LABELS[page],OPS_DESCRIPTIONS[page]);
 try{
  const [lookup,result]=await Promise.all([api('/api/ops/view?page=lookups'),page==='migration'?Promise.resolve({items:[],can_write:can('admin')}):api('/api/ops/view?page='+opsKey(page)+(project&&!['leads','opportunities'].includes(page)?'&project='+encodeURIComponent(project):''))]);
  if(generation!==renderGeneration)return;opsLookups=lookup;opsData=result;
  if(page==='migration'){renderImport(el);return;}
  let actions='';
  if(result.can_write){
   const names={technical:'编制工程单',warehouse:'库位调拨',counts:'新建盘点',installation:'安排安装任务',issues:'提交现场问题',equipment:'登记设备',returns:'申请退换返修',tasks:'新建任务',leads:'新建线索',opportunities:'新建商机',expenses:'登记费用',locations:'新建库位',costs:'设置项目预算'};
   actions=button('ops-new',names[page],'','secondary');
  }
  if(page==='warehouse')actions+=button('ops-locations','仓库与库位','','secondary')+`<button class="secondary" data-view="procurement">采购收货与验收</button><button class="secondary" data-view="inventory">客户发货与领用</button>`;
  if(page==='technical')actions+=`<button class="secondary" data-view="orders">查看销售订单</button>`;
  if(page==='opportunities'&&can('sales'))actions+=button('customer','新建客户','','secondary');
  el.innerHTML=head(OPS_LABELS[page],OPS_DESCRIPTIONS[page],actions);
  if(page==='technical')el.insertAdjacentHTML('beforeend',`<div class="ops-process" aria-label="订单执行顺序"><span>销售确认</span><span aria-hidden="true">→</span><strong>工程下单</strong><span aria-hidden="true">→</span><span>采购执行／工厂后续接入</span><span aria-hidden="true">→</span><span>验收与交付</span></div>`);
  if(page==='expenses'&&!result.enabled){el.insertAdjacentHTML('beforeend',panel('费用登记 · 暂未开放',`<div class="panel-body"><p>费用功能已准备，开放后按项目登记并关联凭证。</p><form class="form-grid"><fieldset disabled class="ops-finance-preview"><legend>费用资料</legend>${select('preview-project','所属项目',state.projects)}${select('preview-category','费用类别',expenseCategories())}${input('preview-amount','金额','number','',false)}${select('preview-currency','币种',[opsOption('CNY','人民币'),opsOption('USD','美元')])}${input('preview-date','费用日期','date',opsDate(),false)}${input('preview-reference','凭证号','text','',false)}${textarea('preview-note','费用说明',false)}<button disabled type="button">暂未开放</button></fieldset></form></div>`));return;}
  if(page==='costs'){el.insertAdjacentHTML('beforeend',`<div class="notice">人民币与美元分别列示。采购金额为已记录的订单金额；完整费用尚未接入时，利润显示“暂未核算”。</div>`);}
  const statuses=OPS_STATES[page]||[...new Set(result.items.map(r=>r.status).filter(Boolean))];
  el.insertAdjacentHTML('beforeend',`<div class="ops-toolbar"><label>搜索<input id="ops-search" type="search" placeholder="搜索名称、编号或内容" value="${esc(opsQuery)}"></label>${statuses.length?`<label>状态<select id="ops-status"><option value="">全部状态</option>${statuses.map(s=>`<option value="${s}"${s===opsStatus?' selected':''}>${OPS_STATUS[s]||s}</option>`).join('')}</select></label>`:''}<span id="ops-count" class="ops-result-count"></span></div><div id="ops-records"></div>`);
  renderOpsRecords();
 }catch(error){if(generation!==renderGeneration)return;el.innerHTML=head(OPS_LABELS[page],OPS_DESCRIPTIONS[page])+empty('暂时无法读取此页面',error.message)+button('refresh','重新加载','','secondary');}
}
function opsRowActions(r){
 let actions=button('ops-detail','查看',r.id);
 const page=opsPage;
 if((OPS_WRITE[page]?.includes(session.user.role)||(page==='leads'&&opsData?.can_write))&&page!=='expenses')actions+=button('ops-edit','更新',r.id);
 if(['leads','opportunities'].includes(page)){if(can('admin','ceo','sales'))actions+=button('center-followup','记录跟进',r.id);actions+=button('center-followup-history','跟进历史',r.id);}
 if(page==='opportunities'&&can('sales'))actions+=button('opportunity-quote','进入报价',r.id);
 if(page==='technical'&&can('engineering')&&r.status==='draft')actions+=button('ops-edit','编辑',r.id)+button('ops-release','下达',r.id);
 if(page==='counts'&&can('warehouse')&&r.status==='draft')actions+=button('ops-post-count','核对并入账',r.id);
 if(page==='returns'){
  if(r.status==='requested'&&can('sales'))actions+=button('ops-return-confirm','销售确认',r.id);
  if(r.status==='confirmed'&&can('warehouse'))actions+=button('ops-return-receive','确认退回',r.id);
  if(r.status==='received'&&can('aftersales','purchasing'))actions+=button('ops-return-close','记录处置并关闭',r.id);
 }
 const attachable=OPS_WRITE[page]?.includes(session.user.role)||(page==='technical'&&can('engineering')&&r.status==='draft')||(page==='returns'&&can('sales','aftersales','warehouse','installation','purchasing'));
 if(attachable)actions+=button('ops-attach','附件',r.id);
 return `<div class="ops-row-actions">${actions}</div>`;
}
function renderOpsRecords(){
 const target=$('#ops-records');if(!target||!opsData)return;
 const data=opsData.items.filter(r=>(!opsStatus||r.status===opsStatus||r.stage===opsStatus)&&(!opsQuery||JSON.stringify(r).toLowerCase().includes(opsQuery.toLowerCase())));
 $('#ops-count').textContent=`${data.length} 条记录`;
 let headers=[],rows=[];
 const projectCell=r=>`<td>${esc(projectName(r.project_id))}</td>`;
 if(['tasks','installation','issues'].includes(opsPage)){
  headers=['事项／项目','负责人','期限','状态','操作'];
  rows=data.map(r=>`<tr><td><strong>${esc(r.title)}</strong><small>${esc(projectName(r.project_id))}${r.location?' · '+esc(r.location):''}</small>${r.blocking?'<small class="error">影响安装或交付</small>':''}</td><td>${esc(opsEmployee(r.owner_id))}</td><td>${esc(r.due_date)}${r.due_date<opsDate()&&!['done','accepted','closed'].includes(r.status)?'<small class="error">已逾期</small>':''}</td><td>${opsTag(r.status)}</td><td>${opsRowActions(r)}</td></tr>`);
 }else if(opsPage==='technical'){
  headers=['工程单／项目','销售订单','要求完成','执行去向','状态','操作'];rows=data.map(r=>`<tr><td><strong>${esc(r.number)}</strong><small>${esc(projectName(r.project_id))} · 第 ${r.revision} 版</small></td><td>${esc(baselineName(r.baseline_id))}</td><td>${esc(r.required_date)}</td><td>${r.lines.some(l=>l.route==='purchase')?'采购 ':''}${r.lines.some(l=>l.route==='factory')?'工厂（后续）':''}</td><td>${opsTag(r.status)}</td><td>${opsRowActions(r)}</td></tr>`);
 }else if(opsPage==='warehouse'){
  const balances=opsData.balances.filter(r=>!opsQuery||JSON.stringify(r).toLowerCase().includes(opsQuery.toLowerCase()));
  target.innerHTML=panel('按库位查看库存',balances.length?table(['产品','仓库／库位','数量','可用状态'],balances.map(r=>`<tr><td>${esc(r.name)}<small>${esc(r.sku)}</small></td><td>${esc(r.warehouse)}<small>${esc(r.location_name)}</small></td><td class="number">${r.quantity} ${esc(r.unit)}</td><td>${r.usable?'可用':'待检／不可用'}</td></tr>`)):empty('暂无库位库存','采购验收入库后，按实际存放位置办理调拨。'));
  headers=['单号','产品','调出','调入','数量','说明'];rows=data.map(r=>`<tr><td>${esc(r.number)}</td><td>${esc(opsProduct(r.product_id))}</td><td>${esc(opsLocation(r.source_id))}</td><td>${esc(opsLocation(r.destination_id))}</td><td class="number">${r.quantity}</td><td>${esc(r.note)}<small>${esc(r.reference)}</small></td></tr>`);
  target.insertAdjacentHTML('beforeend',panel('调拨记录',rows.length?table(headers,rows):empty('暂无调拨记录')));return;
 }else if(opsPage==='counts'){
  headers=['产品／库位','账面数量','实盘数量','差异','状态','操作'];rows=data.map(r=>`<tr><td>${esc(opsProduct(r.product_id))}<small>${esc(opsLocation(r.location_id))}</small></td><td class="number">${r.expected}</td><td class="number">${r.counted}</td><td class="number">${r.counted-r.expected}</td><td>${opsTag(r.status)}</td><td>${opsRowActions(r)}</td></tr>`);
 }else if(opsPage==='equipment'){
  headers=['设备编号／名称','项目','安装位置','保修期限','操作'];rows=data.map(r=>`<tr><td><strong>${esc(r.serial)}</strong><small>${esc(r.name)}</small></td>${projectCell(r)}<td>${esc(r.location)}</td><td>${esc(r.warranty_start)}<small>至 ${esc(r.warranty_end)}</small></td><td>${opsRowActions(r)}</td></tr>`);
 }else if(opsPage==='returns'){
  headers=['项目／交付产品','类型／数量','原因','状态','操作'];rows=data.map(r=>`<tr><td>${esc(projectName(r.project_id))}<small>${esc(opsLookups.deliveries.find(d=>d.id===r.delivery_line_id)?.name_snapshot||'—')}</small></td><td>${{return:'退货',exchange:'换货',repair:'返修'}[r.kind]} · ${r.quantity}</td><td>${esc(r.reason)}</td><td>${opsTag(r.status)}</td><td>${opsRowActions(r)}</td></tr>`);
 }else if(opsPage==='leads'){
  headers=['线索／公司','联系人','负责人','下一步','状态','操作'];rows=data.map(r=>`<tr><td><strong>${esc(r.name)}</strong><small>${esc(r.company)} · ${esc(r.source)}</small></td><td>${esc(r.contact)}<small>${esc(r.phone)}</small></td><td>${esc(opsEmployee(r.owner_id))}</td><td>${esc(r.next_action)}<small>${esc(r.next_date)}</small></td><td>${opsTag(r.status)}</td><td>${opsRowActions(r)}</td></tr>`);
 }else if(opsPage==='opportunities'){
  headers=['商机／客户','预估金额','预计成交','阶段','下一步','操作'];rows=data.map(r=>`<tr><td><strong>${esc(r.name)}</strong><small>${esc(state.customers.find(c=>c.id===r.customer_id)?.name||'—')}</small></td><td class="number">${r.expected_minor==null?'待确认':amount(r.expected_minor,r.currency)}</td><td>${esc(r.expected_date)}</td><td>${opsTag(r.stage)}</td><td>${esc(r.next_action)}</td><td>${opsRowActions(r)}</td></tr>`);
 }else if(opsPage==='costs'){
  headers=['项目','币种','预算','已记录采购','已登记费用','利润'];rows=data.map(r=>`<tr><td><strong>${esc(r.name)}</strong><small>${esc(r.code)}</small></td><td>${r.currency}</td><td class="number">${r.budget?amount(r.budget.amount_minor,r.currency):'待设置'}</td><td class="number">${amount(r.purchase_minor,r.currency)}</td><td class="number">${opsMoney(r.expenses_minor,r.currency)}</td><td>暂未核算</td></tr>`);
 }else if(opsPage==='expenses'){
  headers=['项目','类别','金额','日期／凭证','说明','操作'];rows=data.map(r=>`<tr>${projectCell(r)}<td>${esc(expenseCategories().find(c=>c.id===r.category)?.name)}</td><td class="number">${amount(r.amount_minor,r.currency)}</td><td>${esc(r.record_date)}<small>${esc(r.reference)}</small></td><td>${esc(r.note)}</td><td>${opsRowActions(r)}</td></tr>`);
 }else if(opsPage==='locations'){
  headers=['编号','仓库','库位','库存范围','状态'];rows=data.map(r=>`<tr><td>${esc(r.code)}</td><td>${esc(r.warehouse)}</td><td>${esc(r.name)}</td><td>${esc(locationCategories().find(c=>c.id===r.category)?.name)}</td><td>${r.usable?'可用':'待检／不可用'}</td></tr>`);
 }
 const hints={technical:'销售确认订单后，工程在这里编制并下达工程单。',tasks:'选择项目后建立任务，填写负责人及完成日期。',installation:'从项目安排安装任务，现场问题在独立入口跟进。',issues:'选择项目，填写现场位置、问题及负责人。',equipment:'先完成客户交付，再从实际交付产品登记设备。',returns:'选择实际交付记录建立退换返修单。',leads:'销售可建立自己负责的线索和下一步跟进。',opportunities:'先建立线索和正式客户，再建立商机。'};
 target.innerHTML=panel(OPS_LABELS[opsPage],rows.length?table(headers,rows):empty(opsQuery||opsStatus?'没有符合条件的记录':'暂无记录',opsQuery||opsStatus?'调整搜索或状态筛选后重试。':hints[opsPage]||'新建资料后会显示在这里。'));
 if(opsPage==='tasks'&&opsData.related?.length)target.insertAdjacentHTML('beforeend',panel('其他中心待处理事项',table(['事项','项目','期限','处理入口'],opsData.related.map(r=>`<tr><td>${esc(r.title)}</td><td>${esc(projectName(r.project_id))}</td><td>${esc(r.due_date||'待安排')}</td><td>${button('project-'+r.page,labels[r.page]||r.page,r.project_id)}</td></tr>`))));
}
function expenseCategories(){return [['freight','运输'],['installation','安装人工'],['travel','差旅'],['rework','返工'],['aftersales','售后补件'],['other','其他']].map(([id,name])=>({id,name}));}
function locationCategories(){return [['purchase','采购仓／共用配件'],['parts','售后常用配件'],['factory_toy','工厂玩具'],['factory_material','工厂原材料']].map(([id,name])=>({id,name}));}
function projectField(r={}){return select('project_id','所属项目',state.projects,r.project_id||project);}
function ownerField(r={}){return select('owner_id','负责人',opsLookups.employees.map(e=>opsOption(e.id,`${e.name} · ${roles[e.role]}`)),r.owner_id||session.user.id);}
function statusField(page,r={}){const key=page==='opportunities'?'stage':'status';return select(key,page==='opportunities'?'商机阶段':'状态',OPS_STATES[page].map(s=>opsOption(s,OPS_STATUS[s])),r[key]||OPS_STATES[page][0]);}
function deliveryField(r={}){return select('delivery_line_id','实际交付产品',opsLookups.deliveries.filter(d=>!project||d.project_id===project).map(d=>opsOption(d.id,`${d.number} · ${d.name_snapshot} · ${d.model_snapshot}`)),r.delivery_line_id);}
function opsForm(page,r={}){
 if(['tasks','installation','issues'].includes(page))return projectField(r)+input('title',page==='issues'?'现场问题':'任务名称','text',r.title||'')+ownerField(r)+input('due_date','要求完成日期','date',r.due_date||opsDate())+statusField(page,r)+input('location','设备／现场位置','text',r.location||'',page!=='tasks')+textarea('description',page==='issues'?'问题描述':'工作内容')+select('blocking','是否影响安装或交付',[opsOption('0','不影响'),opsOption('1','影响，需要优先处理')],String(r.blocking||0))+textarea('resolution','处理结果',false)+(page==='installation'?textarea('acceptance','客户验收签收记录',false):'');
 if(page==='equipment')return projectField(r)+deliveryField(r)+input('serial','设备编号／序列号','text',r.serial||'')+input('name','设备名称','text',r.name||'')+input('location','安装位置','text',r.location||'')+input('warranty_start','保修开始日期','date',r.warranty_start||'')+input('warranty_end','保修结束日期','date',r.warranty_end||'')+textarea('notes','设备说明',false);
 if(page==='leads')return input('name','线索名称','text',r.name||'')+input('company','公司／客户名称','text',r.company||'')+input('contact','联系人','text',r.contact||'')+input('phone','电话／其他联系途径','text',r.phone||'',false)+select('source','线索来源',centerOptions([...new Set([...CENTER_CHANNELS,'转介绍','客户主动联系',...(r.source?[r.source]:[])])]),r.source||'')+input('activity','来源活动／账户','text',r.activity||'',false)+input('region','客户地区','text',r.region||'',false)+ownerField(r)+statusField(page,r)+input('next_date','下次跟进日期','date',r.next_date||opsDate())+input('next_action','下一步行动','text',r.next_action||'')+select('customer_id','关联正式客户',state.customers,r.customer_id||'',false)+select('customer_grade','运营客户标签',[{id:'',name:'未标记'},{id:'A',name:'A 类'},{id:'B',name:'B 类'},{id:'C',name:'C 类'}],r.customer_grade||'',false)+textarea('validity_reason','有效性判断／终止原因',false)+textarea('notes','需求与补充资料',false);
 if(page==='opportunities')return select('lead_id','来源线索',opsLookups.leads,r.lead_id)+select('customer_id','正式客户',state.customers,r.customer_id)+input('name','商机名称','text',r.name||'')+ownerField(r)+statusField(page,r)+input('expected_minor','预估金额','number',r.expected_minor==null?'':r.expected_minor/100,false,'min="0" step="0.01"')+select('currency','币种',[opsOption('CNY','人民币'),opsOption('USD','美元')],r.currency||'CNY')+input('expected_date','预计成交日期','date',r.expected_date||'')+input('next_action','下一步行动','text',r.next_action||'')+textarea('notes','商机记录',false);
 if(page==='expenses'||page==='budgets')return projectField(r)+(page==='expenses'?select('category','费用类别',expenseCategories(),r.category):'')+input('amount_minor',page==='budgets'?'预算金额':'费用金额','number',r.amount_minor==null?'':r.amount_minor/100,true,'min="0.01" step="0.01"')+select('currency','币种',[opsOption('CNY','人民币'),opsOption('USD','美元')],r.currency||'CNY')+(page==='expenses'?input('record_date','费用日期','date',r.record_date||opsDate())+input('reference','凭证号','text',r.reference||''):'')+textarea('note',page==='budgets'?'预算依据':'费用说明');
 return '';
}
function fillTextareas(r){for(const e of $('#dialog-fields').querySelectorAll('textarea'))e.value=r[e.name]||'';}
async function operationsAction(name,id){
 if(!name.startsWith('ops-'))return false;
 const page=opsPage,r=opsData?.items.find(r=>r.id===id);
 if(name==='ops-locations'){view='locations';await render();return true;}
 if(name==='ops-new'||name==='ops-edit'){
  if(page==='technical'){engineeringForm(r);return true;}
  if(page==='warehouse'){modal('库位调拨',select('product_id','共用产品',products())+select('source_id','调出库位',opsLookups.locations.map(l=>opsOption(l.id,opsLocation(l.id))))+select('destination_id','调入库位',opsLookups.locations.map(l=>opsOption(l.id,opsLocation(l.id))))+input('quantity','数量','number','',true,'min="0.001" step="any"')+input('reference','关联单据／凭证','text','',false)+textarea('note','调拨说明'),p=>opsCall('warehouse-transfer',p),'确认调拨');return true;}
  if(page==='counts'){modal('新建盘点',select('product_id','共用产品',products())+select('location_id','盘点库位',opsLookups.locations.map(l=>opsOption(l.id,opsLocation(l.id))))+input('counted','实盘数量','number','',true,'min="0" step="any"')+textarea('reason','盘点说明'),p=>opsCall('count-create',p),'保存待核对盘点');return true;}
  if(page==='locations'){modal('建立仓库库位',input('code','库位编号')+input('warehouse','仓库名称')+input('name','库位名称')+select('category','库存范围',locationCategories(),'purchase')+select('usable','库存状态',[opsOption('1','可用'),opsOption('0','待检／不良品，暂不可用')],'1'),p=>opsCall('location-create',p));return true;}
  if(page==='returns'){modal('申请退换返修',projectField()+deliveryField()+select('kind','处理类型',[opsOption('return','退货'),opsOption('exchange','换货'),opsOption('repair','返修')])+input('quantity','本次数量','number','',true,'min="0.001" step="any"')+select('replacement_product_id','拟更换产品（换货时填写）',products(),'',false)+textarea('reason','原因与客户要求'),p=>opsCall('return-create',p),'提交销售确认');return true;}
  let kind=page==='costs'?'budgets':page;
  let record=r||{};
  if(page==='costs'&&project)record=opsData.items.find(i=>i.id===project&&i.currency==='CNY')?.budget||{};
  modal((r?'更新':'新建')+(page==='costs'?'项目预算':OPS_LABELS[page]),opsForm(kind,record),p=>opsCall('save',{...p,page:kind,...(record.id?{id:record.id,version:record.version}:{})}),'保存',()=>fillTextareas(record));return true;
 }
 if(name==='ops-release'){modal('下达工程单',`<p class="full">${esc(r.number)} · 第 ${r.revision} 版。下达后保留本版内容，采购据此执行。订金确认或 CEO 特批条件继续适用。</p>`,()=>opsCall('engineering-release',{id,version:r.version}),'确认下达');return true;}
 if(name==='ops-post-count'){modal('核对盘点差异',`<p class="full">${esc(opsProduct(r.product_id))} · ${esc(opsLocation(r.location_id))}</p><p class="full">账面 ${r.expected}，实盘 ${r.counted}，差异 ${r.counted-r.expected}。确认后追加库存流水。</p>`,()=>opsCall('count-post',{id,version:r.version}),'确认差异并入账');return true;}
 if(name.startsWith('ops-return-')){
  const action=name.slice(4),fields=action==='return-confirm'?textarea('responsibility','客户确认、费用责任及差额处理说明'):action==='return-receive'?select('location_id','退回待检库位',opsLookups.locations.filter(l=>!l.usable).map(l=>opsOption(l.id,opsLocation(l.id)))):textarea('resolution','实物处置、补发凭证与处理结果');
  modal(action==='return-confirm'?'销售确认退换':action==='return-receive'?'确认收到退回产品':'记录处置并关闭',fields,p=>opsCall(action,{...p,id,version:r.version}),'确认');return true;
 }
 if(name==='ops-attach'){
  modal('追加照片或文件',`<label class="full">附件<input id="ops-upload" type="file" accept="image/png,image/jpeg,image/webp,.pdf,.docx,.xlsx" required></label><p class="form-help full">每个附件不超过 5 MB，上传后保留原文件。</p>`,async()=>{const file=$('#ops-upload').files[0];if(!file)throw Error('请选择附件');if(file.size>5*1024*1024)throw Error('附件超过 5 MB');const content=await fileBase64(file);await opsCall('attach',{page:opsKey(page),id,file_name:file.name,mime:file.type||'application/octet-stream',content});},'上传附件');return true;
 }
 if(name==='ops-detail'){showOpsDetail(r);return true;}
 if(name==='ops-import-preview'){await previewImport();return true;}
 if(name==='ops-import-commit'){await commitImport();return true;}
 if(name==='ops-template'){downloadTemplate();return true;}
 return true;
}
function engineeringForm(r){
 const defaults=r?state.baselines.find(b=>b.id===r.baseline_id):state.baselines[0];
 const fields=select('baseline_id','已确认销售订单',state.baselines.map(b=>opsOption(b.id,`${b.number} · ${projectName(b.project_id)}`)),defaults?.id)+input('required_date','要求完成日期','date',r?.required_date||'')+`<div id="ops-engineering-lines" class="full"></div>`+textarea('notes','工程说明',false);
 modal(r?'编辑工程单':'编制工程单',fields,p=>{const b=state.baselines.find(b=>b.id===p.baseline_id);if(!b)throw Error('请选择已确认的销售订单');return opsCall('engineering-save',{baseline_id:b.id,required_date:p.required_date,notes:p.notes,...(r?{id:r.id,version:r.version}:{}),lines:b.lines.map(l=>({id:l.id,specification:p['spec_'+l.id],drawing:p['drawing_'+l.id],route:p['route_'+l.id]}))});},'保存工程草稿',()=>{
  const selector=$('#dialog-fields [name="baseline_id"]');if(r)selector.disabled=true;
  if(r)selector.insertAdjacentHTML('afterend',`<input type="hidden" name="baseline_id" value="${esc(r.baseline_id)}">`);
  const draw=()=>{const b=state.baselines.find(b=>b.id===selector.value);$('#ops-engineering-lines').innerHTML=b?b.lines.map(l=>{const old=r?.lines.find(x=>x.id===l.id);return `<fieldset class="ops-engineering-line"><legend>${esc(l.sku)} · ${esc(l.name)} × ${l.effective_quantity}</legend>${input('spec_'+l.id,'执行规格','text',old?.specification||l.specification||'')}${input('drawing_'+l.id,'图纸编号／版本','text',old?.drawing||'',false)}${select('route_'+l.id,'执行去向',[opsOption('purchase','采购'),opsOption('factory','工厂（生产后续接入）')],old?.route||'purchase')}</fieldset>`;}).join(''):empty('暂无已确认销售订单','请由销售先确认下单。');};selector.onchange=draw;draw();fillTextareas(r||{});
 });
}
function showOpsDetail(r){
 const fields={title:'事项',name:'名称',number:'单号',serial:'设备编号',company:'公司',contact:'联系人',phone:'电话',source:'来源',description:'内容',location:'现场位置',resolution:'处理结果',acceptance:'验收签收',notes:'记录',note:'说明',responsibility:'责任与差额处理',reason:'原因',next_action:'下一步',next_date:'下次跟进',required_date:'要求完成',due_date:'完成期限',warranty_start:'保修开始',warranty_end:'保修结束',reference:'凭证',record_date:'日期'};
 let content=`<dl class="ops-details full">${r.project_id?`<div><dt>项目</dt><dd>${esc(projectName(r.project_id))}</dd></div>`:''}${r.owner_id?`<div><dt>负责人</dt><dd>${esc(opsEmployee(r.owner_id))}</dd></div>`:''}${Object.entries(fields).filter(([key])=>r[key]).map(([key,label])=>`<div><dt>${label}</dt><dd>${esc(r[key])}</dd></div>`).join('')}</dl>`;
 if(r.lines)content+=`<div class="full">${table(['产品','数量','执行规格','图纸版本','去向'],r.lines.map(l=>`<tr><td>${esc(l.name)}</td><td>${l.quantity}</td><td>${esc(l.specification)}</td><td>${esc(l.drawing||'—')}</td><td>${l.route==='purchase'?'采购':'工厂（后续）'}</td></tr>`))}</div>`;
 if(r.purchases)content+=`<div class="full"><strong>采购执行追踪</strong>${r.purchases.length?table(['采购单','采购数量','已收货','已入库'],r.purchases.map(p=>`<tr><td>${esc(p.po_number)}</td><td>${p.quantity}</td><td>${p.received}</td><td>${p.stocked}</td></tr>`)):'<p>尚未建立关联采购单</p>'}</div>`;
 content+=`<div class="full"><strong>附件记录</strong>${r.files?.length?`<ul class="ops-file-list">${r.files.map(f=>`<li><a href="/api/ops/file/${encodeURIComponent(f.id)}" download>${esc(f.file_name)}</a><small>${stamp(f.created_at)}</small></li>`).join('')}</ul>`:'<p>暂无附件</p>'}</div>`;
 modal(OPS_LABELS[opsPage]+'详情',content,async()=>{},'关闭');
}
function fileBase64(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('文件读取失败'));reader.readAsDataURL(file);});}
document.addEventListener('input',e=>{if(e.target.id==='ops-search'){opsQuery=e.target.value;renderOpsRecords();}});
document.addEventListener('change',e=>{if(e.target.id==='ops-status'){opsStatus=e.target.value;renderOpsRecords();}});

function renderImport(el){
 el.innerHTML=head('数据导入与核对',OPS_DESCRIPTIONS.migration,button('ops-template','下载 CSV 模板','','secondary'))+panel('选择导入资料',`<div class="panel-body"><div class="ops-process"><strong>选择资料</strong><span>→</span><span>逐行核对</span><span>→</span><span>确认导入</span></div><div class="form-grid"><label>档案类型<select id="import-kind"><option value="customers">客户</option><option value="projects">项目</option><option value="products">产品</option></select></label><label>来源系统／批次<input id="import-source" placeholder="例如：原系统导出 2026-09"></label><label class="full">CSV 文件<input type="file" id="import-file" accept=".csv,text/csv"></label></div><div class="actions">${button('ops-import-preview','读取并核对','','secondary')}</div></div>`)+`<div id="import-preview" aria-live="polite"></div>`+`<div class="notice">客户先于项目导入；项目通过客户编号关联。已有编号不会被覆盖，库存余额不通过档案导入增加。</div>`;
}
function parseCSV(text){
 const rows=[];let row=[],value='',quoted=false;text=text.replace(/^\uFEFF/,'');
 for(let i=0;i<text.length;i++){const ch=text[i];if(ch==='"'){if(quoted&&text[i+1]==='"'){value+='"';i++;}else quoted=!quoted;}else if(ch===','&&!quoted){row.push(value);value='';}else if((ch==='\n'||ch==='\r')&&!quoted){if(ch==='\r'&&text[i+1]==='\n')i++;row.push(value);if(row.some(v=>v.trim()))rows.push(row);row=[];value='';}else value+=ch;}
 if(quoted)throw Error('CSV 引号未闭合，请核对文件');row.push(value);if(row.some(v=>v.trim()))rows.push(row);
 const headers=rows.shift()?.map(h=>h.trim());if(!headers?.length)throw Error('文件为空');return rows.map(r=>Object.fromEntries(headers.map((h,i)=>[h,r[i]||''])));
}
async function previewImport(){
 const file=$('#import-file').files[0];if(!file)throw Error('请选择 CSV 文件');if(file.size>5*1024*1024)throw Error('文件超过 5 MB');
 const p={kind:$('#import-kind').value,source:$('#import-source').value,rows:parseCSV(await file.text())};
 opsImport=await opsCall('import-preview',p);opsImport.request=p;
 const rows=opsImport.items.map(r=>`<tr><td>${r.row}</td><td>${esc(r.code)}</td><td>${esc(r.name)}</td><td>${esc(r.status)}</td><td>${esc(r.message)}</td></tr>`);
 $('#import-preview').innerHTML=panel('核对结果',table(['行号','编号','名称','状态','说明'],rows),opsImport.ready?button('ops-import-commit','确认导入','','secondary'):'')+(!opsImport.ready?'<p class="error">请先修正标记的问题，再重新读取文件。</p>':'');
}
async function commitImport(){if(!opsImport?.ready)throw Error('请先完成核对');const r=await opsCall('import-commit',{...opsImport.request,digest:opsImport.digest});await refresh();notify(`已导入 ${r.imported} 条，保留原有 ${r.skipped} 条`);opsImport=null;}
function downloadTemplate(){
 const type=$('#import-kind').value;const text={customers:'code,name,contact,phone,email,notes\n',projects:'code,name,customer_code,owner_email,location,notes\n',products:'sku,name,unit,specification\n'}[type];
 const url=URL.createObjectURL(new Blob(['\uFEFF'+text],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=`${{customers:'客户',projects:'项目',products:'产品'}[type]}导入模板.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}

async function outboundLocation(){const lookup=await api('/api/ops/view?page=lookups');return select('location_id','出库库位',lookup.locations.filter(l=>l.usable).map(l=>({id:l.id,name:l.warehouse+' · '+l.name})),'unassigned');}
