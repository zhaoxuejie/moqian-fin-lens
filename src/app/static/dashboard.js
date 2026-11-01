(function () {
  const sessionId = document.body.dataset.session;
  const mask = document.getElementById("mask");

  document.querySelectorAll(".tab[data-tab]").forEach(function (tab) {
    tab.addEventListener("click", function () {
      document.querySelectorAll(".tab[data-tab]").forEach(function (item) { item.classList.remove("on"); });
      document.querySelectorAll(".panel").forEach(function (item) { item.classList.remove("on"); });
      tab.classList.add("on");
      const panel = document.getElementById(tab.dataset.tab);
      if (panel) panel.classList.add("on");
    });
  });

  const CIRCLED = { v1: "①", v2: "②", v3: "③", v4: "④", v5: "⑤", v6: "⑥", v7: "⑦" };

  function unitLabel(unit) {
    if (!unit) return "";
    return unit === "元" ? "亿元" : unit;
  }

  function axisFormatter(unit) {
    if (unit === "元") {
      return function (value) {
        const abs = Math.abs(value);
        if (abs >= 100000000) return (value / 100000000).toFixed(0) + " 亿";
        if (abs >= 10000) return (value / 10000).toFixed(0) + " 万";
        return value;
      };
    }
    if (unit === "%") return function (value) { return value + "%"; };
    if (unit === "倍") return function (value) { return Number(value).toFixed(1); };
    return null;
  }

  function allMissing(series) {
    return series.every(function (item) {
      return !item.data || item.data.every(function (value) { return value === null || value === undefined; });
    });
  }

  function renderChart(chart) {
    const el = document.getElementById("chart-" + chart.id);
    const title = document.getElementById("title-" + chart.id);
    const sub = document.getElementById("sub-" + chart.id);
    const meta = document.getElementById("meta-" + chart.id);
    if (!el) return;
    const circle = CIRCLED[chart.id] || String(chart.id).toUpperCase();
    if (title) title.textContent = circle + " " + chart.title;
    if (sub && chart.meta && chart.meta.caliber) {
      sub.textContent = chart.meta.caliber + (chart.unit ? " · 单位：" + unitLabel(chart.unit) : "");
    }

    const missing = (chart.meta && chart.meta.missing) || [];
    if (meta) {
      if (missing.length) {
        meta.textContent = "数据不足：" + missing.join("、");
        meta.classList.add("warn");
      } else {
        meta.textContent = "";
      }
    }

    if (allMissing(chart.series || [])) {
      el.innerHTML = '<div style="height:100%;display:grid;place-items:center;color:#9ca3af;font-size:12px">数据不足，暂不绘图</div>';
      return;
    }

    const chartInstance = echarts.init(el);
    const formatter = axisFormatter(chart.unit);
    const hasDual = (chart.series || []).some(function (item) { return item.yAxisIndex === 1; });
    const series = (chart.series || []).map(function (item) {
      const copy = Object.assign({}, item);
      copy.type = item.type || "line";
      return copy;
    });

    chartInstance.setOption({
      tooltip: {
        trigger: "axis",
        valueFormatter: formatter ? function (value) { return formatter(value); } : undefined,
      },
      legend: { top: 0, right: 0, textStyle: { fontSize: 11 } },
      grid: { left: 8, right: 12, top: 34, bottom: 4, containLabel: true },
      xAxis: { type: "category", data: chart.x, axisLabel: { color: "#6b7280", fontSize: 11 } },
      yAxis: hasDual
        ? [
            {
              type: "value",
              axisLabel: { formatter: axisFormatter(chart.unit === "倍" ? "元" : chart.unit) || undefined },
              splitLine: { lineStyle: { color: "#f1f3f5" } },
            },
            {
              type: "value",
              axisLabel: { formatter: axisFormatter(chart.unit === "倍" ? "倍" : chart.unit) || undefined },
              splitLine: { show: false },
            },
          ]
        : { type: "value", axisLabel: { formatter: formatter || undefined }, splitLine: { lineStyle: { color: "#f1f3f5" } } },
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

  let compareData = null;
  let compareUnit = localStorage.getItem("finance_compare_unit") || "auto";
  let compareDelta = localStorage.getItem("compare_show_delta") !== "0";

  function rawText(text) {
    if (text === null || text === undefined) return "";
    const value = Number(text);
    return Number.isFinite(value) ? value.toLocaleString("zh-CN", { maximumFractionDigits: 2 }) : String(text);
  }

  function fmtCompare(text) {
    if (text === null || text === undefined) return "—";
    const value = Number(text);
    if (!Number.isFinite(value)) return String(text);
    if (compareUnit === "yuan") return value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
    const abs = Math.abs(value);
    if (compareUnit === "yi" || (compareUnit === "auto" && abs >= 100000000)) {
      return (value / 100000000).toLocaleString("zh-CN", { maximumFractionDigits: 2 }) + " 亿";
    }
    if (compareUnit === "wan" || (compareUnit === "auto" && abs >= 10000)) {
      return (value / 10000).toLocaleString("zh-CN", { maximumFractionDigits: 2 }) + " 万";
    }
    return value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
  }

  function activeCompareKind() {
    const active = document.querySelector("#compare-tabs .tab.on");
    return active ? active.dataset.compare : "balance";
  }

  function renderCompare(kind) {
    const body = document.getElementById("compare-body");
    if (!body || !compareData || !compareData.statements[kind]) return;
    const statement = compareData.statements[kind];
    const periods = compareData.periods;

    let headTop = '<th rowspan="2">科目</th>';
    let headSub = "";
    periods.forEach(function (period, index) {
      if (index === 0) {
        headTop += '<th rowspan="2">' + period + "</th>";
      } else if (compareDelta) {
        headTop += '<th class="group" colspan="3">' + period + "</th>";
        headSub += '<th class="sub group">值</th><th class="sub">增减额</th><th class="sub">同比</th>';
      } else {
        headTop += '<th class="group" colspan="2">' + period + "</th>";
        headSub += '<th class="sub group">值</th><th class="sub">同比</th>';
      }
    });

    let html = '<table class="compare"><thead><tr>' + headTop + "</tr><tr>" + headSub + "</tr></thead><tbody>";
    statement.rows.forEach(function (row) {
      html += "<tr><td>" + row.label + "</td>";
      row.values.forEach(function (value, index) {
        html += '<td class="num" title="' + rawText(value) + '">' + fmtCompare(value) + "</td>";
        if (index > 0) {
          if (compareDelta) {
            const delta = row.delta ? row.delta[index] : null;
            html += '<td class="num delta" title="' + rawText(delta) + '">' + fmtCompare(delta) + "</td>";
          }
          const yoy = row.yoy[index];
          if (yoy === null || yoy === undefined) {
            html += '<td class="num">—</td>';
          } else {
            html += '<td class="num cy ' + (yoy >= 0 ? "up" : "down") + '">' + (yoy >= 0 ? "▲" : "▼") + " " + Math.abs(yoy).toFixed(1) + "%</td>";
          }
        }
      });
      html += "</tr>";
    });
    body.innerHTML = html + "</tbody></table>";

    document.querySelectorAll("#compare-units .unit[data-unit]").forEach(function (button) {
      button.classList.toggle("on", button.dataset.unit === compareUnit);
    });
    const deltaButton = document.getElementById("toggle-delta");
    if (deltaButton) deltaButton.classList.toggle("on", compareDelta);
  }

  document.querySelectorAll("#compare-units .unit[data-unit]").forEach(function (button) {
    button.addEventListener("click", function () {
      compareUnit = button.dataset.unit;
      localStorage.setItem("finance_compare_unit", compareUnit);
      renderCompare(activeCompareKind());
    });
  });

  const deltaToggle = document.getElementById("toggle-delta");
  if (deltaToggle) {
    deltaToggle.addEventListener("click", function () {
      compareDelta = !compareDelta;
      localStorage.setItem("compare_show_delta", compareDelta ? "1" : "0");
      renderCompare(activeCompareKind());
    });
  }

  fetch("/api/v1/sessions/" + encodeURIComponent(sessionId) + "/compare")
    .then(function (response) { return response.json(); })
    .then(function (body) {
      compareData = body.data;
      renderCompare("balance");
    })
    .catch(function () {
      const body = document.getElementById("compare-body");
      if (body) body.textContent = "对比数据加载失败";
    });

  document.querySelectorAll("#compare-tabs .tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      document.querySelectorAll("#compare-tabs .tab").forEach(function (item) { item.classList.remove("on"); });
      tab.classList.add("on");
      renderCompare(tab.dataset.compare);
    });
  });

  const companyToggle = document.getElementById("company-toggle");
  const companyDetail = document.getElementById("company-detail");

  function applyCompanyDetail(open) {
    if (!companyDetail || !companyToggle) return;
    companyDetail.hidden = !open;
    companyToggle.textContent = open ? "收起档案 ▴" : "展开档案 ▾";
  }

  if (companyToggle && companyDetail) {
    applyCompanyDetail(localStorage.getItem("company_detail_open") === "1");
    companyToggle.addEventListener("click", function () {
      const open = companyDetail.hidden;
      localStorage.setItem("company_detail_open", open ? "1" : "0");
      applyCompanyDetail(open);
    });
  }

  function closeModal() {
    if (mask) mask.classList.remove("on");
  }

  document.addEventListener("click", function (event) {
    const trigger = event.target.closest("[data-entry]");
    if (trigger) {
      const entryId = trigger.dataset.entry;
      fetch("/api/v1/sessions/" + encodeURIComponent(sessionId) + "/trace/" + encodeURIComponent(entryId))
        .then(function (response) { return response.json(); })
        .then(function (body) {
          const data = body.data || {};
          document.getElementById("m-title").textContent = data.label || "原文溯源";
          document.getElementById("m-meta").textContent = "P." + data.page + (data.account_code ? " · " + data.account_code : "");
          document.getElementById("m-quote").textContent = data.snippet || "原文片段缺失";
          document.getElementById("m-note").textContent = data.formula || data.unit_note || "";
          mask.classList.add("on");
        })
        .catch(function () {});
    }
    if (event.target === mask) closeModal();
  });

  const mClose = document.getElementById("m-close");
  if (mClose) mClose.addEventListener("click", closeModal);

  function exportAs(kind) {
    fetch("/api/v1/sessions/" + encodeURIComponent(sessionId) + "/exports", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: kind }),
    })
      .then(function (response) { return response.json(); })
      .then(function (body) {
        if (body.data && body.data.download_url) {
          window.location.href = body.data.download_url;
        }
      });
  }

  const md = document.getElementById("export-md");
  const xlsx = document.getElementById("export-xlsx");
  if (md) md.addEventListener("click", function () { exportAs("markdown"); });
  if (xlsx) xlsx.addEventListener("click", function () { exportAs("xlsx"); });

  const continueBtn = document.getElementById("continue-upload");
  const continueFile = document.getElementById("continue-file");
  const continueStatus = document.getElementById("continue-status");

  function setContinueStatus(text) {
    if (continueStatus) continueStatus.textContent = text;
  }

  if (continueBtn && continueFile) {
    continueBtn.addEventListener("click", function () { continueFile.click(); });
    continueFile.addEventListener("change", function () {
      const file = continueFile.files && continueFile.files[0];
      if (!file) return;
      const data = new FormData();
      data.append("file", file);
      data.append("session_id", sessionId);
      continueBtn.disabled = true;
      setContinueStatus("上传中…");
      fetch("/api/v1/uploads", { method: "POST", body: data })
        .then(function (response) { return response.json(); })
        .then(function (body) {
          if (body.code !== 0) {
            setContinueStatus("失败：" + body.msg);
            continueBtn.disabled = false;
            return;
          }
          const jobId = body.data.job.job_id;
          (function poll() {
            fetch("/api/v1/jobs/" + encodeURIComponent(jobId))
              .then(function (response) { return response.json(); })
              .then(function (result) {
                const job = result.data || {};
                if (job.state === "done") {
                  location.reload();
                  return;
                }
                if (job.state === "failed") {
                  setContinueStatus("解析失败：" + ((job.error && job.error.msg) || "未知错误"));
                  continueBtn.disabled = false;
                  return;
                }
                setContinueStatus("解析中 " + Math.round((job.progress || 0) * 100) + "%");
                setTimeout(poll, 1200);
              });
          })();
        })
        .catch(function () {
          setContinueStatus("上传失败，请重试");
          continueBtn.disabled = false;
        });
    });
  }
})();
