"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage } from "./api";
import type { CallSession, ExtractResponse, Outcomes, SubmitResponse } from "./call-types";

export const RECOMPUTE_DEBOUNCE_MS = 300;

export function fetchCallSession(customerId: string, outcomes: Outcomes, signal?: AbortSignal): Promise<CallSession> {
  return api<CallSession>("/call/session", {
    method: "POST",
    body: JSON.stringify({ customer_id: customerId, outcomes }),
    signal,
  });
}

export function extractFromNote(customerId: string, note: string): Promise<ExtractResponse> {
  return api<ExtractResponse>("/call/extract", { method: "POST", body: JSON.stringify({ customer_id: customerId, note }) });
}

export function submitCall(customerId: string, outcomes: Outcomes, note: string): Promise<SubmitResponse> {
  return api<SubmitResponse>("/call/submit", { method: "POST", body: JSON.stringify({ customer_id: customerId, outcomes, note }) });
}

export interface CallSessionState {
  data: CallSession | null;
  /** the request body (serialised outcomes) that produced `data` */
  requested: string | null;
  error: string | null;
  /** true while a recompute is in flight; `data` keeps the previous result meanwhile */
  loading: boolean;
  retry: () => void;
}

/**
 * Recomputes the call session whenever the outcomes change. The first request goes out
 * immediately; later ones are debounced and any in-flight request is aborted, so only the
 * latest outcomes ever land on screen.
 */
export function useCallSession(customerId: string, outcomes: Outcomes): CallSessionState {
  const [data, setData] = useState<CallSession | null>(null);
  const [requested, setRequested] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const loaded = useRef(false);
  const body = JSON.stringify(outcomes);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    const timer = window.setTimeout(
      () => {
        fetchCallSession(customerId, JSON.parse(body) as Outcomes, controller.signal)
          .then((result) => {
            if (controller.signal.aborted) return;
            loaded.current = true;
            setData(result);
            setRequested(body);
            setError(null);
            setLoading(false);
          })
          .catch((err: unknown) => {
            if (controller.signal.aborted) return;
            setError(errorMessage(err));
            setLoading(false);
          });
      },
      loaded.current ? RECOMPUTE_DEBOUNCE_MS : 0,
    );
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [customerId, body, attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  return { data, requested, error, loading, retry };
}
