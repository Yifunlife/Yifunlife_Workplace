'use strict';
let connectionData=null;
const onlineOrigin='https://yifunlife-erp.yifunlife.workers.dev';
const externalLink=(url,label)=>`<a class="quiet" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;
async function renderConnections(el,generation){
 pageLoading(el,'连接资料');
 try{
  const data=await api('/api/connections'+(project?'?project='+encodeURIComponent(project):''));if(generation!==renderGeneration)return;connectionData=data;
  const runs=data.runs.map(r=>`<tr><td>${r.source==='sales'?'亦玩销售工作台':'线上报价网站'}</td><td>${r.error?esc(r.error):r.last_success?'已同步':'等待首次同步'}</td><td>${esc(stamp(r.last_success))}</td><td>${r.count} ${r.source==='sales'?'位客户':'份报价'}</td></tr>`);
  el.innerHTML=head('连接资料',data.enabled?'客户由销售工作台维护，产品及报价由线上报价网站维护。每分钟检查一次更新。':'尚未配置连接，请联系管理员。',data.can_manage?button('connection-sync','立即同步','','secondary'):'')+
   (runs.length?panel('连接状态',table(['来源','状态','最近成功时间','已接入'],runs)):'')+
   `<div class="ops-toolbar"><label>搜索客户或项目<input type="search" id="connection-search" placeholder="姓名、原编号、项目或国家"></label><span id="connection-count">${data.sales.length} 位客户</span></div><div id="connection-clients">`+panel('客户与项目',data.sales.length?table(['客户／原编号','项目／国家','负责人／阶段','下一步','操作'],data.sales.map(c=>`<tr><td><strong>${esc(c.name)}</strong><small>${esc(c.id)}</small></td><td>${esc(c.project||'项目待补充')}<small>${esc(c.country)}</small></td><td>${esc(c.owner)}<small>${esc(c.projectStatus)} · 阶段 ${esc(c.stage)}</small></td><td>${esc(c.nextAction||'待补充')}<small>${esc(c.nextContact)}</small></td><td>${c.project_id?button('connection-design','设计任务',c.project_id)+button('connection-quote','进入报价',c.project_id):'在销售工作台填写项目后同步'}</td></tr>`)):empty('当前范围暂无客户','普通员工须加入对应项目后才能查看。'))+'</div>'+
   panel('线上报价记录',data.quotes.length?table(['报价编号','报价中的项目名','已关联项目','状态','操作'],data.quotes.map(q=>`<tr><td>${esc(q.contract_no)}</td><td>${esc(q.project_name)}</td><td>${esc(q.project_id?projectName(q.project_id):'待关联')}${!q.project_id&&data.can_manage?button('connection-link','关联项目',q.id):''}</td><td>${q.voided_at?'已作废':q.archived_at?'已归档':q.is_finalized?'已确认':'未确认'}</td><td>${externalLink(onlineOrigin+'/?quotationHistory='+encodeURIComponent(q.id),'查看原报价')}</td></tr>`)):empty('当前范围暂无线上报价','未关联项目的历史报价由管理员核对，不按项目名称自动合并。'))+
   panel('共用产品',`<div class="panel-body"><p>已接入 ${data.products} 项线上产品。名称、规格和单位显示在共用档案；价格、图片和历史报价继续在原网站查看。</p>${data.quote_url?externalLink(data.quote_url,'打开线上产品库'):''}</div>`);
 }catch(err){if(generation===renderGeneration)el.innerHTML=head('连接资料','')+empty('读取失败',err.message)+button('refresh','重试');}
}
async function renderOnlineQuote(el,generation){
 const title=head('报价工作台','使用原来的线上产品库、选品、报价编辑和历史记录。');
 if(!project){
  el.innerHTML=title+panel('原报价工作台',`<div class="panel-body"><div class="actions">${externalLink(onlineOrigin,'打开报价工作台')}</div><p>可直接进入原系统查看产品和报价。需要关联本次客户需求时，可从商机进入，或选择报价业务。</p><div class="actions"><button class="secondary" data-view="quote-entry">选择报价业务</button>${can('sales')?button('quote-start','开始新报价','','secondary'):''}</div></div>`);return;
 }
 el.innerHTML=title+`<p class="ops-loading" role="status">正在连接当前报价业务…</p>`;
 try{
  const data=await api('/api/connections/quote-context',{project_id:project});if(generation!==renderGeneration)return;
  el.innerHTML=title+panel(esc(projectName(project)),`<div class="panel-body"><p>客户和需求资料将带入原报价系统，保存后继续关联订单与交付。</p><div class="actions">${externalLink(data.url,'打开报价工作台')} <button class="secondary" data-view="quote-entry">切换报价业务</button></div></div>`);
 }catch(err){if(generation===renderGeneration)el.innerHTML=title+empty('当前业务暂时无法关联',err.message)+button('refresh','重新连接')+externalLink(onlineOrigin,'打开原报价工作台');}
}
async function connectionAction(name,id){
 if(name==='connection-sync'){await api('/api/connections/sync',{});notify('同步已开始，请稍后刷新查看成功时间。');return true;}
 if(name==='connection-link'){
  const q=connectionData?.quotes.find(q=>q.id===id);if(!q)throw Error('请刷新后重试');
  modal('关联历史报价',`<p class="full">${esc(q.contract_no)} · ${esc(q.project_name)}。请核对客户与项目，关联不会改写原报价。</p>`+select('project_id','对应项目',state.projects),p=>api('/api/connections/link',{...p,id,version:q.version}),'确认关联');return true;
 }
 if(name==='connection-design'||name==='connection-quote'){view=name==='connection-design'?'center-design-records':'quote';await chooseProject(id);return true;}
 return false;
}

document.addEventListener('input',e=>{if(e.target.id!=='connection-search')return;const query=e.target.value.trim().toLowerCase();let count=0;document.querySelectorAll('#connection-clients tbody tr').forEach(row=>{row.hidden=!row.textContent.toLowerCase().includes(query);if(!row.hidden)count++;});$('#connection-count').textContent=`${count} 位客户`;});
