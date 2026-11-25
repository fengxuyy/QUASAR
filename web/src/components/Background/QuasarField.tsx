import { useEffect, useRef } from 'react';

interface QuasarFieldProps {
  /** Density profile. 'hero' is richer than 'panel'. */
  variant?: 'hero' | 'panel';
  /** Visual palette; matches the portal theme. */
  appearance?: 'light' | 'dark';
  className?: string;
}

/** Soft volumetric light source — large, elliptical, never hard-edged. */
interface Volume {
  x: number; // 0..1 anchor
  y: number;
  rx: number; // radius as fraction of min(w,h)
  ry: number;
  hue: number; // palette index
  phase: number;
  driftX: number; // cycle speed (rad/s scale)
  driftY: number;
  pulse: number;
  amp: number; // position amplitude
}

/** Architectural light plane — slow diagonal wash, not a drawn stroke. */
interface Plane {
  angle: number;
  offset: number;
  width: number; // band width fraction
  speed: number;
  phase: number;
  hue: number;
  alpha: number;
}

/** Sparse dust mote — reads as atmosphere, not particles. */
interface Mote {
  x: number;
  y: number;
  z: number;
  phase: number;
  speed: number;
  size: number;
  hue: number;
}

interface FieldStyle {
  base: string;
  volumes: readonly string[];
  plane: readonly string[];
  moteCore: readonly string[];
  moteGlow: readonly string[];
  sheen: string;
  vignette: string;
  veil: string;
}

const FIELD_STYLES: Record<'light' | 'dark', FieldStyle> = {
  dark: {
    base: 'rgba(5, 8, 18, 1)',
    volumes: [
      'rgba(88, 108, 210, 0.28)',
      'rgba(42, 170, 200, 0.14)',
      'rgba(130, 95, 210, 0.18)',
      'rgba(70, 90, 170, 0.12)',
    ],
    plane: ['88, 108, 210', '42, 170, 200', '130, 95, 210'],
    moteCore: ['220, 228, 255', '200, 240, 250', '235, 220, 255'],
    moteGlow: ['100, 120, 220', '50, 180, 210', '140, 110, 220'],
    sheen: 'rgba(160, 180, 255, 0.045)',
    vignette: 'rgba(2, 4, 12, 0.62)',
    veil: 'rgba(8, 12, 28, 0.22)',
  },
  light: {
    base: 'rgba(245, 247, 255, 1)',
    volumes: [
      'rgba(79, 114, 232, 0.16)',
      'rgba(14, 165, 233, 0.09)',
      'rgba(111, 79, 228, 0.11)',
      'rgba(99, 120, 200, 0.07)',
    ],
    plane: ['79, 114, 232', '8, 145, 178', '111, 79, 228'],
    moteCore: ['255, 255, 255', '240, 248, 255', '250, 246, 255'],
    moteGlow: ['79, 114, 232', '14, 165, 233', '111, 79, 228'],
    sheen: 'rgba(79, 114, 232, 0.04)',
    vignette: 'rgba(235, 238, 252, 0.42)',
    veil: 'rgba(245, 247, 255, 0.12)',
  },
};

/** Rewrite trailing alpha in an `rgba(r,g,b,a)` string. */
function withAlpha(color: string, alpha: number): string {
  return color.replace(/[\d.]+\)$/, `${Math.max(0, Math.min(1, alpha))})`);
}

/** Extract alpha from `rgba(..., a)`. */
function readAlpha(color: string): number {
  const m = color.match(/([\d.]+)\)$/);
  return m ? parseFloat(m[1]) : 0.1;
}

/**
 * Enterprise ambient field.
 *
 * Intentionally not geometry: no orbits, dashed rings, sine ribbons, or
 * particle meshes. Layers of soft volumetric light, slow architectural
 * planes, and sparse atmospheric dust — the language of premium product
 * surfaces (quiet, slow, depth-first).
 */
