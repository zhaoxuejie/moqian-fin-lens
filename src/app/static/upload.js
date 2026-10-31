(function () {
  const form = document.getElementById("upload-form");
  const status = document.getElementById("status");
  if (!form) return;

  const STAGES = {
    queued: "排队中",
    parsing: "解析表格",
    aligning: "对齐科目",
    computing: "计算指标",
  };

  function setStatus(text, kind) {
    status.textContent = text;
    status.className = "status" + (kind ? " " + kind : "");
  }

  function poll(jobId, sessionId) {
    fetch("/api/v1/jobs/" + encodeURIComponent(jobId))
      .then(function (response) { return response.json(); })
      .then(function (body) {
        const job = body.data || {};
        if (job.state === "done") {
          setStatus("解析完成，正在打开看板…", "ok");
          window.location.href = "/s/" + sessionId;
          return;
        }
        if (job.state === "failed") {
          const detail = job.error && job.error.msg ? job.error.msg : "解析失败";
          setStatus("解析失败：" + detail + "（可重新上传重试）", "error");
          return;
        }
        const stage = STAGES[job.stage] || job.stage || "处理中";
        const percent = Math.round((job.progress || 0) * 100);
        const queue = job.queue_position ? "（排队第 " + job.queue_position + " 位）" : "";
        setStatus(stage + " " + percent + "%" + queue);
        setTimeout(function () { poll(jobId, sessionId); }, 1000);
      })
      .catch(function () {
        setStatus("状态查询失败，请稍后重试", "error");
      });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    const input = document.getElementById("file");
    if (!input || !input.files || !input.files.length) {
      setStatus("请先选择一份 PDF", "error");
      return;
    }
    if (input.files[0].size > 50 * 1024 * 1024) {
      setStatus("文件超过 50MB", "error");
      return;
    }

    const data = new FormData();
    data.append("file", input.files[0]);
    setStatus("正在上传…");

    fetch("/api/v1/uploads", { method: "POST", body: data })
      .then(function (response) {
        return response.json().then(function (body) { return { status: response.status, body: body }; });
      })
      .then(function (result) {
        if (result.body.code !== 0) {
          setStatus("上传失败：" + result.body.msg, "error");
          return;
        }
        const payload = result.body.data;
        setStatus("已提交，开始解析…");
        poll(payload.job.job_id, payload.session_id);
      })
      .catch(function () {
        setStatus("上传失败，请检查网络后重试", "error");
      });
  });
})();
