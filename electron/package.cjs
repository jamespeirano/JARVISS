require('./build-map.cjs');
const {packager}=require('@electron/packager');
packager({dir:__dirname,name:'JARVISS',out:require('node:path').resolve(__dirname,'../dist'),overwrite:true,asar:true,
 icon:require('node:path').join(__dirname,'icons/icon'),
 extraResource:[require('node:path').join(__dirname,'backend')],
 ignore:[/^\/backend($|\/)/,/^\/tests($|\/)/,/^\/package.cjs$/],
 appBundleId:'org.jarviss.desktop',appCategoryType:'public.app-category.productivity',
 extendInfo:{NSMicrophoneUsageDescription:'JARVISS transcribes your speech locally for hands-free conversation.'}
}).then(paths=>console.log(paths.join('\n'))).catch(e=>{console.error(e);process.exitCode=1;});
