import { Container, getContainer } from '@cloudflare/containers';
export { ContainerProxy } from '@cloudflare/containers';
import { createRemoteJWKSet, jwtVerify } from 'jose';
import browserSource from './module-browser.js.txt';
export { BusinessDatabase } from './business-database.js';

const ports = { quote: 8991, procurement: 8992, aftersales: 8993 };
const keys = new Map();
export class WorkplaceContainer extends Container {
  defaultPort = 8975;
  requiredPorts = [8975, 8991, 8992, 8993];
  sleepAfter = '2m';
  constructor(ctx, env) {
    super(ctx, env);
    this.envVars = {
      YIFUN_CONTAINER_MODE: '1', YIFUN_AUTH_MODE: env.AUTH_MODE || 'access', YIFUN_PUBLIC_ORIGIN: env.PUBLIC_ORIGIN,
      YIFUN_OWNER_EMAIL: env.OWNER_EMAIL, YIFUN_VIEWER_EMAILS: env.VIEWER_EMAILS,
      YIFUN_DATA_ROOT: '/tmp/workplace-runtime', YIFUN_DEMO_MODE: '1',
      YIFUN_DATABASE_BACKEND: 'cloudflare', YIFUN_DATABASE_ENDPOINT: 'http://database.yifun.internal',
      YIFUN_OBJECT_BACKEND: 'r2', YIFUN_OBJECT_ENDPOINT: 'http://objects.yifun.internal',
      WRANGLER_SEND_METRICS: 'false', NODE_ENV: 'production'
    };
  }
  async fetch(request) {
    const url = new URL(request.url);
    const match = url.pathname.match(/^\/modules\/(quote|procurement|aftersales)(?:\/|$)/);
    const name = match?.[1];
    await this.startAndWaitForPorts({ ports: name ? [8975,ports[name]] : [8975], cancellationOptions: { portReadyTimeoutMS: 90000 } });
    if (!name) return this.containerFetch(request);
    const base = '/modules/' + name;
    if (url.pathname === base + '/cloud-entry.js') {
      return new Response(browserSource, { headers: { 'Content-Type': 'application/javascript; charset=utf-8', 'Cache-Control': 'no-store' } });
    }
    url.pathname = url.pathname.slice(base.length) || '/';
    const response = await this.containerFetch(new Request(url, request), ports[name]);
    const headers = new Headers(response.headers);
    headers.delete('Content-Length');
    headers.set('Cache-Control', 'no-store');
    const redirect = headers.get('Location');
    if (redirect?.startsWith('/') && !redirect.startsWith('/modules/')) headers.set('Location', base + redirect);
    const type = headers.get('Content-Type') || '';
    if (type.includes('application/json')) {
      const linkFields = new Set(['url','href','src','imageUrl','image_url','downloadUrl','fileUrl','photoUrl','previewUrl','attachmentUrl']);
      const mapLinks = (value, key = '') => {
        if (Array.isArray(value)) return value.map(item=>mapLinks(item,key));
        if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([field,item])=>[field,mapLinks(item,field)]));
        return typeof value === 'string' && linkFields.has(key) && /^\/(api|assets|brand)\//.test(value) ? base+value : value;
      };
      return new Response(JSON.stringify(mapLinks(await response.json())), { status: response.status, headers });
    }
    if (type.includes('text/html')) {
      const body = await response.text();
      const patched = body.replace(/<head([^>]*)>/i, '<head$1><script src="' + base + '/cloud-entry.js"></script>');
      const rewriter = new HTMLRewriter().on('[src],[href],[action]', {
        element(element) {
          for (const attribute of ['src', 'href', 'action']) {
            const value = element.getAttribute(attribute);
            if (value?.startsWith('http://127.0.0.1:8975')) element.setAttribute(attribute, url.origin + value.slice('http://127.0.0.1:8975'.length));
            else if (value?.startsWith('/') && !value.startsWith('//') && !value.startsWith('/modules/')) element.setAttribute(attribute, base + value);
          }
        }
      });
      return rewriter.transform(new Response(patched, { status: response.status, headers }));
    }
    return new Response(response.body, { status: response.status, headers });
  }
}

