export async function sessionUser(){return globalThis.__aftercareUser||null;}
export async function digest(raw){return Buffer.from(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(raw))).toString('hex');}
