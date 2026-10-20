import { useCallback, useEffect, useRef, useState } from "react";
import { sessionsApi } from "../api/sessions.js";
import { sessionRecord } from "../domain/experiment.js";

export const SESSION_STORAGE_KEY = "sdl-color-lab:active-session";
const LEGACY_STORAGE_KEY = "colour-session";

function initialSelection() {
  const explicit = new URLSearchParams(window.location.search).get("session");
  if (explicit) return { id: explicit, legacy: false };
  const current = window.localStorage.getItem(SESSION_STORAGE_KEY);
  if (current !== null) return { id: current, legacy: false };
  return { id: window.localStorage.getItem(LEGACY_STORAGE_KEY) || "", legacy: true };
}

function persistSelection(id) {
  const url = new URL(window.location.href);
  if (id) {
    url.searchParams.set("session", id);
    window.localStorage.setItem(SESSION_STORAGE_KEY, id);
  } else {
    url.searchParams.delete("session");
    // Empty explicitly means "new experiment" and also marks legacy migration
    // as handled, so an untouched old project key cannot resurrect a selection.
    window.localStorage.setItem(SESSION_STORAGE_KEY, "");
  }
  window.history.replaceState({}, "", url);
}

/** Own navigation and async loading; never run an experiment as a side effect. */
export function useSessionNavigation() {
  const [initial] = useState(initialSelection);
  const [sessionId, setSessionId] = useState(initial.id);
  const [bootstrap, setBootstrap] = useState(null);
  const [snapshot, updateSnapshot] = useState(null);
  const [error, setError] = useState("");
  const [bootstrapBusy, setBootstrapBusy] = useState(true);
  const [sessionBusy, setSessionBusy] = useState(false);
  const [bootstrapRetry, setBootstrapRetry] = useState(0);
  const [sessionRetry, setSessionRetry] = useState(0);
  const snapshotRef = useRef(null);
  const legacyPending = useRef(initial.legacy);

  const setSnapshot = useCallback((value) => {
    snapshotRef.current = value;
    updateSnapshot(value);
    if (value) {
      setBootstrap((previous) => previous ? {
        ...previous,
        sessions: previous.sessions.map((item) => item.id === value.id ? sessionRecord(value) : item),
      } : previous);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    setBootstrapBusy(true);
    setError("");
    sessionsApi.bootstrap({ signal: controller.signal }).then((value) => {
      if (!current) return;
      if (legacyPending.current) {
        legacyPending.current = false;
        const id = value.sessions.some((item) => item.id === initial.id) ? initial.id : "";
        setSessionId(id);
        persistSelection(id);
      }
      setBootstrap(value);
    }).catch((exc) => {
      if (current) setError(exc.message);
    }).finally(() => {
      if (current) setBootstrapBusy(false);
    });
    return () => { current = false; controller.abort(); };
  }, [bootstrapRetry, initial.id]);

  useEffect(() => {
    if (!sessionId) {
      setSnapshot(null);
      setSessionBusy(false);
      return;
    }
    // Bootstrap is awaited before a restore, and a newly-created response is
    // already authoritative. Neither path competes for the backend session lock.
    if (!bootstrap) return;
    if (snapshotRef.current?.id === sessionId) {
      setSessionBusy(false);
      return;
    }
    const controller = new AbortController();
    let current = true;
    setSessionBusy(true);
    setError("");
    sessionsApi.get(sessionId, { signal: controller.signal }).then((value) => {
      if (current) setSnapshot(value);
    }).catch((exc) => {
      if (current) { setError(exc.message); setSnapshot(null); }
    }).finally(() => {
      if (current) setSessionBusy(false);
    });
    return () => { current = false; controller.abort(); };
  }, [sessionId, Boolean(bootstrap), sessionRetry, setSnapshot]);

  function selectSession(id) {
    legacyPending.current = false;
    setError("");
    if (snapshotRef.current?.id !== id) setSnapshot(null);
    setSessionId(id);
    if (!id) setSessionBusy(false);
    persistSelection(id);
    if (!bootstrap && !bootstrapBusy) setBootstrapRetry((value) => value + 1);
  }

  function created(value) {
    // Update the ref before selecting the ID, so restore effects never re-fetch.
    setSnapshot(value);
    setSessionBusy(false);
    selectSession(value.id);
    setBootstrap((previous) => ({
      ...previous,
      sessions: [
        sessionRecord(value),
        ...(previous?.sessions || []).filter((item) => item.id !== value.id),
      ],
    }));
  }

  function retrySelected() {
    setError("");
    if (!bootstrap) setBootstrapRetry((value) => value + 1);
    else setSessionRetry((value) => value + 1);
  }

  const loading = bootstrapBusy || sessionBusy ||
    Boolean(bootstrap && sessionId && !snapshot && !error);
  return {
    bootstrap, snapshot, setSnapshot, error, loading,
    sessionId, selectSession, created, retrySelected,
  };
}