export function QuasarField({ variant = 'hero', appearance = 'light', className }: QuasarFieldProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d', { alpha: true, desynchronized: true });
    if (!ctx) return;

    const style = FIELD_STYLES[appearance];
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const isHero = variant === 'hero';

    let width = 0;
    let height = 0;
    let dpr = 1;
    let raf = 0;
    let running = false;
    let visible = true;
    let t0 = performance.now();
    let volumes: Volume[] = [];
    let planes: Plane[] = [];
    let motes: Mote[] = [];
    const pointer = { x: 0.5, y: 0.42, sx: 0.5, sy: 0.42, active: false };

    const seed = () => {
      // Large soft luminaires — positions are normalized anchors
      volumes = [
        { x: 0.28, y: 0.32, rx: 0.55, ry: 0.42, hue: 0, phase: 0.4, driftX: 0.07, driftY: 0.05, pulse: 0.18, amp: 0.04 },
        { x: 0.72, y: 0.28, rx: 0.48, ry: 0.38, hue: 2, phase: 1.7, driftX: -0.05, driftY: 0.06, pulse: 0.14, amp: 0.05 },
        { x: 0.55, y: 0.68, rx: 0.52, ry: 0.36, hue: 1, phase: 2.9, driftX: 0.04, driftY: -0.045, pulse: 0.12, amp: 0.035 },
        { x: 0.18, y: 0.72, rx: 0.38, ry: 0.32, hue: 3, phase: 4.1, driftX: -0.035, driftY: -0.03, pulse: 0.1, amp: 0.03 },
        { x: 0.82, y: 0.62, rx: 0.34, ry: 0.4, hue: 0, phase: 5.2, driftX: 0.03, driftY: 0.04, pulse: 0.11, amp: 0.028 },
      ];
      if (!isHero) volumes = volumes.slice(0, 3);

      // Soft light planes (wide diagonal washes)
      planes = [
        { angle: -0.28, offset: 0.18, width: 0.22, speed: 0.018, phase: 0.2, hue: 0, alpha: appearance === 'dark' ? 0.06 : 0.045 },
        { angle: 0.42, offset: 0.55, width: 0.18, speed: -0.012, phase: 1.8, hue: 1, alpha: appearance === 'dark' ? 0.045 : 0.032 },
        { angle: -0.08, offset: 0.78, width: 0.28, speed: 0.01, phase: 3.4, hue: 2, alpha: appearance === 'dark' ? 0.035 : 0.025 },
      ];
      if (!isHero) planes = planes.slice(0, 2);

      // Sparse dust — atmosphere, not a starfield
      const density = isHero ? 42000 : 70000;
      const count = Math.max(12, Math.min(isHero ? 42 : 24, Math.round((width * height) / density)));
      motes = Array.from({ length: count }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        z: Math.random(),
        phase: Math.random() * Math.PI * 2,
        speed: 0.12 + Math.random() * 0.28,
        size: 0.5 + Math.random() * 1.4,
        hue: Math.random() < 0.15 ? 2 : Math.random() < 0.4 ? 1 : 0,
      }));
    };

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = rect.width;
      height = rect.height;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      seed();
      if (reducedMotion) draw(0);
    };

    /** Soft elliptical volume of light. */
    const drawVolumes = (time: number, ox: number, oy: number) => {
      const t = time * 0.001;
      const minDim = Math.min(width, height);

      for (const v of volumes) {
        const breath = 1 + Math.sin(t * v.pulse + v.phase) * 0.06;
        const dx = Math.sin(t * v.driftX + v.phase) * v.amp * width;
        const dy = Math.cos(t * v.driftY + v.phase * 0.7) * v.amp * height;
        const cx = v.x * width + dx + ox * (0.35 + v.hue * 0.05);
        const cy = v.y * height + dy + oy * (0.35 + v.hue * 0.05);
        const rx = v.rx * minDim * breath;
        const ry = v.ry * minDim * breath;

        ctx.save();
        ctx.translate(cx, cy);
        ctx.scale(1, ry / Math.max(rx, 1));
        const g = ctx.createRadialGradient(0, 0, 0, 0, 0, rx);
        const c = style.volumes[v.hue % style.volumes.length];
        const a0 = readAlpha(c);
        g.addColorStop(0, c);
        g.addColorStop(0.35, withAlpha(c, a0 * 0.45));
        g.addColorStop(0.7, withAlpha(c, a0 * 0.12));
        g.addColorStop(1, 'transparent');
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(0, 0, rx, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      }
    };

    /**
     * Wide soft light planes — painted as rotated linear gradients,
     * not stroked geometry. Reads as architectural light, not lines.
     */
    const drawPlanes = (time: number, ox: number, oy: number) => {
      const t = time * 0.001;
      const span = Math.max(width, height);
      for (const p of planes) {
        const travel = Math.sin(t * p.speed + p.phase) * 0.14;
        // Center-relative band position so rotation feels intentional
        const mid = (p.offset + travel - 0.5) * span * 1.1;
        const band = p.width * Math.min(width, height);

        ctx.save();
        ctx.translate(width * 0.5 + ox * 0.2, height * 0.5 + oy * 0.2);
        ctx.rotate(p.angle);

        const half = span * 1.25;
        const g = ctx.createLinearGradient(0, mid - band, 0, mid + band);
        const rgb = style.plane[p.hue % style.plane.length];
        g.addColorStop(0, 'transparent');
        g.addColorStop(0.32, `rgba(${rgb}, ${p.alpha * 0.3})`);
        g.addColorStop(0.5, `rgba(${rgb}, ${p.alpha})`);
        g.addColorStop(0.68, `rgba(${rgb}, ${p.alpha * 0.3})`);
        g.addColorStop(1, 'transparent');
        ctx.fillStyle = g;
        ctx.fillRect(-half, -half, half * 2, half * 2);
        ctx.restore();
      }
    };

    /** Slow horizontal luminance sheen — product-page horizon light. */
    const drawSheen = (time: number, ox: number, oy: number) => {
      const y = height * (0.38 + 0.03 * Math.sin(time * 0.00022)) + oy * 0.15;
      const h = height * 0.55;
      const a = readAlpha(style.sheen);
      const g = ctx.createLinearGradient(0, y - h * 0.5, 0, y + h * 0.5);
      g.addColorStop(0, 'transparent');
      g.addColorStop(0.4, style.sheen);
      g.addColorStop(0.55, withAlpha(style.sheen, Math.min(1, a * 1.6)));
      g.addColorStop(0.7, style.sheen);
      g.addColorStop(1, 'transparent');
      ctx.fillStyle = g;
      ctx.fillRect(0, y - h * 0.5, width, h);

      // Soft secondary highlight, slightly offset
      const y2 = height * (0.62 + 0.02 * Math.cos(time * 0.00018)) + oy * 0.1;
      const g2 = ctx.createLinearGradient(ox * 0.3, y2 - 30, ox * 0.3, y2 + 50);
      g2.addColorStop(0, 'transparent');
      g2.addColorStop(0.5, style.sheen);
      g2.addColorStop(1, 'transparent');
      ctx.fillStyle = g2;
      ctx.fillRect(0, y2 - 30, width, 80);
    };

    /** Extremely restrained atmospheric dust. */
    const drawMotes = (time: number, ox: number, oy: number) => {
      for (const m of motes) {
        const depth = 0.3 + m.z * 0.7;
        const breath = 0.55 + 0.45 * Math.sin(m.phase + time * 0.00045 * m.speed);
        const px = m.x + ox * (0.12 + m.z * 0.4);
        const py = m.y + oy * (0.12 + m.z * 0.4);
        const r = m.size * depth * (0.7 + breath * 0.35);

        // Soft halo only — no hard core dots
        const glowR = r * (appearance === 'dark' ? 9 : 11);
        const glow = ctx.createRadialGradient(px, py, 0, px, py, glowR);
        const ga = (appearance === 'dark' ? 0.14 : 0.09) * breath * depth;
        glow.addColorStop(0, `rgba(${style.moteGlow[m.hue]}, ${ga})`);
        glow.addColorStop(0.45, `rgba(${style.moteGlow[m.hue]}, ${ga * 0.25})`);
        glow.addColorStop(1, 'transparent');
        ctx.fillStyle = glow;
        ctx.beginPath();
        ctx.arc(px, py, glowR, 0, Math.PI * 2);
        ctx.fill();

        // Faint core
        const ca = (appearance === 'dark' ? 0.28 : 0.22) * breath * depth;
        ctx.fillStyle = `rgba(${style.moteCore[m.hue]}, ${ca})`;
        ctx.beginPath();
        ctx.arc(px, py, Math.max(0.4, r * 0.35), 0, Math.PI * 2);
        ctx.fill();
      }
    };

    const drawVignette = () => {
      // Corner falloff — keeps UI focus centered
      const g = ctx.createRadialGradient(
        width * 0.5,
        height * 0.42,
        Math.min(width, height) * 0.18,
        width * 0.5,
        height * 0.5,
        Math.max(width, height) * 0.78,
      );
      g.addColorStop(0, 'transparent');
      g.addColorStop(0.65, 'transparent');
      g.addColorStop(1, style.vignette);
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, width, height);

      // Top veil — product chrome often sits under a soft sky wash
      const top = ctx.createLinearGradient(0, 0, 0, height * 0.35);
      top.addColorStop(0, style.veil);
      top.addColorStop(1, 'transparent');
      ctx.fillStyle = top;
      ctx.fillRect(0, 0, width, height * 0.35);
    };

    const draw = (time: number) => {
      // Clean base each frame — no motion-trail smear (reads as cheaper CGI)
      ctx.globalCompositeOperation = 'source-over';
      ctx.fillStyle = style.base;
      ctx.fillRect(0, 0, width, height);

      // Smooth pointer follow
      pointer.sx += (pointer.x - pointer.sx) * 0.025;
      pointer.sy += (pointer.y - pointer.sy) * 0.025;
      const strength = isHero ? 28 : 16;
      const ox = (pointer.sx - 0.5) * strength;
      const oy = (pointer.sy - 0.5) * (strength * 0.65);

      drawVolumes(time, ox, oy);
      drawPlanes(time, ox, oy);
      drawSheen(time, ox, oy);
      drawMotes(time, ox, oy);
      drawVignette();
    };

    const step = (now: number) => {
      const time = now - t0;
      const dt = 0.85; // calm drift

      for (const m of motes) {
        // Very slow laminar drift — no swirl mesh
        const u = Math.sin(m.y * 0.004 + time * 0.00012) * 0.35;
        const v = Math.cos(m.x * 0.0035 - time * 0.00009) * 0.22;
        m.x += u * m.speed * dt * (0.4 + m.z * 0.6);
        m.y += v * m.speed * dt * (0.4 + m.z * 0.6);
        m.phase += 0.004 * m.speed;

        if (pointer.active) {
          const px = pointer.sx * width;
          const py = pointer.sy * height;
          const dx = m.x - px;
          const dy = m.y - py;
          const distSq = dx * dx + dy * dy;
          const R = 220;
          if (distSq < R * R && distSq > 16) {
            const dist = Math.sqrt(distSq);
            // Gentle parallax push, not orbit/repulsion theater
            const force = ((R - dist) / R) * 0.12 * m.z;
            m.x += (dx / dist) * force;
            m.y += (dy / dist) * force;
          }
        }

        if (m.x < -20) m.x = width + 20;
        if (m.x > width + 20) m.x = -20;
        if (m.y < -20) m.y = height + 20;
        if (m.y > height + 20) m.y = -20;
      }

      draw(time);
      raf = requestAnimationFrame(step);
    };

    const start = () => {
      if (running || reducedMotion || !visible || document.hidden) return;
      running = true;
      t0 = performance.now();
      raf = requestAnimationFrame(step);
    };

    const stop = () => {
      running = false;
      cancelAnimationFrame(raf);
    };

    const handlePointerMove = (event: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      pointer.x = (event.clientX - rect.left) / rect.width;
      pointer.y = (event.clientY - rect.top) / rect.height;
      pointer.active = true;
    };

    const handlePointerLeave = () => {
      pointer.active = false;
      pointer.x = 0.5;
      pointer.y = 0.42;
    };

    const handleVisibility = () => {
      if (document.hidden) stop();
      else start();
    };

    const observer = new IntersectionObserver(entries => {
      visible = entries[0]?.isIntersecting ?? true;
      if (visible) start();
      else stop();
    });
    observer.observe(canvas);

    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(canvas);

    resize();
    start();

    window.addEventListener('pointermove', handlePointerMove, { passive: true });
    window.addEventListener('pointerleave', handlePointerLeave);
    document.addEventListener('visibilitychange', handleVisibility);

    return () => {
      stop();
      observer.disconnect();
      resizeObserver.disconnect();
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerleave', handlePointerLeave);
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [variant, appearance]);

  return <canvas ref={canvasRef} aria-hidden="true" className={className} />;
}
