(()=>{
'use strict';
const fragment=new URLSearchParams(location.hash.slice(1));
let token=fragment.get('token')||'';
history.replaceState(null,'','/password-recovery');
const fields=document.querySelector('#fields'),message=document.querySelector('#message'),button=document.querySelector('#submit');
if(token){document.querySelector('#heading').textContent='设置新密码';document.querySelector('#description').textContent='此链接仅可使用一次，30 分钟内有效。请自行设置新密码。';fields.innerHTML='<label>姓名（首次建立账号时使用）<input name="name" autocomplete="name" maxlength="100"></label><label>新密码<input name="password" type="password" required minlength="10" maxlength="256" autocomplete="new-password"></label><label>确认新密码<input name="confirm" type="password" required minlength="10" maxlength="256" autocomplete="new-password"></label>';button.textContent='保存新密码';}
else fields.innerHTML='<label>账号邮箱<input name="email" type="email" required maxlength="254" autocomplete="username"></label>';
document.querySelector('#recovery-form').addEventListener('submit',async event=>{event.preventDefault();button.disabled=true;message.textContent='';try{const payload=Object.fromEntries(new FormData(event.target));if(token&&payload.password!==payload.confirm)throw new Error('两次密码输入不一致');if(token)payload.token=token;const response=await fetch(token?'/api/auth/reset-link':'/api/auth/recovery-request',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const result=await response.json();if(!response.ok)throw new Error(result.error||'暂时无法提交，请稍后重试');if(token){token='';fields.replaceChildren();button.hidden=true;message.textContent='密码已保存，请返回登录，使用新密码进入。';}else{message.textContent=result.message;button.textContent='申请已提交';}}catch(error){message.textContent=error.message;}finally{button.disabled=false;}});
})();
