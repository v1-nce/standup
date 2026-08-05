"use client";

import { useCallback, useEffect, useState } from "react";
import { api, reason, type ChatMessage, type Deck } from "@/app/api/client";

/** One project's conversation and the deck it is building. They change together, so they live together. */
export function useConversation(projectId: string | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [deck, setDeck] = useState<Deck | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(
    (id: string) =>
      Promise.all([api.readChat(id), api.readDeck(id)]).then(([said, current]) => {
        setMessages(said);
        setDeck(current);
      }),
    [],
  );

  const [showing, setShowing] = useState(projectId);
  if (showing !== projectId) {
    setShowing(projectId);
    setMessages([]);
    setDeck(null);
    setError(null);
  }

  useEffect(() => {
    if (projectId) refresh(projectId).catch((failure) => setError(reason(failure)));
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
        if (finished.state === "failed") setError(finished.detail ?? "The turn failed");
        await refresh(projectId);
      } catch (failure) {
        setError(reason(failure));
      } finally {
        setPending(false);
      }
    },
    [projectId, refresh],
  );

  return { messages, deck, pending, error, send };
}
