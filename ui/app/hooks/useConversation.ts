"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, reason, type ChatMessage, type Deck } from "@/app/api/client";

/** One project's conversation and the deck it is building. They change together, so they live together. */
export function useConversation(projectId: string | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [deck, setDeck] = useState<Deck | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(projectId !== null);
  const latest = useRef(0);
  const active = useRef(projectId);
  useEffect(() => {
    active.current = projectId;
  });

  const refresh = useCallback((id: string) => {
    const mine = ++latest.current;
    return Promise.all([api.readChat(id), api.readDeck(id)]).then(([said, current]) => {
      if (mine === latest.current) {
        setMessages(said);
        setDeck(current);
      }
    });
  }, []);

  const [showing, setShowing] = useState(projectId);
  if (showing !== projectId) {
    setShowing(projectId);
    setMessages([]);
    setDeck(null);
    setError(null);
    setPending(false);
    setLoading(projectId !== null);
  }

  useEffect(() => {
    if (projectId) {
      refresh(projectId)
        .catch((failure) => setError(reason(failure)))
        .finally(() => setLoading(false));
    }
  }, [projectId, refresh]);

  const send = useCallback(
    async (content: string) => {
      if (!projectId) return;
      setPending(true);
      setError(null);
      setMessages((said) => [...said, { role: "user", content, at: new Date().toISOString() }]);

      try {
        const started = await api.sendMessage(projectId, content);
        const finished = await api.awaitJob(started.id);
        if (active.current !== projectId) return;
        if (finished.state === "failed") setError(finished.detail ?? "The turn failed");
        await refresh(projectId);
      } catch (failure) {
        if (active.current === projectId) {
          setError(reason(failure));
          // The optimistic bubble above was never confirmed sent (sendMessage/awaitJob itself
          // threw, before or during the request) - resync with the server instead of guessing
          // which local message to remove.
          await refresh(projectId).catch(() => {});
        }
      } finally {
        if (active.current === projectId) setPending(false);
      }
    },
    [projectId, refresh],
  );

  return { messages, deck, pending, error, loading, send };
}
