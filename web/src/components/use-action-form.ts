"use client";

import { startTransition, useActionState, useEffect, useRef, type FormEvent } from "react";

export type State = { message: string; error: boolean };

// useActionState for a form, without React's automatic reset after every submission: a
// rejected submission keeps what Edgar typed, and only a successful one clears the form.
// The plain `action` stays on the form so it still posts before hydration.
export function useActionForm(
  fn: (prev: State, formData: FormData) => Promise<State>,
  initial: State,
) {
  const [state, action, pending] = useActionState(fn, initial);
  const ref = useRef<HTMLFormElement>(null);

  useEffect(() => {
    if (state !== initial && !state.error) ref.current?.reset();
  }, [state, initial]);

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const submitter = (e.nativeEvent as SubmitEvent).submitter;
    const data = new FormData(e.currentTarget, submitter);
    startTransition(() => action(data));
  }

  return { state, pending, action, ref, onSubmit };
}
