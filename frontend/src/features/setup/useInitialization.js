import { useEffect, useRef, useState } from "react";
import { sessionsApi } from "../../api/sessions.js";

export function useInitialization({ bootstrap, onCreated }) {
  const [method, setMethod] = useState("llm");
  const [target, setTarget] = useState(bootstrap.default_target || [143, 150, 106]);
  const [receipt, setReceipt] = useState(null);
  const [working, setWorking] = useState("");
  const [error, setError] = useState("");
  const requestId = useRef({ signature: null, id: null });
  const inFlight = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  const model = bootstrap.model_config || {};
  const ready = Boolean(method === "bo" || model.api_key_configured);

  async function start() {
    if (!ready || inFlight.current) return;
    inFlight.current = true;
    setWorking("start"); setError("");
    try {
      let connection = receipt;
      if (method === "llm" && !connection) {
        connection = await sessionsApi.preflight();
        if (mounted.current) setReceipt(connection);
      }
      const body = {
        target_rgb: target, initial_method: method,
      };
      const signature = JSON.stringify(body);
      if (requestId.current.signature !== signature) {
        requestId.current = { signature, id: crypto.randomUUID() };
      }
      const value = await sessionsApi.create({
        ...body, request_id: requestId.current.id, preflight_token: connection?.token,
      });
      if (mounted.current) onCreated(value);
    } catch (exc) { if (mounted.current) setError(exc.message); }
    finally { inFlight.current = false; if (mounted.current) setWorking(""); }
  }

  function switchMethod(value) {
    setMethod(value); setError("");
  }

  return {
    method, setMethod: switchMethod, target, setTarget,
    working, error, model, ready, start,
  };
}
