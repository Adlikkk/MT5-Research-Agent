import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, pingHealth, type ApiErrorKind } from "./api/client";
import type { Job } from "./api/types";

export interface AsyncState<T> {
  data: T | null;
  error: string | null;
  errorKind: ApiErrorKind | null;
  loading: boolean;
  reload: () => void;
}

// Small data-fetching hook. The deps array controls when the loader re-runs.
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorKind, setErrorKind] = useState<ApiErrorKind | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);

  const reload = useCallback(() => setTick((value) => value + 1), []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    setErrorKind(null);
    loader()
      .then((result) => {
        if (active) {
          setData(result);
        }
      })
      .catch((err: unknown) => {
        if (active) {
          setError(err instanceof Error ? err.message : String(err));
          setErrorKind(err instanceof ApiError ? err.kind : "http");
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  return { data, error, errorKind, loading, reload };
}

export type BackendState = "connecting" | "online" | "offline";

// Polls /health so the shell can show a live API status pill and so screens can
// distinguish "backend still starting" from a genuine failure.
export function useBackendStatus(intervalMs = 2000): { state: BackendState; recheck: () => void } {
  const [state, setState] = useState<BackendState>("connecting");
  const seen = useRef(false);

  const check = useCallback(() => {
    pingHealth().then((ok) => {
      if (ok) {
        seen.current = true;
        setState("online");
      } else {
        // Before the first successful contact we are "connecting" (backend is
        // likely still booting); after that, a failure means it went offline.
        setState(seen.current ? "offline" : "connecting");
      }
    });
  }, []);

  useEffect(() => {
    check();
    const id = window.setInterval(check, intervalMs);
    return () => window.clearInterval(id);
  }, [check, intervalMs]);

  return { state, recheck: check };
}

const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);

// Poll the whole job list on an interval so the queue + inspector stay live
// while long MT5 jobs run, without ever blocking the UI thread.
export function useJobPolling(intervalMs = 1500): { jobs: Job[]; reload: () => void } {
  const [jobs, setJobs] = useState<Job[]>([]);
  const timer = useRef<number | null>(null);

  const load = useCallback(() => {
    api
      .jobs()
      .then((res) => setJobs(res.jobs))
      .catch(() => {
        /* API may be offline; keep last known jobs */
      });
  }, []);

  useEffect(() => {
    load();
    timer.current = window.setInterval(load, intervalMs);
    return () => {
      if (timer.current !== null) {
        window.clearInterval(timer.current);
      }
    };
  }, [load, intervalMs]);

  return { jobs, reload: load };
}

export function isJobActive(job: Job | null | undefined): boolean {
  return !!job && !TERMINAL.has(job.status);
}
