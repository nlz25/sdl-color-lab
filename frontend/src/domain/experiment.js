export const METHODS = { llm: "GPT-6", bo: "BO-EI" };
export const SUCCESS_THRESHOLD = 1;
export const NAMES = ["Red", "Blue", "Green", "water"];
export const SWATCHES = { Red: "#b95648", Blue: "#4b7197", Green: "#638366", water: "#e5e9eb" };

export function sessionRecord(snapshot) {
  return {
    id: snapshot.id,
    plate_id: snapshot.config.plate_id,
    phase: snapshot.phase,
    active_method: snapshot.active_method,
    model: snapshot.config.model,
  };
}

export function sessionLabel(record) {
  const method = record.active_method || (record.phase === "bo" ? "bo" : "llm");
  const model = method === "bo" ? METHODS.bo : record.model || METHODS.llm;
  const plate = record.plate_id || record.id.slice(0, 8).toUpperCase();
  const generatedPlate = `EXP-${record.id.slice(0, 8).toUpperCase()}`;
  const identifier = plate === generatedPlate ? plate : `${plate} · ${record.id.slice(0, 6)}`;
  return `${model} · ${identifier}`;
}

export function allRows(snapshot) {
  return ["llm", "bo"].flatMap((method) =>
    (snapshot?.runs?.[method]?.history || []).map((row) => ({ ...row, method })),
  );
}

export function sessionRound(snapshot) {
  const method = snapshot?.active_method || (["llm", "bo"].includes(snapshot?.phase) ? snapshot.phase : null);
  const state = method ? snapshot.runs[method] : null;
  const complete = Boolean(state && state.history.length >= snapshot.config.budget);
  const round = state ? Math.min(state.history.length + 1, snapshot.config.budget) : null;
  return { method, state, round, complete, well: method ? `${method === "llm" ? "A" : "B"}${round}` : null };
}
