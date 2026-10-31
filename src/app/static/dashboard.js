(function () {
  const sessionId = document.body.dataset.session;

  document.querySelectorAll(".tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      document.querySelectorAll(".tab").forEach(function (item) { item.classList.remove("on"); });
      document.querySelectorAll(".panel").forEach(function (item) { item.classList.remove("on"); });
      tab.classList.add("on");
      const panel = document.getElementById(tab.dataset.tab);
      if (panel) panel.classList.add("on");
    });
  });

  function allMissing(series) {
    return series.every(function (item) {
      return !item.data || item.data.every(function (value) { return value === null || value === undefined; });
    });
  }

  function renderChart(chart) {
    const el = document.getElementById("chart-" + chart.id);
    const title = document.getElementById("title-" + chart.id);
    const meta = document.getElementById("meta-" + chart.id);
    if (!el) return;
    if (title) title.textContent = String(chart.id).toUpperCase() + " · " + chart.title;

    const missing = (chart.meta && chart.meta.missing) || [];
    if (meta) {
      if (missing.length) {
        meta.textContent = "数据不足：" + missing.join("、");
        meta.classList.add("warn");
      } else if (chart.meta && chart.meta.caliber) {
        meta.textContent = chart.meta.caliber;
      }
    }

    if (allMissing(chart.series || [])) {
      el.innerHTML = '<div style="height:100%;display:grid;place-items:center;color:#9ca3af;font-size:12px">数据不足，暂不绘图</div>';
      return;
    }

    const chartInstance = echarts.init(el);
    const hasDual = (chart.series || []).some(function (item) { return item.yAxisIndex === 1; });
    const series = (chart.series || []).map(function (item) {
      const copy = Object.assign({}, item);
      copy.type = item.type || "line";
      return copy;
    });

    chartInstance.setOption({
      tooltip: { trigger: "axis" },
      legend: { top: 0, right: 0, textStyle: { fontSize: 11 } },
      grid: { left: 8, right: 12, top: 34, bottom: 4, containLabel: true },
      xAxis: { type: "category", data: chart.x, axisLabel: { color: "#6b7280", fontSize: 11 } },
      yAxis: hasDual
        ? [{ type: "value", splitLine: { lineStyle: { color: "#f1f3f5" } } }, { type: "value", splitLine: { show: false } }]
        : { type: "value", splitLine: { lineStyle: { color: "#f1f3f5" } } },
      series: series,
    });
    window.addEventListener("resize", function () { chartInstance.resize(); });
  }

  fetch("/api/v1/sessions/" + encodeURIComponent(sessionId) + "/charts")
    .then(function (response) { return response.json(); })
    .then(function (body) {
      (body.data && body.data.charts ? body.data.charts : []).forEach(renderChart);
    })
    .catch(function () {
      document.querySelectorAll(".chart").forEach(function (el) {
        el.innerHTML = '<div style="height:100%;display:grid;place-items:center;color:#b91c1c;font-size:12px">图表加载失败</div>';
      });
    });
})();
