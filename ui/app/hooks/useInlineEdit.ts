"use client";

import { useRef, useState } from "react";

/** An inline text field that opens in place, commits on Enter or blur, and
 *  discards on Escape. The `cancelling` ref exists because Escape blurs the
 *  field itself, which would otherwise re-fire onBlur and commit the value
 *  Escape just meant to discard.
 *
 *  `onCommit` may resolve to `false` to keep the field open with its typed
 *  value intact - e.g. a create request the backend rejected, worth
 *  correcting in place rather than retyping. The field stays mounted (and
 *  so keeps its DOM value) for the whole async wait, rather than closing
 *  optimistically and reopening empty. */
export function useInlineEdit(onCommit: (value: string) => unknown) {
  const [editing, setEditing] = useState(false);
  const cancelling = useRef(false);

  const commit = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed) return setEditing(false);
    const result = onCommit(trimmed);
    if (result && typeof result === "object" && "then" in result) {
      void (result as Promise<unknown>).then((made) => {
        if (made !== false) setEditing(false);
      });
    } else {
      setEditing(false);
    }
  };

  const cancel = () => {
    cancelling.current = true;
    setEditing(false);
  };

  const fieldProps = {
    onBlur: (event: React.FocusEvent<HTMLInputElement>) => {
      if (cancelling.current) {
        cancelling.current = false;
        return;
      }
      commit(event.currentTarget.value);
    },
    onKeyDown: (event: React.KeyboardEvent<HTMLInputElement>) => {
      if (event.key === "Enter") commit(event.currentTarget.value);
      if (event.key === "Escape") cancel();
    },
  };

  return { cancel, commit, editing, fieldProps, open: () => setEditing(true) };
}
