(function () {
  const $ = (id) => document.getElementById(id);
  const dropzone = $("dropzone");
  const fileInput = $("files");
  const fileList = $("file-list");
  const btnUpload = $("btn-upload");
  const btnEnroll = $("btn-enroll");
  const btnScan = $("btn-scan");
  const btnRec = $("btn-rec");
  const btnRecSave = $("btn-rec-save");
  const btnRecDiscard = $("btn-rec-discard");
  const btnRecCheck = $("btn-rec-check");
  const btnCheckAll = $("btn-check-all");
  const btnRestart = $("btn-restart");
  const speakerInput = $("speaker");
  const enrollSpeaker = $("enroll-speaker");
  const enrollLog = $("enroll-log");
  const flashBox = $("flash-box");
  const scanResults = $("scan-results");
  const currentUpstream = $("current-upstream");
  const recStatus = $("rec-status");
  const recPreview = $("rec-preview");
  const recActions = $("rec-actions");
  const recCheckResult = $("rec-check-result");
  const qualityBox = $("quality-box");
  const restartBanner = $("restart-banner");

  let mediaRecorder = null;
  let recChunks = [];
  let recBlob = null;
  let recording = false;

  function flash(msg, type) {
    flashBox.innerHTML = '<div class="flash ' + type + '">' + msg + "</div>";
    setTimeout(function () { flashBox.innerHTML = ""; }, 8000);
  }

  function speaker() {
    return (speakerInput.value || "").trim().toLowerCase();
  }

  speakerInput.addEventListener("input", function () {
    enrollSpeaker.value = speaker();
  });

  function updateFileList() {
    fileList.innerHTML = "";
    if (!fileInput.files) return;
    Array.from(fileInput.files).forEach(function (f) {
      var li = document.createElement("li");
      li.textContent = "📄 " + f.name + " (" + (f.size / 1024).toFixed(1) + " KB)";
      fileList.appendChild(li);
    });
  }
  fileInput.addEventListener("change", updateFileList);

  ["dragenter", "dragover"].forEach(function (ev) {
    dropzone.addEventListener(ev, function (e) {
      e.preventDefault();
      dropzone.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach(function (ev) {
    dropzone.addEventListener(ev, function (e) {
      e.preventDefault();
      dropzone.classList.remove("dragover");
    });
  });
  dropzone.addEventListener("drop", function (e) {
    if (e.dataTransfer.files.length) {
      fileInput.files = e.dataTransfer.files;
      updateFileList();
    }
  });

  // ---- Recording ----
  btnRec.addEventListener("click", async function () {
    if (recording) {
      mediaRecorder.stop();
      return;
    }
    if (!speaker()) { flash("Спочатку вкажіть ім'я спікера", "error"); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recChunks = [];
      mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.ondataavailable = function (e) {
        if (e.data.size > 0) recChunks.push(e.data);
      };
      mediaRecorder.onstop = function () {
        stream.getTracks().forEach(function (t) { t.stop(); });
        recBlob = new Blob(recChunks, { type: mediaRecorder.mimeType || "audio/webm" });
        recPreview.src = URL.createObjectURL(recBlob);
        recPreview.classList.remove("hidden");
        recActions.classList.remove("hidden");
        recStatus.textContent = "Запис готовий (" + (recBlob.size / 1024).toFixed(1) + " KB)";
        btnRec.textContent = "🔴 Запис";
        btnRec.classList.remove("recording");
        recording = false;
      };
      mediaRecorder.start();
      recording = true;
      btnRec.textContent = "⏹ Стоп";
      btnRec.classList.add("recording");
      recStatus.textContent = "Запис… говоріть 3–10 секунд";
      recActions.classList.add("hidden");
      recPreview.classList.add("hidden");
      recCheckResult.textContent = "";
    } catch (err) {
      flash("Немає доступу до мікрофона: " + err, "error");
    }
  });

  btnRecDiscard.addEventListener("click", function () {
    recBlob = null;
    recPreview.removeAttribute("src");
    recPreview.classList.add("hidden");
    recActions.classList.add("hidden");
    recStatus.textContent = "Запис скасовано";
    recCheckResult.textContent = "";
  });

  btnRecCheck.addEventListener("click", function () {
    if (!recBlob) return;
    var kb = recBlob.size / 1024;
    var msg;
    if (kb < 5) {
      msg = "❌ Занадто короткий/тихий — краще перезаписати (3–10 сек).";
    } else if (kb < 15) {
      msg = "⚠ Короткий зразок. Можна зберегти, але краще довший.";
    } else {
      msg = "✅ Розмір нормальний. Можна зберегти.";
    }
    recCheckResult.textContent = msg;
  });

  btnRecSave.addEventListener("click", async function () {
    if (!recBlob) return;
    if (!speaker()) { flash("Вкажіть ім'я спікера", "error"); return; }
    btnRecSave.disabled = true;
    var form = new FormData();
    form.append("speaker", speaker());
    form.append("audio", recBlob, "recording.webm");
    try {
      var res = await fetch("./upload_recording", { method: "POST", body: form });
      var data = await res.json();
      if (data.ok) {
        flash(data.message || "Збережено", "success");
        btnRecDiscard.click();
        await refreshStatus();
      } else {
        flash(data.message || "Помилка", "error");
      }
    } catch (err) {
      flash("Помилка: " + err, "error");
    } finally {
      btnRecSave.disabled = false;
    }
  });

  // ---- Upload files ----
  btnUpload.addEventListener("click", async function () {
    if (!speaker()) { flash("Вкажіть ім'я спікера", "error"); return; }
    if (!fileInput.files || fileInput.files.length === 0) {
      flash("Виберіть файли", "error"); return;
    }
    btnUpload.disabled = true;
    var form = new FormData();
    form.append("speaker", speaker());
    Array.from(fileInput.files).forEach(function (f) { form.append("files", f); });
    try {
      var res = await fetch("./upload", { method: "POST", body: form });
      var data = await res.json();
      if (data.ok) {
        flash(data.message || "Завантажено", "success");
        fileInput.value = "";
        fileList.innerHTML = "";
        await refreshStatus();
      } else flash(data.message || "Помилка", "error");
    } catch (err) {
      flash("Помилка: " + err, "error");
    } finally {
      btnUpload.disabled = false;
    }
  });

  // ---- Quality check all ----
  btnCheckAll.addEventListener("click", async function () {
    var sp = speaker() || enrollSpeaker.value.trim().toLowerCase();
    if (!sp) { flash("Вкажіть ім'я спікера", "error"); return; }
    btnCheckAll.disabled = true;
    qualityBox.classList.remove("hidden");
    qualityBox.innerHTML = "<p class=\"empty\">Перевірка…</p>";
    try {
      var form = new FormData();
      form.append("speaker", sp);
      var res = await fetch("./api/check_quality", { method: "POST", body: form });
      var data = await res.json();
      if (!data.scores || !data.scores.length) {
        qualityBox.innerHTML = "<p class=\"empty\">" + (data.message || "Немає зразків") + "</p>";
      } else {
        var html = "<ul class=\"quality-list\">";
        data.scores.forEach(function (s) {
          var badge = s.quality === "ok" ? "ok" : (s.quality === "weak" ? "weak" : "bad");
          html += "<li class=\"q-" + badge + "\"><strong>" + s.file + "</strong> — " +
            (s.note || s.quality) + " (" + s.size_kb + " KB)</li>";
        });
        html += "</ul>";
        if (data.recommendation) {
          html += "<p class=\"hint\">" + data.recommendation + "</p>";
        }
        qualityBox.innerHTML = html;
      }
    } catch (err) {
      qualityBox.innerHTML = "<p class=\"empty\">Помилка: " + err + "</p>";
    } finally {
      btnCheckAll.disabled = false;
    }
  });

  // ---- Enroll ----
  btnEnroll.addEventListener("click", async function () {
    var sp = (enrollSpeaker.value || "").trim().toLowerCase();
    if (!sp) { alert("Вкажіть ім'я спікера"); return; }
    btnEnroll.disabled = true;
    btnEnroll.textContent = "⏳ Обробка…";
    enrollLog.classList.remove("hidden", "ok", "err");
    enrollLog.textContent = "Запуск enrollment…\n";
    try {
      var form = new FormData();
      form.append("speaker", sp);
      var res = await fetch("./enroll", { method: "POST", body: form });
      var data = await res.json();
      enrollLog.textContent = data.log || "(немає виводу)";
      enrollLog.classList.add(data.ok ? "ok" : "err");
      if (data.ok) {
        restartBanner.classList.remove("hidden");
        await refreshStatus();
      }
    } catch (err) {
      enrollLog.textContent = "Помилка: " + err;
      enrollLog.classList.add("err");
    } finally {
      btnEnroll.disabled = false;
      btnEnroll.textContent = "▶ Запустити enrollment";
    }
  });

  btnRestart.addEventListener("click", async function () {
    btnRestart.disabled = true;
    btnRestart.textContent = "⏳…";
    try {
      var res = await fetch("./api/restart", { method: "POST" });
      var data = await res.json();
      flash(data.message || (data.ok ? "Restart…" : "Помилка"), data.ok ? "success" : "error");
    } catch (err) {
      flash("Помилка restart: " + err + " — зробіть Restart вручну на сторінці аддона.", "error");
    } finally {
      btnRestart.disabled = false;
      btnRestart.textContent = "🔄 Restart аддона";
    }
  });

  // ---- Scan ----
  btnScan.addEventListener("click", async function () {
    btnScan.disabled = true;
    btnScan.textContent = "⏳ Сканування…";
    scanResults.classList.remove("hidden");
    scanResults.innerHTML = "<p class=\"empty\">Перевірка…</p>";
    try {
      var res = await fetch("./api/scan_stt");
      var data = await res.json();
      if (!data.found || !data.found.length) {
        scanResults.innerHTML =
          "<p class=\"empty\">Нічого не знайдено. Спробуйте tcp://homeassistant:10300</p>";
      } else {
        var html = "<ul class=\"scan-list\">";
        data.found.forEach(function (item) {
          var badge = item.current ? ' <span class="badge current">поточний</span>' : "";
          var wok = item.wyoming_ok ? "✓" : "?";
          html += "<li><code class=\"uri\">" + item.uri + "</code> " + wok + badge +
            ' <button type="button" class="btn small" data-copy="' + item.uri +
            '">Копіювати</button></li>';
        });
        html += "</ul>";
        if (data.hint) html += "<p class=\"hint\">" + data.hint + "</p>";
        scanResults.innerHTML = html;
        scanResults.querySelectorAll("[data-copy]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var uri = btn.dataset.copy;
            if (navigator.clipboard && navigator.clipboard.writeText) {
              navigator.clipboard.writeText(uri).then(function () {
                flash("Скопійовано: " + uri, "success");
              });
            } else flash("URI: " + uri, "success");
          });
        });
      }
    } catch (err) {
      scanResults.innerHTML = "<p class=\"empty\">Помилка: " + err + "</p>";
    } finally {
      btnScan.disabled = false;
      btnScan.textContent = "🔍 Сканувати Wyoming STT";
    }
  });

  async function refreshStatus() {
    try {
      var res = await fetch("./api/status");
      var data = await res.json();
      renderEnrollment(data.enrollment || []);
      renderVoiceprints(data.voiceprints || []);
      if (data.upstream_uri) currentUpstream.textContent = data.upstream_uri;
    } catch (err) { console.error(err); }
  }

  function renderEnrollment(list) {
    var el = $("enrollment-list");
    if (!list.length) {
      el.innerHTML = '<p class="empty">Поки немає зразків.</p>';
      return;
    }
    var html = "";
    list.forEach(function (s) {
      html += "<div class=\"speaker-block\"><strong>" + s.name + "</strong> (" + s.count + ")";
      html += ' <button type="button" class="btn small danger" data-del-samples="' + s.name + '">Видалити всі</button>';
      html += "<ul class=\"file-clean-list\">";
      (s.files || []).forEach(function (f) {
        var name = typeof f === "string" ? f : f.name;
        var kb = typeof f === "object" && f.size_kb != null ? " (" + f.size_kb + " KB)" : "";
        html += "<li>" + name + kb +
          ' <button type="button" class="btn small danger" data-del-file="' + name +
          '" data-speaker="' + s.name + '">Видалити</button></li>';
      });
      html += "</ul></div>";
    });
    el.innerHTML = html;
    el.querySelectorAll("[data-del-samples]").forEach(function (btn) {
      btn.addEventListener("click", function () { deleteSamples(btn.dataset.delSamples); });
    });
    el.querySelectorAll("[data-del-file]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        deleteFile(btn.dataset.speaker, btn.dataset.delFile);
      });
    });
  }

  function renderVoiceprints(list) {
    var el = $("voiceprint-list");
    if (!list.length) {
      el.innerHTML = '<p class="empty">Ще немає voiceprint.</p>';
      return;
    }
    var html = '<ul class="voiceprint-list">';
    list.forEach(function (name) {
      html += '<li><span class="badge">✓</span> <strong>' + name +
        '</strong> <button type="button" class="btn small danger" data-del-vp="' +
        name + '">Видалити</button></li>';
    });
    html += "</ul>";
    el.innerHTML = html;
    el.querySelectorAll("[data-del-vp]").forEach(function (btn) {
      btn.addEventListener("click", function () { deleteVoiceprint(btn.dataset.delVp); });
    });
  }

  async function deleteSamples(sp) {
    if (!confirm("Видалити всі зразки «" + sp + "»?")) return;
    var form = new FormData();
    form.append("speaker", sp);
    await fetch("./delete_samples", { method: "POST", body: form });
    flash("Видалено зразки «" + sp + "»", "success");
    await refreshStatus();
  }

  async function deleteFile(sp, filename) {
    if (!confirm("Видалити «" + filename + "»?")) return;
    var form = new FormData();
    form.append("speaker", sp);
    form.append("filename", filename);
    var res = await fetch("./delete_file", { method: "POST", body: form });
    var data = await res.json();
    flash(data.message || (data.ok ? "Видалено" : "Помилка"), data.ok ? "success" : "error");
    await refreshStatus();
  }

  async function deleteVoiceprint(sp) {
    if (!confirm("Видалити voiceprint «" + sp + "»?")) return;
    var form = new FormData();
    form.append("speaker", sp);
    await fetch("./delete_voiceprint", { method: "POST", body: form });
    flash("Voiceprint «" + sp + "» видалено", "success");
    restartBanner.classList.remove("hidden");
    await refreshStatus();
  }

  refreshStatus();
})();
