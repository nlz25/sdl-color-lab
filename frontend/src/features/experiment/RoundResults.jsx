import React from "react";
import { METHODS, NAMES } from "../../domain/experiment.js";
import { format } from "../../domain/format.js";
import { useI18n } from "../../i18n/I18n.jsx";
import Swatch from "../../components/Swatch.jsx";

/** Recorded measurements only; shares the chart's display filter. */
export default function RoundResults({ rows, filter, modelId }) {
  const { t } = useI18n();
  const displayed = filter === "all" ? rows : rows.filter((row) => row.method === filter);
  return <section className="round-results" aria-label={t("results.title")}>
    <div className="results-heading"><h2>{t("results.title")}</h2><span>{t("results.volume")}</span></div>
    {displayed.length ? <div className="results-scroll" tabIndex={0} role="region" aria-label={t("results.title")}>
      <table className="results-table" aria-label={t("results.title")}>
        <thead><tr>
          <th scope="col">{t("results.method")}</th>
          <th scope="col">{t("results.round")}</th>
          <th scope="col">{t("results.well")}</th>
          {NAMES.map((name) => <th scope="col" key={name}>{t("reagent." + name)}</th>)}
          <th scope="col">{t("results.rgb")}</th>
          <th scope="col">ΔE₀₀</th>
        </tr></thead>
        <tbody>{displayed.map((row) => <tr key={`${row.method}-${row.round}`}>
          <th scope="row"><span className="result-method"><i className={`method-line ${row.method}`} />{row.method === "llm" ? modelId || METHODS.llm : METHODS.bo}</span></th>
          <td>{row.round}</td>
          <td className="result-well">{row.dest_well}</td>
          {NAMES.map((name) => <td key={name}>{row.recipe[name]}</td>)}
          <td><span className="result-colour"><Swatch rgb={row.rgb} /><span>{row.rgb.join(", ")}</span></span></td>
          <td className="result-error">{format(row.delta_e_2000)}</td>
        </tr>)}</tbody>
      </table>
    </div> : <p className="results-empty">{t("results.empty")}</p>}
  </section>;
}
