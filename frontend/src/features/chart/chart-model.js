export function chartScale(rows) {
  const maximum = Math.max(10, ...rows.map((row) => Number(row.delta_e_2000) || 0));
  const step = maximum <= 20 ? 5 : maximum <= 60 ? 10 : maximum <= 120 ? 20 : 25;
  const ceiling = Math.ceil((maximum * 1.15) / step) * step;
  return { ceiling, ticks: Array.from({ length: Math.floor(ceiling / step) + 1 }, (_, i) => i * step) };
}

export function endpointLabelY(row, displayed, y, plotBottom) {
  const other = displayed.find((item) => {
    if (item.method === row.method || item.round !== row.round) return false;
    const series = displayed.filter((point) => point.method === item.method);
    return item === series[0] || item === series.at(-1);
  });
  const position = y(row.delta_e_2000);
  if (!other || Math.abs(position - y(other.delta_e_2000)) >= 36) return position - 19;
  const upper = Math.min(position, y(other.delta_e_2000));
  const lower = Math.max(position, y(other.delta_e_2000));
  if (lower + 26 > plotBottom - 5) return upper - (row.method === "llm" ? 43 : 17);
  return row.method === "llm" ? upper - 19 : lower + 26;
}
