import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { useData } from "./data";
import { readRemembered, remember, withPendingForMonth } from "./month";
import type { DashboardSummary } from "./types";

/**
 * The dashboard's figures for one month. The month is the one picked this session, or the
 * server's default (this month, or the latest month with data when this month is empty).
 */
export function useDashboardMonth() {
  const { summary, pendingOps } = useData();
  const [chosen, setChosen] = useState<string | null>(() => readRemembered());
  const [data, setData] = useState<DashboardSummary | null>(null);

  useEffect(() => {
    let live = true;
    const path = chosen ? `/api/dashboard?month=${chosen}` : "/api/dashboard";
    api.get<DashboardSummary>(path)
      .then((res) => { if (live) setData(res); })
      .catch(() => { /* offline or refused: keep what is shown */ });
    return () => { live = false; };
  }, [chosen, summary]);

  const setMonth = useCallback((ym: string) => {
    remember(ym);
    setChosen(ym);
  }, []);

  return {
    summary: data ? withPendingForMonth(data, pendingOps, data.selected_month) : null,
    selected: data?.selected_month ?? chosen,
    current: data?.current_month ?? null,
    months: data?.months_with_data ?? [],
    notice: data?.notice ?? null,
    setMonth,
  };
}
