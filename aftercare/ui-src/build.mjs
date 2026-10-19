import {build} from 'esbuild';
await build({entryPoints:['request.tsx','customers.tsx'],outdir:'../public',bundle:true,minify:true,jsx:'automatic'});
