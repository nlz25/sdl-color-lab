import React, { useState } from "react";
import { sessionsApi } from "../api/sessions.js";
import { useI18n } from "../i18n/I18n.jsx";
import ErrorNotice from "./ErrorNotice.jsx";

function DownloadIcon() {
  return <svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M8 2v8m-3-3 3 3 3-3M3 10v4h10v-4" /></svg>;
}

export default function OpentronsDownloads({ pending, sessionId, recipeFile }) {
  const { t } = useI18n();
  const [opening, setOpening] = useState(false);
  const [error, setError] = useState("");
  async function openFolder() {
    if (opening) return;
    setOpening(true); setError("");
    try { await sessionsApi.openRecipeFolder(sessionId, pending.method, pending.round); }
    catch (exc) { setError(exc.message); }
    finally { setOpening(false); }
  }
  return <div className={`robot-files${pending ? "" : " protocol-only"}`}>
    <div className="robot-downloads">
      {pending && <button className="secondary" type="button" disabled={opening} onClick={openFolder}>{t(opening ? "opentrons.opening" : "opentrons.openFolder")}<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M2 5V3h4l2 2h6v8H2V5Z" /></svg></button>}
      <a className={pending ? "secondary" : "text-button"} href={sessionsApi.protocolUrl}>{t("opentrons.downloadScript")}{pending && <DownloadIcon />}</a>
    </div>
    {pending && <p className="robot-saved"><span>{t("opentrons.saved")}</span> <a href={sessionsApi.recipeUrl(sessionId, pending.method, pending.round)} title={recipeFile?.path}>{recipeFile?.filename || t("recipe.download")}</a>{recipeFile && <code>{recipeFile.display_directory}</code>}</p>}
    <p className="micro">{t("opentrons.hint")}</p>
    <ErrorNotice>{error}</ErrorNotice>
  </div>;
}
