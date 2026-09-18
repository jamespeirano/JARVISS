/* Original blue JARVIS HUD, with idle and reduced-motion rendering kept static. */
(() => {
  const host = document.getElementById('orb');
  host.replaceChildren();
  const canvas = document.createElement('canvas');
  canvas.setAttribute('role', 'img');
  canvas.setAttribute('aria-label', 'JARVISS voice indicator');
  host.append(canvas);
  const ctx = canvas.getContext('2d');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let phase = 0, last = 0, frame = 0, system = 'idle', voice = 'idle';
  const mode = () => system === 'thinking' ? 'thinking' : voice;
  const animated = () => mode() !== 'idle' && !reduced.matches;
  const visible = () => !document.hidden && host.clientWidth > 0 && !!host.closest('.page')?.classList.contains('visible');
  function ring(radius, width, color, start=0, extent=Math.PI*2, glow=0) {
    ctx.beginPath(); ctx.arc(0, 0, radius, start, start+extent);
    ctx.lineWidth=width; ctx.strokeStyle=color; ctx.shadowColor=color; ctx.shadowBlur=glow;
    ctx.stroke(); ctx.shadowBlur=0;
  }
  function marks(radius, count, length, width, color, rotation=0, skip=0) {
    ctx.save(); ctx.rotate(rotation); ctx.strokeStyle=color;ctx.lineWidth=width;
    ctx.beginPath();
    for(let i=0;i<count;i++) {
      if(skip && i%skip===0)continue;
      const a=i*Math.PI*2/count;
      ctx.moveTo(Math.cos(a)*radius,Math.sin(a)*radius);
      ctx.lineTo(Math.cos(a)*(radius+length),Math.sin(a)*(radius+length));
    }
    ctx.stroke();ctx.restore();
  }
  function flare(a, radius, strength) {
    ctx.save();ctx.rotate(a);ctx.translate(radius,0);
    const glow=ctx.createRadialGradient(0,0,0,0,0,23);
    glow.addColorStop(0,`rgba(225,255,255,${strength})`);
    glow.addColorStop(.15,`rgba(65,213,255,${strength*.8})`);
    glow.addColorStop(1,'rgba(0,110,255,0)');
    ctx.fillStyle=glow;ctx.fillRect(-24,-24,48,48);
    ctx.fillStyle=`rgba(203,250,255,${strength})`;ctx.fillRect(-13,-.6,26,1.2);
    ctx.restore();
  }
  function render() {
    if (!canvas.width) return;
    const mode = host.dataset.state || 'idle';
    const pulse = reduced.matches || mode === 'idle' ? 0 : (Math.sin(phase * 4) + 1) / 2;
    ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,canvas.width,canvas.height);
    ctx.setTransform(canvas.width/480,0,0,canvas.height/480,canvas.width/2,canvas.height/2);
    const haze=ctx.createRadialGradient(0,0,55,0,0,238);
    haze.addColorStop(0,'#021129');haze.addColorStop(.6,'#031b32');haze.addColorStop(.84,'#001126');haze.addColorStop(1,'rgba(0,8,22,0)');
    ctx.fillStyle=haze;ctx.beginPath();ctx.arc(0,0,238,0,Math.PI*2);ctx.fill();
    ring(226,1,'#244c6a');ring(223,2,'#22658a');ring(219,1,'#143149');
    ring(208,1,'#2b7394');ring(203,1,'#102c4b');ring(196,1.5,'#276c91');
    marks(213,120,2,1,'#3c7c9b',phase*.08);
    marks(184,90,2,1,'#27657f',-phase*.13);
    for(let i=0;i<8;i++){
      const a=i*Math.PI/4+phase*.15;
      ring(221,3,'#64ddff',a,.12,8);ring(219,6,'#1d7198',a+.13,.23,3);
      ring(199,3,'#3184ae',-a,.28);ring(199,1,'#a6f8ff',-a,.11,5);
    }
    ring(173,1,'#307696');ring(169,3,'#154c6d');ring(165,1,'#88eaff',0,Math.PI*2,5);
    for(let i=0;i<4;i++){
      const a=i*Math.PI/2-phase*.27;
      ring(179,6,'#16638c',a,.42);ring(179,2,'#9ef7ff',a+.05,.25,7);
    }
    marks(153,144,7,1.3,'#57bcd9',phase*.11);
    marks(143,72,3,1,'#327f9e',-phase*.16);
    // Rotating outlined telemetry cells, matching the reference's inner band.
    ctx.save();ctx.rotate(-phase*.18);
    for(let i=0;i<56;i++){
      ctx.save();ctx.rotate(i*Math.PI*2/56);ctx.strokeStyle=i%7===0?'#a6edff':'#3c839f';ctx.lineWidth=.9;
      ctx.strokeRect(128,-3.4,7,6.8);ctx.restore();
    }ctx.restore();
    ring(121,1,'#2c607d');ring(114,7,'#0a355b');
    ring(113,2.7,'#6ef0ff',0,Math.PI*2,12+pulse*4);
    ring(109,1,'#e0ffff',0,Math.PI*2,5);
    ring(105,1,'#296b92');
    for(let i=0;i<3;i++)ring(117,2,'#c2ffff',phase*.5+i*Math.PI*2/3,.4,8);
    const core=ctx.createRadialGradient(0,0,15,0,0,105);
    core.addColorStop(0,'#03142e');core.addColorStop(.8,'#021127');core.addColorStop(1,'#07334c');
    ctx.fillStyle=core;ctx.beginPath();ctx.arc(0,0,103,0,Math.PI*2);ctx.fill();
    // Deterministic points: no random flashing and no invented live telemetry.
    for(let i=0;i<45;i++){
      const a=i*2.399963,r=20+(i*37)%78;
      ctx.fillStyle=`rgba(81,174,218,${.12+(i%4)*.055})`;
      ctx.fillRect(Math.cos(a)*r,Math.sin(a)*r,1,1);
    }
    if(mode==='speaking'){
      for(let i=0;i<25;i++){
        const h=reduced.matches?5:3+Math.abs(Math.sin(phase*7+i*.6))*8;
        ctx.fillStyle='#68e6ff';ctx.fillRect(-48+i*4,48-h/2,1.5,h);
      }
    }
    ctx.fillStyle='#efffff';ctx.shadowColor='#5ddfff';ctx.shadowBlur=13;
    ctx.font='600 36px "Segoe UI", "Helvetica Neue", sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';
    ctx.fillText('J A R V I S',0,0);ctx.shadowBlur=0;
    ctx.fillStyle='#649aad';ctx.font='500 10px "Segoe UI", "Helvetica Neue", sans-serif';
    ctx.fillText('S U R V I V A L',0,29);
    ctx.strokeStyle='#386878';ctx.lineWidth=.7;
    ctx.beginPath();ctx.moveTo(-51,29);ctx.lineTo(-64,29);ctx.moveTo(51,29);ctx.lineTo(64,29);ctx.stroke();
    for(let i=0;i<4;i++)flare(i*Math.PI/2+phase*.07,222,.7+pulse*.25);
    flare(-phase*.27,177,.7);
  }
  function tick(now) {
    frame = 0;
    if (!animated() || !visible()) { render(); return; }
    if (now - last < 32) { frame = requestAnimationFrame(tick); return; } // ~30 fps is plenty for a dial
    const dt = Math.min((now - last) / 1000, .1); last = now;
    phase += dt * (mode() === 'thinking' ? 1.6 : mode() === 'speaking' ? 1.2 : .7);
    render(); frame = requestAnimationFrame(tick);
  }
  function schedule() {
    if (frame) { cancelAnimationFrame(frame); frame = 0; }
    if (animated() && visible()) { last = performance.now(); frame = requestAnimationFrame(tick); }
    else render();
  }
  function resize() {
    const side = host.clientWidth; if (!side) return;
    const px = Math.round(side * Math.min(devicePixelRatio, 2));
    if (canvas.width !== px) { canvas.width = px; canvas.height = px; }
    schedule();
  }
  window.jarvisState = (kind, text) => {
    if (kind === 'status') system = /Thinking|Loading/.test(text) ? 'thinking' : 'idle';
    if (kind === 'voice') voice = /^(Speaking|Preparing speech)$/.test(text) ? 'speaking' : /^(Listening|Starting voice)$/.test(text) ? 'listening' : 'idle';
    if (kind === 'error') { system = 'idle'; voice = 'idle'; }
    host.dataset.state = mode();
    schedule();
  };
  new ResizeObserver(resize).observe(host);
  new MutationObserver(schedule).observe(host.closest('.page'), { attributes: true, attributeFilter: ['class'] });
  document.addEventListener('visibilitychange', schedule);
  reduced.addEventListener('change', schedule);
  resize();
  window.addEventListener('beforeunload', () => cancelAnimationFrame(frame));
})();
