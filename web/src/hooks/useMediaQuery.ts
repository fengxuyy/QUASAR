import { useEffect, useState } from 'react';

/**
 * Subscribe to a CSS media query. Returns false until mounted to avoid SSR mismatches.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return;
    }
    const media = window.matchMedia(query);
    const update = () => setMatches(media.matches);
    update();
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, [query]);

  return matches;
}

/** App chrome breakpoint — matches Tailwind `md` (768px). */
export function useIsMobileLayout(): boolean {
  return useMediaQuery('(max-width: 767.98px)');
}

/** True when the primary input is touch / no hover (phones, many tablets). */
export function useIsCoarsePointer(): boolean {
  return useMediaQuery('(hover: none), (pointer: coarse)');
}