async function objectRequest(request, env, core = false) {
  const url = new URL(request.url);
  const pieces = url.pathname.split('/').filter(Boolean).map(decodeURIComponent);
  const store = core ? 'core' : pieces.shift();
  if (core && pieces.shift() !== 'objects') return new Response(null, { status: 404 });
  const bucket = { core: env.CORE_FILES, quote: env.QUOTE_FILES, procurement: env.PROCUREMENT_FILES, aftersales: env.AFTERSALES_FILES }[store];
  const key = pieces.join('/');
  if (!bucket || !key || pieces.includes('..') || key.includes('\\')) return new Response(null, { status: 400 });
  if (request.method === 'GET') {
    const object = await bucket.get(key);
    if (!object) return new Response(null, { status: 404 });
    const headers = new Headers(); object.writeHttpMetadata(headers);
    headers.set('ETag', object.httpEtag); headers.set('Content-Length', String(object.size));
    return new Response(object.body, { headers });
  }
  if (request.method === 'PUT') {
    const limit = core ? 5 * 1024 * 1024 : 25 * 1024 * 1024;
    const body = await request.arrayBuffer();
    if (!body.byteLength || body.byteLength > limit) return new Response(null, { status: 413 });
    await bucket.put(key, body, { httpMetadata: { contentType: request.headers.get('Content-Type') || 'application/octet-stream' } });
    return new Response(null, { status: 204 });
  }
  if (!core && request.method === 'DELETE') { await bucket.delete(key); return new Response(null, { status: 204 }); }
  return new Response(null, { status: 405 });
}

WorkplaceContainer.outboundByHost = {
  'database.yifun.internal': (request, env) => env.BUSINESS_DATABASE.getByName('workplace-business-v1').fetch(request),
  'objects.yifun.internal': (request, env) => objectRequest(request, env, true),
  'files.yifun.internal': (request, env) => objectRequest(request, env)
};

