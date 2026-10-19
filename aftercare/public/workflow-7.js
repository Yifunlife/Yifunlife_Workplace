
(()=>{
const app=document.getElementById('yw-after-sales');
const menu=document.createElement('button');menu.type='button';menu.className='yw-mobile-menu';menu.setAttribute('aria-label','展开部门导航');menu.setAttribute('aria-expanded','false');menu.innerHTML='<i data-lucide="menu" aria-hidden="true"></i>';app.querySelector(':scope>header').append(menu);
menu.addEventListener('click',()=>{const open=app.classList.toggle('mobile-nav-open');menu.setAttribute('aria-expanded',String(open));});
app.querySelector(':scope>.shell>nav').addEventListener('click',e=>{if(e.target.closest('[data-nav]')){app.classList.remove('mobile-nav-open');menu.setAttribute('aria-expanded','false');}});
let pending=false;
function enhance(){pending=false;app.querySelectorAll('.order-progress-table>table').forEach(t=>{const labels=[...t.querySelectorAll(':scope>thead>tr>th')].map(x=>x.textContent);t.querySelectorAll(':scope>tbody>tr:not(.order-expanded-row)').forEach(row=>[...row.children].forEach((td,i)=>{if(td.dataset.label!==labels[i])td.dataset.label=labels[i]||'';}));});}
const observer=new MutationObserver(records=>{if(records.some(r=>r.type==='childList')&&!pending){pending=true;requestAnimationFrame(enhance);}});observer.observe(app,{childList:true,subtree:true});enhance();
if(window.lucide)window.lucide.createIcons({attrs:{width:17,height:17}});
})();

