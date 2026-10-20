import { useCallback, useEffect, useRef, useState } from "react";
import { sessionsApi } from "../../api/sessions.js";
import { sessionRound } from "../../domain/experiment.js";

export function useExperiment({ snapshot, setSnapshot }) {
  const [working, setWorking] = useState("");
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState(null);
  const inFlight = useRef(false);
  const mounted = useRef(true);
  const { method, state, round, well, complete } = sessionRound(snapshot);
  const pending = state?.pending;
  const roundKey = `${snapshot.id}/${method}/${round}`;
  const currentRound = useRef(roundKey);
  currentRound.current = roundKey;

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  useEffect(() => {
    setFeedback(null); setError("");
  }, [roundKey]);

  async function mutate(action, body = {}) {
    if (inFlight.current) return;
    inFlight.current = true;
    const requestedRound = roundKey;
    const isCurrent = () => mounted.current && currentRound.current === requestedRound;
    setWorking(action); setError("");
    try {
      if (["propose", "retry-invalid"].includes(action)) body = { ...body, method, round_number: round };
      const value = await sessionsApi.mutate(snapshot.id, action, body);
      if (isCurrent()) setSnapshot(value);
    } catch (exc) {
      if (isCurrent()) {
        setError(exc.message);
        // Read authoritative state after a failed response; never replay a write.
        try {
          const value = await sessionsApi.get(snapshot.id);
          if (isCurrent()) setSnapshot(value);
        } catch {}
      }
    } finally {
      inFlight.current = false;
      if (mounted.current) setWorking("");
    }
  }

  const onFeedback = useCallback((value) => setFeedback(value), []);
  function submitMeasurement() {
    if (!feedback || feedback.well !== well || !method) return;
    return mutate("record", {
      upload_id: feedback.upload_id, block: feedback.block, well,
      method, round_number: round,
    });
  }
  return {
    method, round, well, complete, pending, working, error,
    feedback: feedback?.well === well ? feedback : null,
    mutate, onFeedback, submitMeasurement,
  };
}
