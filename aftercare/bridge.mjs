// Runs only behind Workplace's verified server session and scoped database snapshot.
import {DatabaseSync} from 'node:sqlite';
import {handleCustomerIntake} from './lib/customer-intake.mjs';
let raw='';for await(const chunk of process.stdin)raw+=chunk;
const input=JSON.parse(raw),sqlite=new DatabaseSync(':memory:'),writes=[],objects=[];
for(const table of input.tables){sqlite.exec(table.sql);if(table.rows.length){const stmt=sqlite.prepare(`INSERT INTO "${table.name}" (${table.columns.map(x=>'"'+x+'"').join(',')}) VALUES (${table.columns.map(()=>'?').join(',')})`);for(const row of table.rows)stmt.run(...row);}}
globalThis.__aftercareUser=input.user;
class Statement{
 constructor(sql,args=[]){this.sql=sql;this.args=args;}
 bind(...args){return new Statement(this.sql,args)}
 async first(){return sqlite.prepare(this.sql).get(...this.args)||null}
 async all(){return {results:sqlite.prepare(this.sql).all(...this.args)}}
 async run(){const r=sqlite.prepare(this.sql).run(...this.args);writes.push({sql:this.sql,args:this.args,changes:Number(r.changes)});return {meta:{changes:Number(r.changes),last_row_id:Number(r.lastInsertRowid)}}}
}
const db={prepare:sql=>new Statement(sql),batch:async statements=>{sqlite.exec('SAVEPOINT batch');const start=writes.length;try{const r=[];for(const s of statements)r.push(await s.run());sqlite.exec('RELEASE batch');return r}catch(e){sqlite.exec('ROLLBACK TO batch; RELEASE batch');writes.length=start;throw e}}};
const bucket={put:async(key,body,options)=>{const bytes=await new Response(body).arrayBuffer();objects.push({op:'put',key,data:Buffer.from(bytes).toString('base64'),mime:options?.httpMetadata?.contentType||'application/octet-stream'})},get:async key=>input.objects?.[key]?{body:Buffer.from(input.objects[key],'base64')}:null,delete:async key=>{const n=objects.findIndex(x=>x.key===key);if(n>=0)objects.splice(n,1)}};
try{
 const request=new Request(input.url,{method:input.method,headers:input.headers,...(input.method==='GET'?{}:{body:Buffer.from(input.body,'base64')})});
 const response=await handleCustomerIntake(request,{db,bucket});
 const body=Buffer.from(await response.arrayBuffer()).toString('base64');
 process.stdout.write(JSON.stringify({status:response.status,headers:Object.fromEntries(response.headers),body,writes:response.ok?writes:writes.filter(w=>/^INSERT INTO customer_rate_limits/i.test(w.sql)),objects:response.ok?objects:[]}));
}catch(e){process.stdout.write(JSON.stringify({status:500,headers:{'content-type':'application/json'},body:Buffer.from(JSON.stringify({error:'售后处理暂未完成，请刷新重试。'})).toString('base64'),writes:[],objects:[]}));process.stderr.write(String(e));}
