const fs=require('node:fs'),path=require('node:path');
const {buildSync}=require('esbuild');
const root=__dirname,dist=path.join(root,'node_modules/maplibre-gl/dist'),assets=path.join(root,'map-assets');
fs.mkdirSync(assets,{recursive:true});
for(const name of ['maplibre-gl.css','maplibre-gl-worker.mjs','maplibre-gl-shared.mjs'])fs.copyFileSync(path.join(dist,name),path.join(assets,name));
buildSync({entryPoints:[path.join(root,'map-view.mjs')],bundle:true,format:'iife',target:'chrome140',outfile:path.join(root,'map-bundle.js'),minify:true,legalComments:'external'});
