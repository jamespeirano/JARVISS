/* Voice orb: a calm dial in the accent palette. It draws one static frame when idle and
   animates only while listening, thinking or speaking; reduced motion keeps it static. */
(() => {
  const host = document.getElementById('orb');
  host.replaceChildren();
  const canvas = document.createElement('canvas');
  canvas.setAttribute('role', 'img');
  canvas.setAttribute('aria-label', 'JARVISS voice indicator');
  host.append(canvas);
  const ctx = canvas.getContext('2d');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const UNITS = 360; // logical drawing size; CSS shows it at 128px while idle (112px in short windows) and 160px while the voice is busy
  let phase = 0, last = 0, frame = 0, system = 'idle', voice = 'idle', palette = null;
  const compact = () => host.clientWidth < 104; // below ~104px the fine tick ring and the wordmark would only blur

  // Colours come from the stylesheet tokens so the orb never carries its own palette.
  function token(name) {
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    const n = parseInt(value.slice(1), 16);
    return value.length === 7 && !Number.isNaN(n) ? [n >> 16 & 255, n >> 8 & 255, n & 255] : [200, 200, 200];
  }
  function readPalette() {
    const accent = token('--accent'), strong = token('--accent-strong'), surface = token('--bg-2'), deep = token('--bg-0'), fg = token('--fg-1');
    const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
    palette = { accent: a => rgba(accent, a), strong: a => rgba(strong, a), surface: a => rgba(surface, a), deep: a => rgba(deep, a), fg: a => rgba(fg, a) };
  }
  const mode = () => system === 'thinking' ? 'thinking' : voice;
  const animated = () => mode() !== 'idle' && !reduced.matches;
  const visible = () => !document.hidden && host.clientWidth > 0 && !!host.closest('.page')?.classList.contains('visible');

  function ring(radius, width, color, start = 0, extent = Math.PI * 2) {
    ctx.beginPath(); ctx.arc(0, 0, radius, start, start + extent);
    ctx.lineWidth = width; ctx.strokeStyle = color; ctx.stroke();
  }
  function ticks(radius, count, length, width, color, rotation = 0) {
    ctx.save(); ctx.rotate(rotation); ctx.strokeStyle = color; ctx.lineWidth = width; ctx.beginPath();
    for (let i = 0; i < count; i++) {
      const a = i * Math.PI * 2 / count;
      ctx.moveTo(Math.cos(a) * radius, Math.sin(a) * radius);
      ctx.lineTo(Math.cos(a) * (radius + length), Math.sin(a) * (radius + length));
    }
    ctx.stroke(); ctx.restore();
  }
  function render() {
    if (!palette) readPalette();
    if (!canvas.width) return;
    const p = palette, m = mode();
    const pulse = animated() ? (Math.sin(phase * 3) + 1) / 2 : 0;
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, canvas.width, canvas.height);
    const k = canvas.width / UNITS; ctx.setTransform(k, 0, 0, k, canvas.width / 2, canvas.height / 2);
    const haze = ctx.createRadialGradient(0, 0, 40, 0, 0, 172);
    haze.addColorStop(0, p.accent(.12 + pulse * .06)); haze.addColorStop(.7, p.accent(.03)); haze.addColorStop(1, p.accent(0));
    ctx.fillStyle = haze; ctx.beginPath(); ctx.arc(0, 0, 172, 0, Math.PI * 2); ctx.fill();
    ring(168, 1, p.accent(.35)); ring(158, 1, p.accent(.18));
    if (!compact()) ticks(160, 72, 5, 1, p.accent(.35), phase * .05);
    ticks(160, 12, 9, 1.5, p.accent(.6), phase * .05);
    const arcs = m === 'thinking' ? 3 : m === 'listening' ? 2 : m === 'speaking' ? 4 : 0;
    for (let i = 0; i < arcs; i++) ring(146, 3, p.strong(.85), i * Math.PI * 2 / arcs + phase * .6, .5);
    ring(146, 1, p.accent(m === 'idle' ? .3 : .5));
    ring(128, 6, p.deep(.9)); ring(128, 1.5, p.accent(.55));
    if (!compact()) ticks(120, 36, 3, 1, p.accent(.3), -phase * .08);
    const core = ctx.createRadialGradient(0, 0, 10, 0, 0, 112);
    core.addColorStop(0, p.surface(1)); core.addColorStop(.85, p.deep(1)); core.addColorStop(1, p.accent(.35));
    ctx.fillStyle = core; ctx.beginPath(); ctx.arc(0, 0, 112, 0, Math.PI * 2); ctx.fill();
    ring(112, 1.5, p.accent(.5 + pulse * .4));
    if (m === 'speaking') {
      for (let i = 0; i < 21; i++) {
        const h = animated() ? 4 + Math.abs(Math.sin(phase * 6 + i * .7)) * 22 : 10;
        ctx.fillStyle = p.strong(.9); ctx.fillRect(-52 + i * 5, 44 - h / 2, 2.5, h);
      }
    } else if (m === 'listening') { ctx.fillStyle = p.strong(.7); ctx.fillRect(-40, 43, 80, 2); }
    if (!compact()) {
      ctx.fillStyle = p.fg(1); ctx.font = '600 30px "Segoe UI Variable Text","Segoe UI",system-ui,sans-serif';
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.letterSpacing = '4px';
      ctx.fillText('JARVISS', 2, -2);
    }
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
