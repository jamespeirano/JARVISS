// Local layout preferences only. Drag a divider or use its arrow keys; double-click resets its width.
(() => {
 const root=document.documentElement,body=document.body;
 const read=key=>{try{return localStorage.getItem(key);}catch{return null;}};
 const save=(key,value)=>{try{value==null?localStorage.removeItem(key):localStorage.setItem(key,String(value));}catch{}};
 const number=key=>{const n=Number(read(key));return Number.isFinite(n)&&n>0?n:null;};
 const panels=[
  {id:'navigation',panel:document.getElementById('navigation-panel'),prop:'--rail-size',fallback:'--rail-w',min:160,max:320,sign:1},
  {id:'voice',panel:document.getElementById('voice-panel'),prop:'--inspector-size',fallback:'--inspector-w',min:240,max:440,sign:-1},
 ];
 for(const p of panels){p.handle=document.getElementById(p.id+'-resize');p.key='jarviss.width.'+p.id;p.preferred=number(p.key);}
 const clamp=(n,min,max)=>Math.max(min,Math.min(max,n));
 function limits(p){
  const rail=body.classList.contains('navigation-hidden')?0:panels[0].panel.getBoundingClientRect().width;
  return {min:p.min,max:Math.max(p.min,Math.min(p.max,innerWidth-(p.id==='navigation'?600:rail+440)))};
 }
 function sync(){
  for(const p of panels){
   const {min,max}=limits(p),fallback=parseFloat(getComputedStyle(root).getPropertyValue(p.fallback));
   const width=clamp(p.preferred??fallback,min,max);
   root.style.setProperty(p.prop,width+'px');
   for(const [key,value] of Object.entries({valuemin:min,valuemax:max,valuenow:width,valuetext:Math.round(width)+' pixels'}))p.handle.setAttribute('aria-'+key,String(value));
  }
  requestAnimationFrame(()=>window.offlineAtlas?.resize());
 }
 const toggle=document.getElementById('navigation-toggle');
 function navigation(hidden){
  body.classList.toggle('navigation-hidden',hidden);toggle.setAttribute('aria-expanded',String(!hidden));
  toggle.title=hidden?'Show navigation sidebar':'Hide navigation sidebar';toggle.setAttribute('aria-label',toggle.title);
  save('jarviss.navigation',hidden?'hidden':'shown');sync();
 }
 toggle.onclick=()=>navigation(!body.classList.contains('navigation-hidden'));
 navigation(read('jarviss.navigation')==='hidden');
 for(const p of panels){
  let drag=null;
  const set=width=>{const {min,max}=limits(p);p.preferred=clamp(width,min,max);sync();};
  const finish=cancel=>{
   if(!drag)return;
   const {pointer,preferred}=drag;drag=null;
   if(cancel){p.preferred=preferred;sync();}else save(p.key,p.preferred);
   body.classList.remove('resizing-sidebar');
   if(p.handle.hasPointerCapture(pointer))p.handle.releasePointerCapture(pointer);
  };
  p.handle.onpointerdown=e=>{
   if(e.button!==0)return;e.preventDefault();p.handle.focus();
   drag={pointer:e.pointerId,x:e.clientX,width:p.panel.getBoundingClientRect().width,preferred:p.preferred};
   p.handle.setPointerCapture(e.pointerId);body.classList.add('resizing-sidebar');
  };
  p.handle.onpointermove=e=>{if(drag)set(drag.width+(e.clientX-drag.x)*p.sign);};
  p.handle.onpointerup=()=>finish(false);p.handle.onpointercancel=()=>finish(true);
  p.handle.onlostpointercapture=()=>finish(true);
  p.handle.ondblclick=()=>{p.preferred=null;save(p.key,null);sync();};
  p.handle.onkeydown=e=>{
   if(e.key==='Escape'&&drag){e.preventDefault();finish(true);return;}
   if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();
   const {min,max}=limits(p),width=p.panel.getBoundingClientRect().width;
   set(e.key==='Home'?min:e.key==='End'?max:width+(e.key==='ArrowRight'?1:-1)*p.sign*(e.shiftKey?40:10));save(p.key,p.preferred);
  };
 }
 window.syncSidebars=sync;
 window.addEventListener('resize',sync);
})();
