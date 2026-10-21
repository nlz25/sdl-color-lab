import React from "react";
import { NAMES, SWATCHES } from "../../domain/experiment.js";
import OpentronsDownloads from "../../components/OpentronsDownloads.jsx";
import { useI18n } from "../../i18n/I18n.jsx";

export default function RecipePanel({ pending, sessionId, recipeFile, desktopFiles = true }) {
  const { t } = useI18n();
  return <div className="recipe-row"><div className="recipe-values">{NAMES.map((name) => <div key={name}><span><i style={{ background: SWATCHES[name] }} />{t("reagent." + name)}</span><b>{pending.recipe[name]}<small>µL</small></b></div>)}</div><OpentronsDownloads pending={pending} sessionId={sessionId} recipeFile={recipeFile} desktopFiles={desktopFiles} /></div>;
}
