// Decrypt an authenticated migration backup; never overwrite an existing output.
import fs from 'node:fs';
import crypto from 'node:crypto';
const [input,keyFile,output]=process.argv.slice(2);
if(!input||!keyFile||!output)throw Error('Usage: node restore-backup.mjs backup.enc key-file output.tar.gz');
const data=fs.readFileSync(input),key=Buffer.from(fs.readFileSync(keyFile,'utf8').trim(),'hex');
if(data.subarray(0,8).toString()!=='YIFUNBK1'||key.length!==32)throw Error('Invalid backup or key');
const decrypt=crypto.createDecipheriv('aes-256-gcm',key,data.subarray(8,20));
decrypt.setAuthTag(data.subarray(20,36));
const clear=Buffer.concat([decrypt.update(data.subarray(36)),decrypt.final()]);
fs.writeFileSync(output,clear,{flag:'wx',mode:0o600});
console.log('Verified and decrypted backup. Inspect and import only into an authorized empty destination.');
