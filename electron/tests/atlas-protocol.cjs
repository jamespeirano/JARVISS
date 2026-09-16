const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {atlasHandler}=require('../atlas-protocol.cjs');
(async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'atlas-protocol-'));
 try{
  const archive=path.join(dir,'data.pmtiles');fs.writeFileSync(archive,Buffer.from('0123456789'));
  const handler=atlasHandler({assets:dir,getArchive:()=>archive});
  const request=(route,range,method='GET')=>handler(new Request('atlas://local'+route,{method,headers:range?{Range:range}:{}}));
  let r=await request('/archive.pmtiles','bytes=2-5');assert.equal(r.status,206);assert.equal(await r.text(),'2345');assert.equal(r.headers.get('content-range'),'bytes 2-5/10');
  r=await request('/archive.pmtiles','bytes=-2');assert.equal(await r.text(),'89');
  r=await request('/archive.pmtiles','bytes=10-20');assert.equal(r.status,416);
  r=await request('/archive.pmtiles','bytes=1-2,4-5');assert.equal(r.status,416);
  r=await request('/archive.pmtiles',null,'HEAD');assert.equal(r.headers.get('content-length'),'10');assert.equal(await r.text(),'');
  r=await request('/archive.pmtiles',null,'POST');assert.equal(r.status,405);
  r=await request('/..%2f..%2fprivate.txt');assert.equal(r.status,404);
  r=await request('/missing.pbf');assert.equal(r.status,404);
  console.log('PASS: local byte ranges, HEAD, invalid ranges, unavailable assets and traversal protection');
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
