/**
 * Shared singleton animation ticker.
 *
 * All spinner components subscribe to this single setInterval instead of
 * maintaining their own. Because every subscriber's setState call happens
 * synchronously within the same interval callback, React 18 automatically
 * batches them into one reconcile pass → one Ink terminal render per tick,
 * eliminating the rapid successive redraws that cause the shortcuts-bar flash.
 */

const TICK_INTERVAL_MS = 100; // 10 fps — smooth enough, minimal redraw cost

const subscribers = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | null = null;

function ensureTimer(): void {
    if (timer !== null) return;
    timer = setInterval(() => {
        subscribers.forEach(fn => fn());
    }, TICK_INTERVAL_MS);
}

function maybeStopTimer(): void {
    if (subscribers.size > 0 || timer === null) return;
    clearInterval(timer);
    timer = null;
}

/**
 * Register a callback that will be called on every animation tick.
 * Returns an unsubscribe function suitable for use as a useEffect cleanup.
 */
export function registerAnimationSubscriber(fn: () => void): () => void {
    subscribers.add(fn);
    ensureTimer();
    return () => {
        subscribers.delete(fn);
        maybeStopTimer();
    };
}
