import { useEffect, useRef, useState } from "react";

const THRESHOLD = 70; // px of pull, from the top of the page, before a refresh starts

/**
 * Pull down from the top of the page to refresh. Touch screens only; other devices are unaffected.
 * Returns "refreshing" while onRefresh runs, so the page can show it.
 */
export function usePullToRefresh(onRefresh: () => Promise<void> | void): "idle" | "refreshing" {
  const [state, setState] = useState<"idle" | "refreshing">("idle");
  const refresh = useRef(onRefresh);
  refresh.current = onRefresh;

  useEffect(() => {
    let startY: number | null = null;
    let pulled = 0;
    const onStart = (e: TouchEvent) => {
      startY = window.scrollY === 0 && e.touches.length === 1 ? e.touches[0].clientY : null;
      pulled = 0;
    };
    const onMove = (e: TouchEvent) => {
      if (startY !== null) pulled = e.touches[0].clientY - startY;
    };
    const onEnd = async () => {
      const shouldRefresh = startY !== null && pulled > THRESHOLD;
      startY = null;
      pulled = 0;
      if (!shouldRefresh) return;
      setState("refreshing");
      try {
        await refresh.current();
      } finally {
        setState("idle");
      }
    };
    window.addEventListener("touchstart", onStart, { passive: true });
    window.addEventListener("touchmove", onMove, { passive: true });
    window.addEventListener("touchend", onEnd);
    return () => {
      window.removeEventListener("touchstart", onStart);
      window.removeEventListener("touchmove", onMove);
      window.removeEventListener("touchend", onEnd);
    };
  }, []);

  return state;
}
