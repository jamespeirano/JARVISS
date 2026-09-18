const {_electron:electron}=require('playwright');
const {spawn}=require('node:child_process');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{const root=path.resolve(__dirname,'../..'),temp=fs.mkdtempSync(path.join(os.tmpdir(),'jarvis-board-'));let app,server;
try{
 server=spawn(path.join(root,process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python'),['-u','-c','from jarviss.local_board import LocalBoard; import json,sys; b=LocalBoard(); print(json.dumps(b.start("127.0.0.1"))); sys.stdin.read(); b.close()'],{cwd:root,env:{...process.env,JARVISS_DATA:temp}});
 const board=await new Promise((resolve,reject)=>{let text='';server.stdout.on('data',d=>{text+=d;if(text.includes('\n'))resolve(JSON.parse(text.split('\n')[0]));});server.on('error',reject);server.on('exit',code=>reject(Error('Board exited '+code)));});
 const entry=path.join(temp,'board-app.cjs');fs.writeFileSync(entry,`const {app,BrowserWindow}=require('electron');app.whenReady().then(()=>{for(let i=0;i<2;i++){const w=new BrowserWindow({width:420,height:850,webPreferences:{contextIsolation:true,nodeIntegration:false}});w.loadURL(${JSON.stringify(board.address)});}});app.on('window-all-closed',()=>app.quit());`);
 const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
 app=await electron.launch({args:[entry],env});await app.firstWindow();const deadline=Date.now()+15000;while(app.windows().length<2){if(Date.now()>deadline)throw Error("Second client did not open");await new Promise(r=>setTimeout(r,50));}const [a,b]=app.windows();
 for(const page of [a,b])await page.waitForSelector('#join');
 await a.locator('#code').fill('WRONG');await a.locator('#join').click();await a.waitForFunction(()=>document.querySelector('#status').textContent.includes('code'));
 for(const page of [a,b]){await page.locator('#code').fill(board.code);await page.locator('#join').click();}
 await a.locator('#name').fill('Alex');await a.locator('#text').fill('Meet at the library at noon.');await a.locator('#form button').click();
 await b.waitForFunction(()=>document.querySelector('#messages').textContent.includes('library'),null,{timeout:10000});
 await b.locator('#name').fill('Sam');await b.locator('#text').fill('<b>Received</b>. Bringing water.');await b.locator('#form button').click();
 await a.waitForFunction(()=>document.querySelector('#messages').textContent.includes('<b>Received</b>'),null,{timeout:10000});
 assert.equal(await a.locator('#messages b').count(),0);assert.equal(await a.locator('#messages article').count(),2);
 assert.equal(await a.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 await a.screenshot({path:path.join(root,'local-data/board.png')});
 console.log('PASS: two board browser clients; wrong-code recovery; posting; automatic receipt; text escaping; phone-width layout');
}finally{if(app)await app.close();if(server){server.stdin.end();await new Promise(resolve=>server.once('exit',resolve));}fs.rmSync(temp,{recursive:true,force:true});}})().catch(e=>{console.error(e);process.exitCode=1;});
