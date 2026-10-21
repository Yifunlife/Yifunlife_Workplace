export async function workspace(request: Request, env:any, module:string) {
  const origin=request.headers.get('origin');
  if(!['GET','HEAD'].includes(request.method) && origin && !(env.PUBLIC_ORIGIN ? [env.PUBLIC_ORIGIN] : ['http://127.0.0.1:8975','http://127.0.0.1:8991','http://127.0.0.1:8992','http://127.0.0.1:8993']).includes(origin)) return null;
  const result=await fetch(`${env.WORKPLACE_URL || 'http://127.0.0.1:8975'}/api/internal/session?module=${module}&method=${encodeURIComponent(request.method)}`,{headers:{'X-Workspace-Bridge':env.WORKSPACE_BRIDGE||'',Cookie:request.headers.get('Cookie')||'','X-Yifun-Verified-Email':request.headers.get('X-Yifun-Verified-Email')||''}});
  return result.ok ? await result.json() as any : null;
}
export async function core(request:Request,env:any,path:string,method='GET',body?:any) {
 const result=await fetch(`${env.WORKPLACE_URL || 'http://127.0.0.1:8975'}${path}`,{method,headers:{'Content-Type':'application/json','X-Workspace-Bridge':env.WORKSPACE_BRIDGE||'',Cookie:request.headers.get('Cookie')||'','X-Yifun-Verified-Email':request.headers.get('X-Yifun-Verified-Email')||''},body:body===undefined?undefined:JSON.stringify(body)});
 return new Response(result.body,{status:result.status,headers:{'Content-Type':'application/json'}});
}

export async function requireEntity(request:Request,env:any,entity:string,id:string) {
  const result=await core(request,env,`/api/internal/access?entity=${encodeURIComponent(entity)}&id=${encodeURIComponent(id)}`);
  return result.ok ? null : result;
}
