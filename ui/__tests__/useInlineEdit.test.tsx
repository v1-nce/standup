import { act, renderHook } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { useInlineEdit } from "../app/hooks/useInlineEdit";

function keyEvent(key: string) {
  return { currentTarget: { value: "typed" }, key } as unknown as React.KeyboardEvent<HTMLInputElement>;
}

function blurEvent(value: string) {
  return { currentTarget: { value } } as unknown as React.FocusEvent<HTMLInputElement>;
}

test("commits the trimmed value on Enter and closes", () => {
  const onCommit = vi.fn();
  const { result } = renderHook(() => useInlineEdit(onCommit));

  act(() => result.current.open());
  expect(result.current.editing).toBe(true);

  act(() => result.current.fieldProps.onKeyDown(keyEvent("Enter")));

  expect(onCommit).toHaveBeenCalledWith("typed");
  expect(result.current.editing).toBe(false);
});

test("Escape discards without committing, and the blur it triggers is suppressed", () => {
  const onCommit = vi.fn();
  const { result } = renderHook(() => useInlineEdit(onCommit));

  act(() => result.current.open());
  act(() => result.current.fieldProps.onKeyDown(keyEvent("Escape")));

  expect(onCommit).not.toHaveBeenCalled();
  expect(result.current.editing).toBe(false);

  // Escape blurs the input in a real browser; that blur must not re-commit.
  act(() => result.current.fieldProps.onBlur(blurEvent("typed")));
  expect(onCommit).not.toHaveBeenCalled();
});

test("blur commits, same as Enter", () => {
  const onCommit = vi.fn();
  const { result } = renderHook(() => useInlineEdit(onCommit));

  act(() => result.current.open());
  act(() => result.current.fieldProps.onBlur(blurEvent("typed")));

  expect(onCommit).toHaveBeenCalledWith("typed");
  expect(result.current.editing).toBe(false);
});

test("an empty value closes without committing", () => {
  const onCommit = vi.fn();
  const { result } = renderHook(() => useInlineEdit(onCommit));

  act(() => result.current.open());
  act(() => result.current.fieldProps.onBlur(blurEvent("   ")));

  expect(onCommit).not.toHaveBeenCalled();
  expect(result.current.editing).toBe(false);
});

test("a rejected async commit reopens the field instead of leaving it closed", async () => {
  let resolve!: (made: boolean) => void;
  const onCommit = vi.fn(() => new Promise<boolean>((r) => (resolve = r)));
  const { result } = renderHook(() => useInlineEdit(onCommit));

  act(() => result.current.open());
  act(() => result.current.fieldProps.onKeyDown(keyEvent("Enter")));

  // Stays open for the whole async wait - never closes and reopens, which
  // would remount the (uncontrolled) input and lose what was typed.
  expect(result.current.editing).toBe(true);

  await act(async () => resolve(false));
  expect(result.current.editing).toBe(true);
});

test("a resolved async commit closes the field", async () => {
  let resolve!: (made: boolean) => void;
  const onCommit = vi.fn(() => new Promise<boolean>((r) => (resolve = r)));
  const { result } = renderHook(() => useInlineEdit(onCommit));

  act(() => result.current.open());
  act(() => result.current.fieldProps.onKeyDown(keyEvent("Enter")));

  await act(async () => resolve(true));
  expect(result.current.editing).toBe(false);
});
