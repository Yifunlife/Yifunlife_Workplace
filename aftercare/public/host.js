(()=>{
 const ctx=window.__AFTERCARE_CONTEXT__;if(!ctx)return;
 const scopeProject=new URLSearchParams(location.search).get('project');if(scopeProject)ctx.projects=ctx.projects.filter(p=>p.id===scopeProject);
 const original=window.fetch.bind(window);
 window.fetch=(input,options={})=>{const url=new URL(input instanceof Request?input.url:input,location.href);if(scopeProject&&url.pathname==='/api/aftercare/work-items'&&!(options.method||'').match(/POST/i)){url.searchParams.set('project',scopeProject);input=url.href;}if(url.origin===location.origin&&url.pathname.startsWith('/api/')){const headers=new Headers(options.headers||(input instanceof Request?input.headers:undefined));headers.set('X-Yifun-Token',ctx.csrf);options={...options,headers};}return original(input,options);};
 window.openai={widgetState:{privateContent:{}},setWidgetState:async()=>{}};
})();
