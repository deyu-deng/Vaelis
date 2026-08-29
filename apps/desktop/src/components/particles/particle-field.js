import { jsx as _jsx } from "react/jsx-runtime";
import './particle-field.css';
import { useEffect, useMemo, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
const rand = ([min, max]) => min + Math.random() * (max - min);
/** Sample a range along `t` (0→min, 1→max) — couples travel/lifetime to `life`. */
const lerp = ([min, max], t) => min + (max - min) * t;
export const DEFAULT_PARTICLE_CONFIG = {
    count: 12,
    spawnWindowMs: 550,
    size: [6, 13],
    rise: [6.75, 15.75],
    duration: [320, 700],
    swayAmp: [9, 24],
    bank: [7, 16],
    swayDuration: [1300, 2800],
    maxAlive: 200
};
/** Create an emitter handle. `burst()` is safe to call from anywhere. */
export function createParticleEmitter() {
    const listeners = new Set();
    return {
        burst: count => listeners.forEach(fn => fn(count)),
        subscribe: fn => {
            listeners.add(fn);
            return () => void listeners.delete(fn);
        }
    };
}
let nextId = 1;
function spawn(cfg, colors) {
    // Short-lived particles fade out lower; a few live longer and rise higher.
    const life = Math.random() ** 1.7;
    const swayDurationMs = Math.round(rand(cfg.swayDuration));
    return {
        id: nextId++,
        // Spread edge to edge across the lane, not clustered near center.
        leftPct: 4 + Math.random() * 92,
        size: rand(cfg.size),
        color: colors[Math.floor(Math.random() * colors.length)],
        delayMs: Math.round(Math.random() * 120),
        durationMs: Math.round(lerp(cfg.duration, life)),
        rise: lerp(cfg.rise, life),
        swayAmp: rand(cfg.swayAmp),
        bank: rand(cfg.bank),
        swayDurationMs,
        // Negative delay drops each particle in mid-swing (desynced phases).
        swayDelayMs: -Math.round(Math.random() * swayDurationMs)
    };
}
const prefersReducedMotion = () => typeof window !== 'undefined' && Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
export function ParticleField({ emitter, glyph, colors, config, className, style }) {
    const cfg = useMemo(() => ({ ...DEFAULT_PARTICLE_CONFIG, ...config }), [config]);
    const [particles, setParticles] = useState([]);
    const timers = useRef(new Set());
    useEffect(() => {
        const pool = timers.current;
        const add = () => setParticles(prev => [...prev, spawn(cfg, colors)].slice(-cfg.maxAlive));
        // Release a burst across a tight window so it reads as one poof, each node
        // with its own random birth time; reduced motion gets a single flash.
        const onBurst = (count) => {
            const n = Math.max(1, Math.min(cfg.maxAlive, Math.round(count ?? cfg.count)));
            if (prefersReducedMotion()) {
                add();
                return;
            }
            for (let i = 0; i < n; i++) {
                const timer = setTimeout(() => {
                    pool.delete(timer);
                    add();
                }, Math.random() * cfg.spawnWindowMs);
                pool.add(timer);
            }
        };
        const unsubscribe = emitter.subscribe(onBurst);
        return () => {
            unsubscribe();
            pool.forEach(clearTimeout);
            pool.clear();
        };
    }, [cfg, colors, emitter]);
    const remove = (id) => setParticles(prev => prev.filter(p => p.id !== id));
    if (particles.length === 0) {
        return null;
    }
    return (_jsx("div", { "aria-hidden": true, className: cn('particle-field', className), style: style, children: particles.map(p => (_jsx("span", { className: "particle", 
            // Retire on the RISE track only (sway is infinite, pop is shorter).
            onAnimationEnd: e => {
                if (e.animationName === 'particle-rise' || e.animationName === 'particle-flash') {
                    remove(p.id);
                }
            }, style: {
                '--particle-left': `${p.leftPct}%`,
                '--particle-size': `${p.size}px`,
                '--particle-color': p.color,
                '--particle-delay': `${p.delayMs}ms`,
                '--particle-duration': `${p.durationMs}ms`,
                '--particle-rise': p.rise,
                '--particle-sway': `${p.swayAmp}px`,
                '--particle-bank': `${p.bank}deg`,
                '--particle-sway-duration': `${p.swayDurationMs}ms`,
                '--particle-sway-delay': `${p.swayDelayMs}ms`
            }, children: _jsx("span", { className: "particle__sway", children: _jsx("span", { className: "particle__glyph", children: glyph }) }) }, p.id))) }));
}
