"use client";

import { useCallback, useEffect, useState } from "react";
import { api, reason, type ModelStatus } from "@/app/api/client";

/** The model's live status, plus the one write the user can make: paste a key. */
export function useModel() {
  const [status, setStatus] = useState<ModelStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api
      .getModel()
      .then((found) => {
        setStatus(found);
        setError(null);
      })
      .catch((failure) => setError(reason(failure)));
  }, []);

  useEffect(() => void refresh(), [refresh]);

  const connect = useCallback((apiKey: string): Promise<boolean> => {
    return api
      .setModelKey(apiKey)
      .then((found) => {
        setStatus(found);
        setError(null);
        return true;
      })
      .catch((failure) => {
        setError(reason(failure));
        return false;
      });
  }, []);

  return { status, error, connect, refresh };
}

export type Model = ReturnType<typeof useModel>;