export default {
  async scheduled(controller, env, ctx) {
    const response = await getContainer(env.WORKPLACE_CONTAINER, 'workplace-v1').fetch(new Request(env.PUBLIC_ORIGIN + '/internal/android-maintenance', {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Yifun-Internal-Schedule': 'android-ops-v1' }, body: '{}'
    }));
    if (!response.ok) throw new Error('Android scheduled maintenance failed: HTTP ' + response.status);
  },
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.origin !== env.PUBLIC_ORIGIN) return new Response('Invalid site origin', { status: 403 });
    // These APIs are exclusively for the private module/database bridge.
    if (url.pathname.startsWith('/internal/') || url.pathname.startsWith('/api/internal/')) return new Response(null, { status: 404 });
    let identity;
    const headers = new Headers(request.headers);
    headers.delete('X-Workspace-Bridge'); headers.delete('X-Yifun-Verified-Email');
    const app = getContainer(env.WORKPLACE_CONTAINER, 'workplace-v1');
    if (url.pathname === '/api/auth/recover') return new Response(null, {status:404});
    if (url.pathname === '/account-recovery' || url.pathname === '/account-recovery/reset') {
      const issuer=(env.ACCESS_ISSUER || '').replace(/\/$/,'');
      if(!/^https:\/\/[a-zA-Z0-9-]+\.cloudflareaccess\.com$/.test(issuer) || !env.ACCESS_AUD) return new Response('账号恢复暂未配置',{status:503});
      let email;
      try {
        if(!keys.has(issuer)) keys.set(issuer,createRemoteJWKSet(new URL(issuer+'/cdn-cgi/access/certs')));
        const {payload}=await jwtVerify(request.headers.get('Cf-Access-Jwt-Assertion')||'',keys.get(issuer),{issuer,audience:env.ACCESS_AUD,algorithms:['RS256']});
        email=String(payload.email||'').toLowerCase();
      } catch {return new Response('请先通过邮箱验证码验证身份。',{status:401});}
      const allowed=[env.OWNER_EMAIL.toLowerCase(),...(env.VIEWER_EMAILS||'').split(',').map(value=>value.trim().toLowerCase())];
      if(!allowed.includes(email)) return new Response('此邮箱未获授权。',{status:403});
      const escape=value=>String(value).replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
      const page=(message='',status=200)=>new Response(`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>亦玩 · 找回账号密码</title><style>body{font:16px system-ui;background:#f4f7fb;color:#183765;margin:0}main{max-width:420px;margin:8vh auto;padding:28px;background:white;border-radius:12px}label{display:block;margin:16px 0}input,button{box-sizing:border-box;width:100%;padding:12px;margin-top:6px;border:1px solid #cbd5e1;border-radius:6px;font:inherit}button{background:#264b82;color:white}p{line-height:1.6}.error{color:#b91c1c}</style><main><h1>找回账号／密码</h1><p>已验证邮箱：${escape(email)}</p><p class="error">${escape(message)}</p><form method="post" action="/account-recovery/reset"><label>姓名（首次建立账号时使用）<input name="name" autocomplete="name" maxlength="100"></label><label>新密码<input name="password" type="password" required minlength="10" maxlength="256" autocomplete="new-password"></label><label>确认新密码<input name="confirm" type="password" required minlength="10" maxlength="256" autocomplete="new-password"></label><button>保存新密码</button></form><p><a href="/">返回登录</a></p></main></html>`,{status,headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",'Referrer-Policy':'same-origin'}});
      if(request.method==='GET' && url.pathname==='/account-recovery')return page();
      if(request.method==='GET' && url.pathname==='/account-recovery/reset')return new Response(null,{status:303,headers:{Location:'/account-recovery','Cache-Control':'no-store'}});
      if(request.method!=='POST' || url.pathname!=='/account-recovery/reset')return new Response('请从账号找回页面提交新密码。',{status:405,headers:{'Content-Type':'text/plain; charset=utf-8'}});
      if(request.headers.get('Origin')!==env.PUBLIC_ORIGIN)return page('提交来源校验失败，请重新打开找回页面后再保存。',403);
      const form=await request.formData();
      headers.set('Content-Type','application/json');headers.set('X-Yifun-Verified-Email',email);headers.delete('Content-Length');
      const result=await app.fetch(new Request(new URL('/api/auth/recover',url.origin),{method:'POST',headers,body:JSON.stringify({name:form.get('name'),password:form.get('password'),confirm:form.get('confirm')})}));
      if(!result.ok){const payload=await result.json();return page(payload.error||'暂时无法保存，请稍后重试。');}
      return new Response(null,{status:303,headers:{Location:'/', 'Cache-Control':'no-store'}});
    }
    const customerPage = ['GET','HEAD'].includes(request.method) && new Set(['/aftercare/request','/aftercare/public/request.js','/aftercare/public/portal.css']).has(url.pathname);
    const customerApi = request.method==='GET' && url.pathname==='/api/aftercare/portal' || request.method==='POST' && url.pathname==='/api/aftercare/submit' || request.method==='GET' && /^\/api\/aftercare\/file\/[a-f0-9-]+$/.test(url.pathname) && /^[a-f0-9]{64}$/.test(url.searchParams.get('token')||'');
    if(customerPage || customerApi)return app.fetch(new Request(request,{headers}));
    if (env.AUTH_MODE === 'password') {
      const assets = new Set(['/sales-dashboard.js', '/sales-dashboard.css', '/', '/read-cache.js', '/password-recovery', '/password-recovery.js', '/workplace.js', '/dashboard.js', '/operations.js', '/centers.js', '/connections.js', '/workplace.css', '/workplace-theme.css', '/dashboard.css', '/operations.css', '/centers.css', '/workplace-logo.png', '/workplace-favicon.png', '/workplace-favicon.svg']);
      const loginPaths = new Set(['/api/auth/session', '/api/auth/login', '/api/auth/logout', '/api/auth/recovery-request', '/api/auth/reset-link']);
      if (['GET', 'HEAD'].includes(request.method) && assets.has(url.pathname) || loginPaths.has(url.pathname)) {
        return app.fetch(new Request(request, { headers }));
      }
      if (!url.pathname.startsWith('/modules/')) return app.fetch(new Request(request,{headers}));
      const checkUrl = new URL('/api/auth/session', url.origin);
      const checked = await app.fetch(new Request(checkUrl, { headers, method: 'GET' }));
      if (!checked.ok) return new Response('登录验证暂时不可用，请稍后重试。', { status: 503 });
      const session = await checked.json();
      if (!session.authenticated) return Response.json({ error: '请使用自己的账号密码登录。' }, { status: 401 });
      identity = String(session.user?.email || '').toLowerCase();
    } else {
    if (!env.ACCESS_ISSUER || !env.ACCESS_AUD) return new Response('站点部署中，登录入口尚未开放。', { status: 503 });
    const issuer = env.ACCESS_ISSUER.replace(/\/$/, '');
    if (!/^https:\/\/[a-zA-Z0-9-]+\.cloudflareaccess\.com$/.test(issuer)) return new Response(null, { status: 503 });
    try {
      if (!keys.has(issuer)) keys.set(issuer, createRemoteJWKSet(new URL(issuer + '/cdn-cgi/access/certs')));
      const token = request.headers.get('Cf-Access-Jwt-Assertion') || '';
      const { payload } = await jwtVerify(token, keys.get(issuer), { issuer, audience: env.ACCESS_AUD, algorithms: ['RS256'] });
      identity = String(payload.email || '').toLowerCase();
    } catch { return new Response('请通过站点登录入口访问。', { status: 401 }); }
    }
    const owner = env.OWNER_EMAIL.toLowerCase();
    const viewers = (env.VIEWER_EMAILS || '').split(',').map(value => value.trim().toLowerCase());
    if (env.AUTH_MODE !== 'password' && identity !== owner && !viewers.includes(identity)) return new Response('此账号无查看权限。', { status: 403 });
    const personal = ['/api/auth/setup', '/api/auth/login', '/api/auth/logout', '/api/context', '/api/password'];
    if (identity !== owner && !['GET', 'HEAD'].includes(request.method) && !personal.includes(url.pathname)) {
      return Response.json({ error: '共享账号仅可查看' }, { status: 403 });
    }
    headers.set('X-Yifun-Verified-Email', identity);
    return getContainer(env.WORKPLACE_CONTAINER, 'workplace-v1').fetch(new Request(request, { headers }));
  }
};
