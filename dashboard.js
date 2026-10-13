'use strict';
const dashboardStamp=s=>new Date(s).toLocaleString('zh-CN',{hour12:false,timeZone:'Asia/Shanghai'});
let dashboardData=null,dashboardPeriod={},dashboardList='',dashboardTab='overview',dashboardProject='',dashboardCurrency='CNY';
const CEO_STAGES=[['设计中',['设计中'],'commercial'],['报价中',['报价中'],'commercial'],['已报价待签单',['已报价待签单'],'commercial'],['工程下单',['工程下单'],'execution'],['生产中',['生产中'],'unconnected'],['生产完成待发货',['生产完成待发货'],'unconnected'],['已发货待安装',['已发货待安装'],'execution'],['安装中',['安装中'],'execution']];
const ceoMoney=(minor,currency='CNY')=>minor==null?'暂未接入':`${currency} ${(minor/100).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})}`;
const ceoAmounts=(rows,blank='尚无记录')=>rows?.length?rows.map(r=>`<span class="money-line">${esc(ceoMoney(r.minor,r.currency))}</span>`).join(''):`<span class="muted">${blank}</span>`;
const ceoLink=(target,label,id='',projectId='')=>`<a class="dashboard-link" href="/?${esc(new URLSearchParams({view:target,project:projectId,...(id?{record:id}:{})}).toString())}">${esc(label)}</a>`;
const projectLink=p=>ceoLink('home',p.name,p.id,p.id);
const drillButton=(id,label)=>`<button class="quiet" data-action="dashboard-list" data-id="${esc(id)}" aria-expanded="${dashboardList===id}">${esc(label)}</button>`;
function dashboardUrl(){
  if(view!=='dashboard')return;
  const p=new URLSearchParams({view:'dashboard',tab:dashboardTab,...dashboardPeriod});
  if(dashboardProject)p.set('scope',dashboardProject);
  if(dashboardList)p.set('detail',dashboardList);
  if(dashboardCurrency)p.set('currency',dashboardCurrency);
  history.replaceState(null,'','/?'+p.toString());
}
async function companyDashboard(el,generation){
  pageLoading(el,'CEO 总看板','项目全生命周期经营总况');
  const params=new URLSearchParams(dashboardPeriod);if(dashboardProject)params.set('project',dashboardProject);
  const result=await api('/api/dashboard?'+params);
  if(generation!==renderGeneration)return;
  dashboardData=result;dashboardPeriod={from:result.period.from,to:result.period.to};
  if(result.finance.summary.length&&!result.finance.summary.some(s=>s.currency===dashboardCurrency))dashboardCurrency=result.finance.summary[0].currency;
  dashboardUrl();drawDashboard(el);
}
function drawDashboard(el=$('#content')){
  el.innerHTML=dashboardPage();if(dashboardData.account_reporting){const r=dashboardData.account_reporting;el.insertAdjacentHTML('beforeend',panel('运营账号联调 · 独立测试数据',table(['市场','账号数','区间运营花销','区间归属成交','年度广告支出','月度广告支出'],r.markets.map(m=>`<tr><td>${esc(m.market)}</td><td>${m.account_count}</td><td>${ceoMoney(m.cost,r.currency)}</td><td>${ceoMoney(m.sales,r.currency)}</td><td>${ceoMoney(m.annual_ads,r.currency)}</td><td>${ceoMoney(m.monthly_ads,r.currency)}</td></tr>`))));}
  for(const e of el.querySelectorAll('[data-ceo-background]'))e.style.background=e.dataset.ceoBackground;
  for(const e of el.querySelectorAll('[data-ceo-width]'))e.style.width=e.dataset.ceoWidth;
}
function dashboardExportLink(){
  const params=new URLSearchParams({...dashboardPeriod,tab:dashboardTab});if(dashboardProject)params.set('project',dashboardProject);
  return `<a class="ceo-export" href="/api/dashboard/export?${esc(params.toString())}" download>导出当前明细</a>`;
}
function dashboardPage(){
  const d=dashboardData;
  return head('CEO 总看板',dashboardTab==='overview'?'项目全生命周期经营总况':'财务模块 · 资金分析',`${dashboardExportLink()}${button('dashboard-fullscreen',document.fullscreenElement?'退出全屏':'全屏查看','','secondary')}`)+
  `<div class="ceo-toolbar"><nav class="ceo-tabs" aria-label="CEO 看板页面">${[['overview','经营总况'],['finance','财务资金分析']].map(([id,label])=>`<a href="/?${esc(new URLSearchParams({view:'dashboard',tab:id,...dashboardPeriod,...(dashboardProject?{scope:dashboardProject}:{})}).toString())}" data-action="dashboard-tab" data-id="${id}" ${id===dashboardTab?'aria-current="page"':''}>${label}</a>`).join('')}</nav><label>查看范围<select id="dashboard-project-filter"><option value="">全部项目</option>${d.project_options.map(p=>`<option value="${esc(p.id)}" ${p.id===dashboardProject?'selected':''}>${esc(p.code)} · ${esc(p.name)}</option>`).join('')}</select></label></div>`+
  `<div class="dashboard-period"><form id="dashboard-period-form">${input('from','统计开始日期','date',d.period.from)}${input('to','截止日期','date',d.period.to)}<button class="secondary">应用日期</button>${button('dashboard-this-month','本月').replace('<button ','<button type="button" ')}</form><p>悉尼时间 · ${esc(dashboardStamp(d.updated_at))} 更新<br>${dashboardTab==='overview'?'阶段与预警为当前状态；本期金额按下单日期统计。':'账款按截止日期回看；采购结算与成本预算采用当前确认值。'}</p></div>`+
  `<div class="ceo-board">${dashboardTab==='overview'?overviewBoard():financeBoard()}</div>${dashboardDrill()}`;
}
function overviewBoard(){
  const d=dashboardData,h=d.health,healthy=h.total?Math.round((h.total-h.risk)/h.total*100):null;
  const stageCards=CEO_STAGES.map(([label,stages,tone],i)=>{
    const ps=d.projects.filter(p=>stages.includes(p.lifecycle_stage)),totals={};
    for(const p of ps)for(const a of (tone==='commercial'?p.quote_amounts:p.contract_amounts)||[])totals[a.currency]=(totals[a.currency]||0)+a.minor;
    const pending=tone==='unconnected';
    const notes=['含方案准备项目','正在编制或调整报价','客户已确认，等待下单','工程核对与放行','采购或库存配货','采购执行及收货验收','工厂生产数据待接入','待发货及客户交付','现场安装与客户验收','交付完成及售后跟进'];
    return `<button class="ceo-stage ${tone} stage-color-${i}" ${pending?'disabled':''} data-action="dashboard-list" data-id="stage-${i}" aria-expanded="${dashboardList==='stage-'+i}"><span class="stage-heading"><span class="stage-step">${String(i+1).padStart(2,'0')}</span><span>${label}</span></span><strong>${pending?'—':ps.length}<small>${pending?'':' 个项目'}</small></strong><span class="stage-description">${notes[i]}</span><div class="stage-amount"><small>${tone==='commercial'?'报价金额':'合同金额'}</small>${pending?'<span class="stage-empty">待接入</span>':ceoAmounts(Object.entries(totals).map(([currency,minor])=>({currency,minor})),ps.length?(tone==='commercial'?'暂无报价金额':'暂无合同金额'):'—')}</div><span class="stage-detail">${pending?'尚未统计':ps.length?'查看项目明细 ↗':'暂无项目'}</span></button>`;
  }).join('');
  const groupSummary=(signed)=>{const ps=d.projects.filter(p=>p.signed===signed&&p.stage!=='需求已取消'&&p.lifecycle_stage!=='已完成'),totals={};for(const p of ps)for(const a of (signed?p.contract_amounts:p.quote_amounts)||[])totals[a.currency]=(totals[a.currency]||0)+a.minor;return `<strong>${ps.length} 个项目</strong><span>${signed?'合同':'报价'}金额 ${ceoAmounts(Object.entries(totals).map(([currency,minor])=>({currency,minor})),'暂无记录')}</span>`;};
  const unclassified=d.projects.filter(p=>p.signed&&!p.lifecycle_stage&&p.stage!=='需求已取消').length;
  return `<section class="ceo-lifecycle"><div class="ceo-section-title"><h2>项目全生命周期</h2><span>签单前 → 签单后</span></div><div class="lifecycle-groups"><div class="lifecycle-group commercial"><b>方案与签单</b>${groupSummary(false)}</div><div class="lifecycle-group execution"><b>订单执行与交付</b>${groupSummary(true)}</div></div><div class="ceo-stage-grid">${stageCards}</div><p class="ceo-note">按项目当前阶段去重统计；签单前显示最新有效报价金额，签单后显示合同金额，各币种分别汇总。生产及生产完成状态待接入${unclassified?'；'+unclassified+' 个已签单项目待确认执行阶段':''}。已报价待签单暂按已定稿报价识别。</p></section>`+
  `<div class="ceo-overview-grid"><section class="ceo-card ceo-health ceo-summary-card"><div class="ceo-card-head"><h2>经营健康度</h2><span class="count-badge">${h.risk} 个待关注</span></div>${compactPreview(d.projects.filter(p=>p.exception_count>0).slice(0,5).map(p=>[projectLink(p),`${p.lifecycle_stage||p.stage} · ${p.owner||'待分配'} · ${p.exception_count} 项提醒`]))}<div class="preview-footer">${drillButton('risks','查看全部异常')}</div></section>`+
  `<section class="ceo-card ceo-top-risks ceo-summary-card"><div class="ceo-card-head"><h2>交付风险预警</h2><span class="count-badge">${d.exceptions.length} 条</span></div>${compactPreview(d.exceptions.slice(0,5).map(e=>[ceoLink(e.target==='members'?'home':e.target==='baseline'?'orders':e.target.replace('operations-',''),e.project_name,e.target_id,e.project_id),`${e.title} · ${e.overdue_days>0?'逾期 '+e.overdue_days+' 天':'待处理'}`]))}<div class="preview-footer">${drillButton('risks','查看全部 '+d.exceptions.length+' 条')}</div></section>`+
  `<section class="ceo-card ceo-customers ceo-summary-card"><div class="ceo-card-head"><h2>客户合作价值</h2><span class="count-badge">${d.customers.filter(c=>c.cooperation_count>0).length} 个成交客户</span></div>${compactPreview(d.customers.filter(c=>c.cooperation_count>0).sort((a,b)=>b.cooperation_count-a.cooperation_count).slice(0,5).map(c=>[ceoLink('customers',c.name),`${c.cooperation_count} 次合作 · ${c.amounts.map(a=>ceoMoney(a.minor,a.currency)).join(' / ')||'暂无金额'}`]),'暂无成交客户')}<div class="preview-footer">${drillButton('customers','查看全部客户')}</div></section>`+
  `<section class="ceo-card ceo-service ceo-summary-card"><div class="ceo-card-head"><h2>客户服务项目</h2><span class="count-badge">${d.tickets.length} 条未关闭</span></div>${compactPreview(d.tickets.slice(0,5).map(t=>[ceoLink('aftersales',t.project_name||t.id,t.id,t.project_id),`${t.stage} · ${t.owner||'待分配'} · ${t.due_date||'待补计划'}`]),'暂无待处理服务项目')}<div class="preview-footer">${drillButton('tickets','查看全部服务项目')}</div></section>`+
  `<section class="ceo-card ceo-finance-glance"><div class="ceo-card-head"><h2>经营财务概览</h2>${button('dashboard-tab','资金分析','finance')}</div>${financeGlance()}<p class="ceo-note">${d.finance.enabled?'各币种分开核对。':'财务暂未开放，收付款数据不显示为零。'}</p></section>`+
  `<section class="ceo-card ceo-tracking"><div class="ceo-card-head"><h2>进行中项目列表</h2>${drillButton('projects',`全部 ${d.projects.length} 个项目`)}</div>${trackingTable(d.projects.filter(p=>!['交付完成','需求已取消','售后跟进中'].includes(p.stage)).slice(0,5))}</section>`+
  `<section class="ceo-card ceo-distribution"><div class="ceo-card-head"><h2>交付进度分布</h2></div>${progressDistribution()}</section></div>`+
  `<section class="ceo-card ceo-decisions"><div class="ceo-card-head"><h2>${can('ceo')?'待我决策':'待 CEO 决策'}</h2><span class="count-badge">${d.decisions.length} 项特殊放行</span></div>${decisionFeed()}</section>`;
}
function compactPreview(items,blank='暂无记录'){return items.length?`<ul class="ceo-preview">${items.map(([title,detail])=>`<li><div>${title}</div><small title="${esc(detail)}">${esc(detail)}</small></li>`).join('')}</ul>`:`<div class="preview-empty">${esc(blank)}</div>`;}
function trackingTable(ps){
  if(!ps.length)return empty('当前范围暂无项目','建立客户与项目后，业务进度将在这里汇总。');
  return table(['项目／客户','合作次数','累计／本期成交','当前阶段','最近期限','交付进度','异常／负责人','操作'],ps.map(p=>`<tr><td>${projectLink(p)}<small>${esc(p.code)} · ${esc(p.customer_name)}</small></td><td>${dashboardData.customers.find(c=>c.id===p.customer_id)?.cooperation_count||0} 次</td><td>${ceoAmounts(p.contract_amounts,'未成交')}<small>本期 ${ceoAmounts(p.period_amounts,'无新下单')}</small></td><td>${tag(p.stage)}<small>${esc(p.next_step)}</small></td><td>${esc(p.due_date||'待安排')}<small>${esc(p.due_source)}${p.days_remaining==null?'':p.days_remaining<0?' · 逾期 '+(-p.days_remaining)+' 天':' · 剩余 '+p.days_remaining+' 天'}</small></td><td>${progressBar(p.progress)}<small>${p.total_lines?`${p.completed_lines} / ${p.total_lines} 个产品行已交齐`:'暂无有效产品行'}</small></td><td>${p.exception_count?`<span class="tag pending">${p.exception_count} 项异常</span>`:'无已记录异常'}<small>${esc(p.owner||'待分配')}</small></td><td>${ceoLink('home','项目详情','',p.id)}${can('admin')?button('members','项目成员',p.id):''}</td></tr>`));
}
function progressBar(value){return value==null?'<span class="muted">—</span>':`<div class="ceo-progress"><span role="progressbar" aria-label="交付进度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${value}"><i data-ceo-width="${Math.max(0,Math.min(100,value))}%"></i></span><strong>${value}%</strong></div>`;}
function riskTable(rows){return rows.length?table(['项目／问题','负责人','期限','查看'],rows.map(e=>`<tr><td><strong>${esc(e.project_name)}</strong><small>${esc(e.title)}</small><details class="risk-description"><summary>问题说明</summary><p>${esc(e.detail)}</p></details></td><td>${esc(e.owner)}</td><td>${e.overdue_days?`<span class="tag pending">逾期 ${e.overdue_days} 天</span>`:'待处理'}</td><td>${ceoLink(e.target==='baseline'?'orders':e.target==='members'?'home':e.target.replace('operations-',''),'详情',e.target_id,e.project_id||'')}</td></tr>`)):empty('暂无已记录的异常','根据采购、验收、售后和现场事项判断。');}
function decisionFeed(){return dashboardData.decisions.length?`<ul class="dashboard-feed decisions">${dashboardData.decisions.map(r=>`<li><div class="feed-caption"><strong>${esc(r.number)} · ${esc(r.project_name)}</strong><small>等待 ${r.waiting_days} 天</small></div><p>${esc(ceoMoney(r.agreed_minor,r.currency))} · 申请人 ${esc(r.requested_by_name)}</p><p class="decision-reason">${esc(r.reason)}</p><div class="feed-bottom"><small>特殊放行仅由 CEO 审批</small><div>${ceoLink('orders','订单记录',r.baseline_id,r.project_id)}${can('ceo')?button('decide-release','审批',r.id,'secondary'):''}</div></div></li>`).join('')}</ul>`:empty('暂无待审批申请','管理员可监管全过程，特殊放行仅由 CEO 决定。');}
function progressDistribution(){
  const ps=dashboardData.projects.filter(p=>p.progress!=null),groups=[[0,25],[25,50],[50,75],[75,100]],colors=['#315789','#5098ad','#ba8c32','#4e8663'];let stop=0;
  const counts=groups.map(([low,high],i)=>ps.filter(p=>(i===0?p.progress>=low:p.progress>low)&&p.progress<=high).length);
  const gradient=counts.map((n,i)=>{const from=stop;stop+=ps.length?n/ps.length*100:0;return `${colors[i]} ${from}% ${stop}%`;}).join(',');
  return `<div class="ceo-donut-layout"><div class="ceo-donut" role="img" aria-label="${ps.length} 个有交付需求的项目，按已交齐产品行比例分组" data-ceo-background="${ps.length?'conic-gradient('+gradient+')':'#e4eaf2'}"><div><strong>${ps.length}</strong><span>有交付需求</span></div></div><ul class="ceo-legend">${groups.map(([l,h],i)=>`<li><button data-action="dashboard-list" data-id="progress-${i}"><i data-ceo-background="${colors[i]}" aria-hidden="true"></i><span>${i===0?'0':'>'+l}–${h}%</span><strong>${counts[i]} 个</strong></button></li>`).join('')}</ul></div><p class="ceo-note">按已交齐产品行占比计算，不混加不同产品数量。</p>`;
}
function financeGlance(){const f=dashboardData.finance;return `<dl class="ceo-definition"><div><dt>累计合同金额</dt><dd>${ceoAmounts(f.summary.map(s=>({currency:s.currency,minor:s.contract_minor})))}</dd></div><div><dt>累计已收款</dt><dd>${f.enabled?ceoAmounts(f.summary.map(s=>({currency:s.currency,minor:s.receipt}))):'暂未接入'}</dd></div><div><dt>待收款</dt><dd>${f.enabled?ceoAmounts(f.summary.map(s=>({currency:s.currency,minor:s.receivable_minor}))):'暂未接入'}</dd></div><div><dt>库存价值</dt><dd>待核定</dd></div><div><dt>资金待核对项目</dt><dd>${f.risk_project_count==null?'暂未接入':f.risk_project_count+' 个'}</dd></div></dl>`;}
function contractMarketSummary(period){
  return ['domestic','overseas','unknown'].filter(k=>k!=='unknown'||period.markets[k].count).map(k=>`<span class="contract-market"><span>${({domestic:'国内',overseas:'国外',unknown:'待确认'})[k]} · ${period.markets[k].count} 份</span><span>${ceoAmounts(period.markets[k].amounts,'尚无记录')}</span></span>`).join('');
}
function financeBoard(){
  const f=dashboardData.finance;
  const sums=field=>ceoAmounts(f.summary.map(s=>({currency:s.currency,minor:s[field]})));
  const metric=(id,label,value,note)=>`<button class="ceo-finance-metric" data-action="dashboard-list" data-id="${id}"><span>${label}</span><strong>${value}</strong><small>${note}</small></button>`;
  return `<div class="ceo-finance-status ${f.enabled?'connected':''}"><strong>${f.enabled?'资金数据已接入':'财务分析预览 · 业务暂未开放'}</strong><span>${f.enabled?'按原单、增项、Credit、补价和实际款项核对。':'可查看页面结构及已确认合同；收付款、Credit 和费用业务保持关闭。'}</span></div>`+
  `<div class="ceo-finance-metrics">${metric('annual-contracts','年度合同金额',contractMarketSummary(dashboardData.contract_periods.annual),dashboardData.contract_periods.annual.from+' 至 '+dashboardData.contract_periods.annual.to+' · 含增项')}${metric('monthly-contracts','月度合同金额',contractMarketSummary(dashboardData.contract_periods.monthly),dashboardData.contract_periods.monthly.from+' 至 '+dashboardData.contract_periods.monthly.to+' · 含增项')}${metric('funds','累计已收款',f.enabled?sums('receipt'):'暂未接入','到账记录扣除冲销')}${metric('receivables','待收款合计',f.enabled?sums('receivable_minor'):'暂未接入','补价及 Credit 后，按订单核对')}${metric('suppliers','供应商待付款',f.enabled?ceoMoney(f.supplier_due_minor):'暂未接入',f.enabled?`${f.unknown_supplier_count} 份结算待确认，未计入合计`:'预付款计划尚未接入')}${metric('inventory','库存价值','待核定','数量共用 · 金额待成本核定')}${metric('finance-risks','资金待核对项目',f.risk_project_count==null?'暂未接入':f.risk_project_count+' 个','贷方余额、超付与待确认结算')}</div>`+
  `<div class="ceo-finance-metrics ceo-annual-expenses">${Object.entries(dashboardData.annual_expenses).map(([key,item])=>metric('annual-expense-'+key,item.label,item.connected?ceoAmounts(item.amounts):'暂未接入',dashboardData.contract_periods.annual.from+' 至 '+dashboardData.contract_periods.annual.to+(key==='advertising'?' · 仅统计有效广告费与展位费':' · 待接入费用记录'))).join('')}</div>`+
  `<div class="ceo-finance-grid"><section class="ceo-card"><div class="ceo-card-head"><h2>1. 项目资金状态</h2>${drillButton('funds','查看全部')}</div>${fundsTable(f.projects.slice(0,5))}</section><section class="ceo-card"><div class="ceo-card-head"><h2>2. 应收账款管理</h2>${drillButton('receivables','待收款明细')}</div>${receivablesTable(f.projects.slice(0,5))}</section><section class="ceo-card"><div class="ceo-card-head"><h2>3. 预付／供应商付款</h2>${drillButton('suppliers','供应商明细')}</div>${suppliersTable(f.suppliers.slice(0,5))}</section><section class="ceo-card"><div class="ceo-card-head"><h2>4. 库存资产分析</h2>${ceoLink('warehouse','库存作业')}</div>${inventoryAnalysis()}</section><section class="ceo-card"><div class="ceo-card-head"><h2>5. 项目利润分析（预计）</h2>${drillButton('profit','项目明细')}</div>${profitTable(f.projects.slice(0,5))}<p class="ceo-note">预计利润 = 变更后合同金额 − 本币种成本预算。资料未齐不推算实际利润。</p></section><section class="ceo-card"><div class="ceo-card-head"><h2>6. 资金趋势（近 6 个月）</h2></div>${trendChart()}</section></div><p class="ceo-note">${esc(f.payment_plan_note)} 所有金额按币种分别展示，不自动换汇。客户贷方余额单列，不抵消其他订单待收款。</p>`;
}
function fundsTable(rows){return rows.length?table(['项目／币种','合同金额','已收款','待收款','回款比例'],rows.map(r=>`<tr><td>${ceoLink('orders',r.project_name,'',r.project_id)}<small>${r.currency} · ${esc(r.stage)}</small></td><td>${ceoMoney(r.contract_minor,r.currency)}</td><td>${ceoMoney(r.receipt,r.currency)}</td><td>${ceoMoney(r.receivable_minor,r.currency)}${r.customer_credit_minor?`<small>客户贷方 ${ceoMoney(r.customer_credit_minor,r.currency)}</small>`:''}</td><td>${r.received_ratio==null?'暂未接入':r.received_ratio+'%'}</td></tr>`)):empty('暂无已确认订单','确认原单或增项后，合同金额在这里汇总。');}
function receivablesTable(rows){return rows.length?table(['客户／项目','待收款','计划收款日期','状态'],rows.map(r=>`<tr><td>${esc(r.customer_name)}<small>${ceoLink('orders',r.project_name,'',r.project_id)}</small></td><td>${ceoMoney(r.receivable_minor,r.currency)}</td><td>待接入分期计划</td><td>${dashboardData.finance.enabled?'到期状态待核对':'财务未开放'}</td></tr>`)):empty('暂无待收款资料');}
function suppliersTable(rows){if(!dashboardData.finance.enabled)return empty('财务暂未开放','已预留供应商、采购单、待付款金额、付款计划和状态。');return rows.length?table(['供应商／采购单','已付款','待付款','付款计划'],rows.map(r=>`<tr><td>${esc(r.supplier_name)}<small>${ceoLink('procurement',r.po_number,r.id,r.project_id||'')}</small></td><td>${ceoMoney(r.paid_minor,r.currency||'CNY')}</td><td>${r.remaining_minor==null?'结算待确认':ceoMoney(r.remaining_minor,r.currency)}${r.overpaid_minor?`<small>超付 ${ceoMoney(r.overpaid_minor,r.currency)}</small>`:''}</td><td>待登记</td></tr>`)):empty('暂无采购付款记录');}
function profitTable(rows){return rows.length?table(['项目','合同净额','成本预算','预计利润／利润率'],rows.map(r=>`<tr><td>${ceoLink('costs',r.project_name,'',r.project_id)}<small>${r.currency}</small></td><td>${ceoMoney(r.net_minor,r.currency)}</td><td>${r.budget_minor==null?'待核定':ceoMoney(r.budget_minor,r.currency)}</td><td>${r.estimated_profit_minor==null?'待核算':ceoMoney(r.estimated_profit_minor,r.currency)+`<small>${r.estimated_margin==null?'—':r.estimated_margin+'%'}</small>`}</td></tr>`)):empty('暂无项目成本资料');}
function inventoryAnalysis(){const f=dashboardData.finance,names={purchase:'采购及售后共用仓',factory_toy:'工厂玩具仓',raw_material:'原材料仓',factory_material:'工厂原材料仓'};return `<div class="ceo-inventory"><div class="ceo-donut" data-ceo-background="#e4eaf2" role="img" aria-label="库存总价值待核定"><div><strong>待核定</strong><span>库存总价值</span></div></div><dl class="ceo-definition">${f.inventory.length?f.inventory.map(r=>`<div><dt>${esc(names[r.category]||r.category)}</dt><dd>${r.sku_count} 种 SKU</dd></div>`).join(''):'<div><dt>当前库存</dt><dd>尚无实物记录</dd></div>'}</dl></div><p class="ceo-note">${esc(f.inventory_note)} 库存范围为公司全部仓库，同一 SKU 可分布于多个仓类。</p>`;}
function trendChart(){
  const f=dashboardData.finance,rows=f.trend.filter(r=>r.currency===dashboardCurrency),series=[['contract_minor','累计合同','#315789'],['receipt','累计已收','#4e8663'],['receivable_minor','待收款','#ae7919']];
  const max=Math.max(1,...rows.flatMap(r=>series.map(([k])=>r[k]||0))),x=i=>46+i*52,y=n=>150-n/max*110;
  return `<div class="ceo-trend-controls"><label>币种<select id="dashboard-currency">${(f.summary.length?f.summary.map(s=>s.currency):['CNY']).map(c=>`<option ${c===dashboardCurrency?'selected':''}>${c}</option>`).join('')}</select></label><span>各月月末累计值 · 金额（元）</span></div>${rows.length?`<svg class="ceo-trend" viewBox="0 0 340 192" role="img" aria-label="${dashboardCurrency} 近六个月资金趋势，准确值见月度明细">${[0,.5,1].map(n=>`<line x1="46" x2="318" y1="${y(max*n)}" y2="${y(max*n)}" class="chart-grid"/><text x="40" y="${y(max*n)+4}" text-anchor="end">${(max*n/100).toLocaleString('zh-CN',{maximumFractionDigits:0,notation:'compact'})}</text>`).join('')}${series.filter(([k])=>rows.some(r=>r[k]!=null)).map(([k,label,color])=>`<polyline fill="none" stroke="${color}" stroke-width="2.5" points="${rows.map((r,i)=>`${x(i)},${y(r[k])}`).join(' ')}"/>${rows.map((r,i)=>`<circle cx="${x(i)}" cy="${y(r[k])}" r="3" fill="${color}"><title>${esc(r.month+' '+label+' '+ceoMoney(r[k],r.currency))}</title></circle>`).join('')}`).join('')}${rows.map((r,i)=>`<text x="${x(i)}" y="176" text-anchor="middle">${r.month.slice(5)}月</text>`).join('')}</svg>`:empty('暂无趋势数据')}<div class="ceo-chart-legend">${series.map(([k,label,color])=>`<span><i data-ceo-background="${color}" aria-hidden="true"></i>${label}${k!=='contract_minor'&&!f.enabled?' · 未接入':''}</span>`).join('')}</div>${drillButton('trend','查看月度数据')}`;
}
function dashboardDrill(){
  if(!dashboardList)return '';
  const d=dashboardData,f=d.finance;let title='项目明细',body='';
  if(dashboardList.startsWith('stage-')){const s=CEO_STAGES[Number(dashboardList.slice(6))];if(!s)return '';title=s[0];body=trackingTable(d.projects.filter(p=>s[1].includes(p.lifecycle_stage)));}
  else if(dashboardList.startsWith('progress-')){const i=Number(dashboardList.slice(9));title='交付进度明细';body=trackingTable(d.projects.filter(p=>p.progress!=null&&(i===0?p.progress>=0:p.progress>i*25)&&p.progress<=(i+1)*25));}
  else if(['projects','executing','upcoming','overdue'].includes(dashboardList)){body=trackingTable(d.projects.filter(p=>dashboardList==='projects'||dashboardList==='executing'&&p.executing||dashboardList==='upcoming'&&p.days_remaining!=null&&p.days_remaining>=0&&p.days_remaining<=30||dashboardList==='overdue'&&d.exceptions.some(e=>e.project_id===p.id&&e.overdue_days)));}
  else if(dashboardList==='risks'){title='全部异常预警';body=riskTable(d.exceptions);}
  else if(dashboardList==='orders'){title='本期已下单明细（含增项）';body=d.period_orders.length?table(['订单','项目','类型','下单时间','金额'],d.period_orders.map(b=>`<tr><td>${ceoLink('orders',b.number,b.id,b.project_id)}</td><td>${esc(b.project_name)}</td><td>${({domestic:'国内',overseas:'国外',unknown:'待确认'})[b.market]}</td><td>${b.kind==='addition'?'增项':'原单'}</td><td>${dashboardStamp(b.created_at)}</td><td>${ceoMoney(b.agreed_minor,b.currency)}</td></tr>`)):empty('本期没有已下单记录');}
  else if(dashboardList==='customers'){title='客户合作明细';body=d.customers.length?table(['客户','成交项目／合作次数','累计合同金额','项目'],d.customers.map(c=>`<tr><td>${esc(c.name)}</td><td>${c.cooperation_count}</td><td>${ceoAmounts(c.amounts)}</td><td>${d.projects.filter(p=>c.project_ids.includes(p.id)).map(projectLink).join('')}</td></tr>`)):empty('暂无客户合作记录');}
  else if(dashboardList==='tickets'){title='未关闭售后';body=d.tickets.length?table(['售后单／项目','问题','当前阶段','负责人','期限'],d.tickets.map(t=>`<tr><td>${ceoLink('aftersales',t.id,t.id,t.project_id)}<small>${esc(t.project_name)}</small></td><td>${esc(t.description)}</td><td>${esc(t.stage)}</td><td>${esc(t.owner)}</td><td>${esc(t.due_date||'待填写')}</td></tr>`)):empty('暂无未关闭售后');}
  else if(dashboardList.startsWith('annual-expense-')){const item=d.annual_expenses[dashboardList.replace('annual-expense-','')];title=item.label+'明细';body=!item.connected?empty('费用记录暂未接入','接入后按本年度自动汇总，不把缺少记录显示为零。'):item.records.length?table(['日期','凭证编号','平台／账号','费用类型','金额'],item.records.map(r=>`<tr><td>${esc(r.date)}</td><td>${esc(r.number)}</td><td>${esc(r.channel)}<small>${esc(r.activity||'—')}</small></td><td>${esc(r.category)}</td><td>${ceoMoney(r.minor,r.currency)}</td></tr>`)):empty('本年度暂无有效费用记录');}
  else if(['annual-contracts','monthly-contracts'].includes(dashboardList)){const period=d.contract_periods[dashboardList==='annual-contracts'?'annual':'monthly'];title=dashboardList==='annual-contracts'?'年度合同明细':'月度合同明细';body=period.orders.length?table(['合同编号','项目','地区','类型','下单日期','合同金额'],period.orders.map(b=>`<tr><td>${ceoLink('orders',b.number,b.id,b.project_id)}</td><td>${esc(b.project_name)}</td><td>${({domestic:'国内',overseas:'国外',unknown:'待确认'})[b.market]}</td><td>${b.kind==='addition'?'增项':'原单'}</td><td>${dashboardStamp(b.created_at)}</td><td>${ceoMoney(b.agreed_minor,b.currency)}</td></tr>`)):empty('当前期间暂无合同记录',period.from+' 至 '+period.to);}
  else if(dashboardList==='funds'){title='项目资金明细';body=fundsTable(f.projects);}
  else if(dashboardList==='receivables'){title='应收账款明细';body=receivablesTable(f.projects);}
  else if(dashboardList==='suppliers'){title='供应商付款明细';body=suppliersTable(f.suppliers);}
  else if(dashboardList==='profit'){title='项目预计利润明细';body=profitTable(f.projects);}
  else if(dashboardList==='inventory'){title='库存资产分析';body=inventoryAnalysis();}
  else if(dashboardList==='trend'){title='近六个月资金明细';body=f.trend.length?table(['月份','币种','累计合同','累计已收','待收款'],f.trend.map(r=>`<tr><td>${r.month}</td><td>${r.currency}</td><td>${ceoMoney(r.contract_minor,r.currency)}</td><td>${ceoMoney(r.receipt,r.currency)}</td><td>${ceoMoney(r.receivable_minor,r.currency)}</td></tr>`)):empty('暂无月度资料');}
  else if(dashboardList==='finance-risks'){title='资金待核对事项';body=f.risks==null?empty('财务暂未开放'):f.risks.length?table(['事项','关联单据'],f.risks.map(r=>`<tr><td>${esc(r.title)}</td><td>${ceoLink(r.target==='baseline'?'orders':r.target,r.detail,r.target_id,r.project_id||'')}</td></tr>`)):empty('暂无已记录的资金核对事项','付款计划未接入，不能据此判断资金风险为零。');}
  else if(dashboardList==='decisions'){title='特殊放行申请';body=decisionFeed();}
  else return '';
  return `<div id="dashboard-drill" tabindex="-1">${panel(title,body,button('dashboard-list','收起明细',''))}</div>`;
}
async function editMembers(id){
  if(!can('admin'))throw new Error('项目成员由管理员分配');
  const employees=(await api('/api/employees')).items.filter(e=>e.role!=='supplier');
  const p=state.projects.find(p=>p.id===id);
  if(!p)throw new Error('项目不存在，请刷新');
  const active=employees.filter(e=>e.status==='active');
  const chosen=new Set(p.members.map(m=>m.employee_id));
  modal('项目成员 · '+p.name,
    `<p class="form-help">选择负责或参与本项目的员工。移除成员后，该员工将不能继续查看本项目及其单据。</p>`+
    select('owner_id','项目负责人',active.map(e=>({id:e.id,name:`${e.name} · ${roles[e.role]} · ${e.email}`})),p.owner_id||'',false)+
    `<fieldset class="member-list full"><legend>参与成员</legend>${active.length?active.map(e=>`<label><input type="checkbox" name="member" value="${esc(e.id)}" ${chosen.has(e.id)?'checked':''}><span><strong>${esc(e.name)}</strong><small>${roles[e.role]} · ${esc(e.email)}</small></span></label>`).join(''):empty('请先在人员与权限建立员工账号')}</fieldset>`+
    `<p class="form-help">管理员与 CEO 始终可查看全部项目。${p.legacy_owner&&!p.owner_id?`历史负责人姓名“${esc(p.legacy_owner)}”仅供核对，不作为授权。`:''}${p.members.some(m=>m.status!=='active')?'本次保存会移除已停用的成员。':''}</p>`,
    values=>{
      const ids=[...$('#dialog-fields').querySelectorAll('input[name="member"]:checked')].map(e=>e.value);
      if(values.owner_id&&!ids.includes(values.owner_id))ids.push(values.owner_id);
      return act('project-members',{project_id:id,member_version:p.member_version,employee_ids:ids,owner_id:values.owner_id||null});
    },'保存项目成员');
}

