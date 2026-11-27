import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";

/** Calls open() once when the page is loaded with ?new=1 (from a floating + button elsewhere), then removes the flag. */
export function useOpenNew(open: () => void) {
  const [params, setParams] = useSearchParams();
  useEffect(() => {
    if (params.get("new") !== "1") return;
    open();
    const next = new URLSearchParams(params);
    next.delete("new");
    setParams(next, { replace: true });
    // Runs on mount and when the flag changes; open() is a state setter, so it's stable enough here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.get("new")]);
}
