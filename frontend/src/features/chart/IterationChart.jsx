import React, { useState } from "react";
import { METHODS, NAMES, SUCCESS_THRESHOLD } from "../../domain/experiment.js";
import { rgbCss } from "../../domain/colors.js";
import { format } from "../../domain/format.js";
import { chartScale, endpointLabelY } from "./chart-model.js";
import { useI18n } from "../../i18n/I18n.jsx";
import Swatch from "../../components/Swatch.jsx";

export default function IterationChart({ rows, target, plateId, budget = 6, method, filter, onFilter }) {
  const { t } = useI18n();
  const [hover, setHover] = useState(null);
  const displayed = filter === "all" ? rows : rows.filter((row) => row.method === filter);
  const methods = Object.keys(METHODS).filter((key) => key === method || rows.some((row) => row.method === key));
  const { ceiling, ticks } = chartScale(rows);
  const width = 1120, height = 390;
  const left = 68, right = 35, top = 31, bottom = 58;
  const x = (round) => left + 30 + ((round - 1) / Math.max(1, budget - 1)) * (width - left - right - 60);
  const y = (value) => height - bottom - (value / ceiling) * (height - bottom - top);
  const selected = displayed.find((row) => `${row.method}-${row.round}` === hover);
  const labelY = (row) => endpointLabelY(row, displayed, y, height - bottom);
  return <section className="chart-panel" aria-label={t("chart.label")}>
    <div className="chart-heading">
      <div>
        <h1>{t("chart.title")}</h1>
        <div className="chart-subtitle">{plateId} <span>·</span> {t("chart.budget", { budget })} <span>·</span> 200 µL</div>
      </div>
      <div className="target-key"><Swatch rgb={target} /><div><span>{t("setup.target")}</span><small>RGB {target.join(", ")}</small></div></div>
    </div>
    <div className="chart-controls">
      {methods.length > 1 && <div className="segmented" aria-label={t("chart.methods")}>
        <span className="filter-label">{t("chart.methods")}</span>
        {[["all", t("chart.all")], ...methods.map((key) => [key, METHODS[key]])].map(([key, label]) =>
          <button type="button" key={key} className={filter === key ? "selected" : ""} onClick={() => { setHover(null); onFilter(key); }}>{label}</button>)}
      </div>}
      <div className="legend">{methods.map((key) => <span key={key}><i className={`line-${key}`} />{METHODS[key]}</span>)}</div>
    </div>
    <div className="chart-scroll">
      <svg viewBox={`0 0 ${width} ${height}`} className="iteration-chart" role="img" aria-label={t("chart.aria", { count: displayed.length })}>
        {ticks.map((tick) => <g key={tick}>
          <line x1={left} x2={width - right} y1={y(tick)} y2={y(tick)} className="grid-line" />
          <text x={left - 15} y={y(tick) + 5} textAnchor="end" className="tick">{tick}</text>
        </g>)}
        <line x1={left} x2={width - right} y1={y(SUCCESS_THRESHOLD)} y2={y(SUCCESS_THRESHOLD)} className="threshold-line" />
        <text x={left + 13} y={y(SUCCESS_THRESHOLD) - 10} className="threshold-text">{t("chart.threshold", { threshold: SUCCESS_THRESHOLD })}</text>
        <line x1={left} x2={left} y1={top} y2={height - bottom} className="axis-line" />
        <line x1={left} x2={width - right} y1={height - bottom} y2={height - bottom} className="axis-line" />
        {Array.from({ length: budget }, (_, i) => i + 1).map((round) => <g key={round}>
          <line x1={x(round)} x2={x(round)} y1={height - bottom} y2={height - bottom + 7} className="axis-line" />
          <text x={x(round)} y={height - bottom + 29} textAnchor="middle" className="tick">{round}</text>
        </g>)}
        <text x={(width + left - right) / 2} y={height - 4} textAnchor="middle" className="axis-label">{t("chart.x")}</text>
        <text transform={`translate(19 ${(height + top - bottom) / 2}) rotate(-90)`} textAnchor="middle" className="axis-label">{t("chart.y")}</text>
        {["llm", "bo"].map((method) => {
          const points = displayed.filter((row) => row.method === method);
          return <g key={method}>
            <polyline className={`series ${method}`} points={points.map((row) => `${x(row.round)},${y(row.delta_e_2000)}`).join(" ")} />
            {points.map((row, index) => {
              const key = `${method}-${row.round}`;
              return <g key={key} className="chart-point" tabIndex={0} role="button"
                aria-label={t("chart.point", { method: METHODS[method], round: row.round, well: row.dest_well, error: format(row.delta_e_2000), rgb: row.rgb.join(",") })}
                onMouseEnter={() => setHover(key)} onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(key)} onBlur={() => setHover(null)}
                onClick={() => setHover(hover === key ? null : key)}>
                <circle cx={x(row.round)} cy={y(row.delta_e_2000)} r={hover === key ? 13 : 10} fill={rgbCss(row.rgb)} className={`colour-point ${method}`} />
                {(index === points.length - 1 || index === 0) && <text x={x(row.round)} y={labelY(row)} textAnchor="middle" className={`point-value ${index === points.length - 1 ? "last" : ""}`}>{format(row.delta_e_2000)}</text>}
                <title>{t("chart.pointTitle", { method: METHODS[method], round: row.round, error: format(row.delta_e_2000), rgb: row.rgb.join(", ") })}</title>
              </g>;
            })}
          </g>;
        })}
        {!displayed.length && <text x={width / 2 + 15} y={height / 2 - 7} textAnchor="middle" className="empty-chart">{t("chart.empty")}</text>}
      </svg>
    </div>
    <div className={`chart-footnote ${selected ? "has-point" : ""}`} aria-live="polite">
      {selected ? <><Swatch rgb={selected.rgb} /><b>{METHODS[selected.method]} · {t("chart.round", { round: selected.round })} · {selected.dest_well}</b><span>ΔE₀₀ {format(selected.delta_e_2000)}</span><span>RGB {selected.rgb.join(", ")}</span><span>{NAMES.map((name) => `${t("reagent." + name)} ${selected.recipe[name]}`).join(" / ")} µL</span></> : <span>{t("chart.footnote")}</span>}
    </div>
  </section>;
}