async function dashboardAction(name,id){
  if(name==='members'){await editMembers(id);return true;}
  if(name==='dashboard-list'){dashboardList=dashboardList===id?'':id;dashboardUrl();drawDashboard();const target=$('#dashboard-drill')||$('#content');target.focus();target.scrollIntoView({block:'nearest'});return true;}
  if(name==='dashboard-tab'){dashboardTab=id==='finance'?'finance':'overview';dashboardList='';dashboardUrl();drawDashboard();$('#content').focus();return true;}
  if(name==='dashboard-fullscreen'){if(document.fullscreenElement)await document.exitFullscreen();else await $('.workspace').requestFullscreen();drawDashboard();return true;}
  if(name==='dashboard-this-month'){const date=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());dashboardPeriod={from:date.slice(0,8)+'01',to:date};await render();return true;}
  return false;
}
document.addEventListener('submit',async event=>{
  if(event.target.id!=='dashboard-period-form')return;event.preventDefault();
  const next=Object.fromEntries(new FormData(event.target));if(next.from>next.to){notify('开始日期不能晚于结束日期');return;}
  const previous=dashboardPeriod;dashboardPeriod=next;
  try{await render();}catch(err){dashboardPeriod=previous;drawDashboard();notify(err.message);}
});
document.addEventListener('change',async event=>{
  if(event.target.id==='dashboard-project-filter'){const prior=dashboardProject;dashboardProject=event.target.value;dashboardList='';try{await render();}catch(err){dashboardProject=prior;drawDashboard();notify(err.message);}}
  if(event.target.id==='dashboard-currency'){dashboardCurrency=event.target.value;dashboardUrl();drawDashboard();}
});

document.addEventListener('fullscreenchange',()=>{const b=document.querySelector('[data-action="dashboard-fullscreen"]');if(b)b.textContent=document.fullscreenElement?'退出全屏':'全屏查看';});

// Keep the visible dashboard current without resetting filters or open details.
setInterval(async()=>{
  if(view!=='dashboard'||document.hidden||document.querySelector('dialog[open]'))return;
  const params=new URLSearchParams(dashboardPeriod);if(dashboardProject)params.set('project',dashboardProject);
  const requested=params.toString();
  try{const result=await api('/api/dashboard?'+requested);const current=new URLSearchParams(dashboardPeriod);if(dashboardProject)current.set('project',dashboardProject);
    if(view==='dashboard'&&current.toString()===requested&&JSON.stringify(result)!==JSON.stringify(dashboardData)){dashboardData=result;drawDashboard();}
  }catch(error){console.warn('看板自动更新暂未成功');}
},30000);
