// The renderer can request only map assets and ranges of the selected archive.
const fs=require('node:fs');
const path=require('node:path');
const {Readable}=require('node:stream');

function atlasHandler({assets,getArchive}) {
 return async request=>{
  const headers={'Access-Control-Allow-Origin':'*','Cache-Control':'no-cache'};
  try {
   const url=new URL(request.url);
   if(url.hostname!=='local')return new Response('Not found',{status:404,headers});
   if(!['GET','HEAD'].includes(request.method))return new Response(null,{status:405,headers:{...headers,Allow:'GET, HEAD'}});
   const pathname=decodeURIComponent(url.pathname);
   let file;
   if(pathname==='/archive.pmtiles')file=getArchive();
   else {
    file=path.resolve(assets,'.'+pathname);
    if(!file.startsWith(path.resolve(assets)+path.sep))return new Response('Not found',{status:404,headers});
   }
   if(!file)return new Response('Choose a local basemap first.',{status:404,headers});
   const info=await fs.promises.stat(file);
   if(!info.isFile())return new Response('Not found',{status:404,headers});
   const etag=`"${info.size}-${info.mtimeMs}"`;
   Object.assign(headers,{'Accept-Ranges':'bytes',ETag:etag,'Content-Type':({'.pmtiles':'application/vnd.pmtiles','.pbf':'application/x-protobuf','.png':'image/png','.json':'application/json','.mjs':'text/javascript','.js':'text/javascript','.css':'text/css'})[path.extname(file)]||'application/octet-stream'});
   let start=0,end=info.size-1,status=200;
   const range=request.headers.get('range');
   if(range){
    const match=/^bytes=(\d*)-(\d*)$/.exec(range);
    if(!match||(!match[1]&&!match[2]))start=info.size;
    else{
     start=match[1]?Number(match[1]):Math.max(0,info.size-Number(match[2]));
     end=match[1]&&match[2]?Math.min(end,Number(match[2])):end;
    }
    if(!Number.isSafeInteger(start)||!Number.isSafeInteger(end)||start<0||start>end||start>=info.size)return new Response(null,{status:416,headers:{...headers,'Content-Range':`bytes */${info.size}`}});
    status=206;headers['Content-Range']=`bytes ${start}-${end}/${info.size}`;
   }
   headers['Content-Length']=String(end-start+1);
   if(request.method==='HEAD')return new Response(null,{status,headers});
   return new Response(Readable.toWeb(fs.createReadStream(file,{start,end})),{status,headers});
  }catch{return new Response('Local map file unavailable. Reimport the archive.',{status:404,headers});}
 };
}
module.exports={atlasHandler};
