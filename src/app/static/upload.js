(function () {
  const dropzone = document.getElementById("dropzone");
  const input = document.getElementById("file");
  const filelist = document.getElementById("filelist");
  const startBtn = document.getElementById("start");
  const statusEl = document.getElementById("status");
  const progressBar = document.getElementById("progressbar");
  const bar = document.getElementById("bar");
  if (!dropzone || !input) return;

  const STAGES = {
    queued: "排队中",
    parsing: "解析表格",
    aligning: "对齐科目",
    computing: "计算指标",
  };
  let files = [];

  function setStatus(text, kind) {
    statusEl.textContent = text || "";
    statusEl.className = "status" + (kind ? " " + kind : "");
  }

  function setProgress(ratio, text) {
    progressBar.hidden = false;
    const percent = Math.max(0, Math.min(100, Math.round(ratio * 100)));
    bar.style.width = percent + "%";
    if (text) statusEl.textContent = text + " " + percent + "%";
  }

  function renderFiles() {
    filelist.innerHTML = "";
    files.forEach(function (file, index) {
      const chip = document.createElement("span");
      chip.className = "file-chip";
      chip.innerHTML =
        '<b>' + (index + 1) + "</b> " +
        file.name + ' <span class="fs">' + (file.size / 1024 / 1024).toFixed(1) + " MB</span>" +
        '<i class="rm" title="移除">×</i>';
      chip.querySelector(".rm").addEventListener("click", function (event) {
        event.stopPropagation();
        files.splice(index, 1);
        renderFiles();
      });
      filelist.appendChild(chip);
    });
    startBtn.disabled = files.length === 0;
    if (files.length) setStatus("已选择 " + files.length + " 份文件", "ok");
    else setStatus("");
  }

  function addFiles(list) {
    const incoming = Array.from(list || []).filter(function (file) {
      return /\.pdf$/i.test(file.name) || file.type === "application/pdf";
    });
    const rejected = Array.from(list || []).length - incoming.length;
    files = files.concat(incoming).slice(0, 5);
    renderFiles();
    if (rejected > 0) setStatus("已忽略 " + rejected + " 个非 PDF 文件", "error");
    if (files.length >= 5) setStatus("最多 5 份，已截断", "error");
  }

  dropzone.addEventListener("click", function () { input.click(); });
  input.addEventListener("change", function () { addFiles(input.files); input.value = ""; });

  ["dragenter", "dragover"].forEach(function (name) {
    dropzone.addEventListener(name, function (event) {
      event.preventDefault();
      dropzone.classList.add("on");
    });
  });
  ["dragleave", "drop"].forEach(function (name) {
    dropzone.addEventListener(name, function (event) {
      event.preventDefault();
      dropzone.classList.remove("on");
    });
  });
  dropzone.addEventListener("drop", function (event) {
    addFiles(event.dataTransfer ? event.dataTransfer.files : []);
  });

  function postUpload(file, sessionId) {
    const data = new FormData();
    data.append("file", file);
    if (sessionId) data.append("session_id", sessionId);
    return fetch("/api/v1/uploads", { method: "POST", body: data }).then(function (response) {
      return response.json();
    });
  }

  function pollJob(jobId) {
    return new Promise(function (resolve, reject) {
      function tick() {
        fetch("/api/v1/jobs/" + encodeURIComponent(jobId))
          .then(function (response) { return response.json(); })
          .then(function (body) {
            const job = body.data || {};
            if (job.state === "done") { resolve(job); return; }
            if (job.state === "failed") {
              reject(new Error((job.error && job.error.msg) || "解析失败"));
              return;
            }
            const stage = STAGES[job.stage] || job.stage || "处理中";
            const queue = job.queue_position ? "（排队第 " + job.queue_position + " 位）" : "";
            setProgress(job.progress || 0, stage + queue);
            setTimeout(tick, 900);
          })
          .catch(function () { setTimeout(tick, 1500); });
      }
      tick();
    });
  }

  startBtn.addEventListener("click", async function () {
    if (!files.length) return;
    startBtn.disabled = true;
    progressBar.hidden = false;
    setProgress(0.02, "上传中");
    let sessionId = null;
    try {
      for (let index = 0; index < files.length; index++) {
        const file = files[index];
        setProgress(index === 0 ? 0.05 : 0.1, "上传第 " + (index + 1) + "/" + files.length + " 份");
        const body = await postUpload(file, sessionId);
        if (body.code !== 0) throw new Error("第 " + (index + 1) + " 份失败：" + body.msg);
        sessionId = body.data.session_id;
        setProgress(0.15, "解析第 " + (index + 1) + "/" + files.length + " 份");
        await pollJob(body.data.job.job_id);
        setProgress((index + 1) / files.length, "已完成 " + (index + 1) + "/" + files.length);
      }
      setStatus("解析完成，正在打开看板…", "ok");
      window.location.href = "/s/" + sessionId;
    } catch (error) {
      setStatus("上传中断：" + error.message, "error");
      startBtn.disabled = false;
      progressBar.hidden = true;
    }
  });
})();
