(function () {
  const $ = (id) => document.getElementById(id);
  const speakerInput = $("speaker");
  const speakerSelect = $("speaker-select");
  const enrollSpeaker = $("enroll-speaker");
  const flashBox = $("flash-box");
  const restartHint = $("restart-hint");

  let mediaRecorder = null, recChunks = [], recBlob = null, recording = false;
  let pendingEnrollment = false; // samples saved but enroll not run
  let needsRestart = false;

  function flash(msg, type) {
    flashBox.innerHTML = '<div class="flash ' + type + '">' + msg + "</div>";
    setTimeout(function () { flashBox.innerHTML = ""; }, 9000);
  }

  function setNeedsRestart(v) {
    needsRestart = !!v;
    if (needsRestart) restartHint.classList.remove("hidden");
    else restartHint.classList.add("hidden");
  }

  function currentSpeaker() {
    var fromSelect = (speakerSelect.value || "").trim().toLowerCase();
    var fromInput = (speakerInput.value || "").trim().toLowerCase();
    return fromInput || fromSelect;
  }

  function syncSpeakerFields(name) {
    name = (name || "").trim().toLowerCase();
    if (!name) return;
    speakerInput.value = name;
    enrollSpeaker.value = name;
    if ([].some.call(speakerSelect.options, function (o) { return o.value === name; })) {
      speakerSelect.value = name;
    }
  }

  speakerSelect.addEventListener("change", function () {
    if (speakerSelect.value) {
      speakerInput.value = speakerSelect.value;
      enrollSpeaker.value = speakerSelect.value;
    }
  });
  speakerInput.addEventListener("input", function () {
    enrollSpeaker.value = speakerInput.value.trim().toLowerCase();
    speakerSelect.value = "";
  });

  function fillSpeakerSelect(list) {
    var cur = speakerSelect.value;
    speakerSelect.innerHTML = '<option value="">— новий / обрати —</option>';
    (list || []).forEach(function (n) {
      var opt = document.createElement("option");
      opt.value = n;
      opt.textContent = n;
      speakerSelect.appendChild(opt);
    });
    if (cur && list && list.indexOf(cur) >= 0) speakerSelect.value = cur;
  }

  // Warn if leaving with unsaved recording or pending enrollment
  window.addEventListener("beforeunload", function (e) {
    if (recording || recBlob || pendingEnrollment) {
      e.preventDefault();
      e.returnValue = "";
    }
  });

  // files
  const fileInput = $("files"), fileList = $("file-list"), dropzone = $("dropzone");
  fileInput.addEventListener("change", function () {
    fileList.innerHTML = "";
    Array.from(fileInput.files || []).forEach(function (f) {
      var li = document.createElement("li");
      li.textContent = f.name + " (" + (f.size / 1024).toFixed(1) + " KB)";
      fileList.appendChild(li);
    });
  });
  ["dragenter", "dragover"].forEach(function (ev) {
    dropzone.addEventListener(ev, function (e) { e.preventDefault(); dropzone.classList.add("dragover"); });
  });
  ["dragleave", "drop"].forEach(function (ev) {
    dropzone.addEventListener(ev, function (e) { e.preventDefault(); dropzone.classList.remove("dragover"); });
  });
  dropzone.addEventListener("drop", function (e) {
    if (e.dataTransfer.files.length) { fileInput.files = e.dataTransfer.files; fileInput.dispatchEvent(new Event("change")); }
  });

  $("btn-upload").addEventListener("click", async function () {
    var sp = currentSpeaker();
    if (!sp) { flash("Оберіть або введіть спікера", "error"); return; }
    if (!fileInput.files || !fileInput.files.length) { flash("Виберіть файли", "error"); return; }
    syncSpeakerFields(sp);
    var form = new FormData();
    form.append("speaker", sp);
    Array.from(fileInput.files).forEach(function (f) { form.append("files", f); });
    try {
      var res = await fetch("./upload", { method: "POST", body: form });
      var data = await res.json();
      flash(data.message || (data.ok ? "OK" : "Помилка"), data.ok ? "success" : "error");
      if (data.ok) {
        fileInput.value = "";
        fileList.innerHTML = "";
        pendingEnrollment = true;
        await refreshStatus();
      }
    } catch (e) { flash("" + e, "error"); }
  });

  // record
  $("btn-rec").addEventListener("click", async function () {
    if (recording) { mediaRecorder.stop(); return; }
    if (!currentSpeaker()) { flash("Оберіть або введіть спікера", "error"); return; }
    try {
      var stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recChunks = [];
      mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.ondataavailable = function (e) { if (e.data.size) recChunks.push(e.data); };
      mediaRecorder.onstop = function () {
        stream.getTracks().forEach(function (t) { t.stop(); });
        recBlob = new Blob(recChunks, { type: mediaRecorder.mimeType || "audio/webm" });
        $("rec-preview").src = URL.createObjectURL(recBlob);
        $("rec-preview").classList.remove("hidden");
        $("rec-actions").classList.remove("hidden");
        $("rec-status").textContent = "Готово (" + (recBlob.size / 1024).toFixed(1) + " KB webm → буде WAV)";
        $("btn-rec").textContent = "🔴 Запис";
        $("btn-rec").classList.remove("recording");
        recording = false;
      };
      mediaRecorder.start();
      recording = true;
      $("btn-rec").textContent = "⏹ Стоп";
      $("btn-rec").classList.add("recording");
      $("rec-status").textContent = "Запис… 3–10 секунд";
      $("rec-actions").classList.add("hidden");
      $("rec-preview").classList.add("hidden");
      $("rec-check-result").textContent = "";
    } catch (err) { flash("Мікрофон: " + err, "error"); }
  });

  $("btn-rec-discard").addEventListener("click", function () {
    recBlob = null;
    $("rec-preview").removeAttribute("src");
    $("rec-preview").classList.add("hidden");
    $("rec-actions").classList.add("hidden");
    $("rec-status").textContent = "Скасовано";
    $("rec-check-result").textContent = "";
  });

  $("btn-rec-check").addEventListener("click", async function () {
    if (!recBlob) return;
    $("rec-check-result").textContent = "Перевірка (конвертація + аналіз)…";
    var form = new FormData();
    form.append("audio", recBlob, "rec.webm");
    try {
      var res = await fetch("./api/analyze_blob", { method: "POST", body: form });
      var data = await res.json();
      if (!data.ok && data.quality === "bad" && !data.duration_s) {
        $("rec-check-result").textContent = "❌ " + (data.message || "Помилка аналізу");
        return;
      }
      var q = data.quality || "bad";
      var icon = q === "ok" ? "✅" : (q === "weak" ? "⚠" : "❌");
      $("rec-check-result").textContent = icon + " " + (data.note || q) +
        (data.duration_s != null ? " | " + data.duration_s + "с" : "") +
        (data.sample_rate ? " | " + data.sample_rate + "Hz" : "");
    } catch (e) {
      $("rec-check-result").textContent = "Помилка: " + e;
    }
  });

  $("btn-rec-save").addEventListener("click", async function () {
    if (!recBlob) return;
    var sp = currentSpeaker();
    if (!sp) { flash("Вкажіть спікера", "error"); return; }
    syncSpeakerFields(sp);
    var form = new FormData();
    form.append("speaker", sp);
    form.append("audio", recBlob, "recording.webm");
    try {
      var res = await fetch("./upload_recording", { method: "POST", body: form });
      var data = await res.json();
      if (data.ok) {
        var extra = data.analysis ? " — " + (data.analysis.note || data.analysis.quality) : "";
        flash((data.message || "Збережено") + extra, data.analysis && data.analysis.quality === "bad" ? "error" : "success");
        $("btn-rec-discard").click();
        pendingEnrollment = true;
        await refreshStatus();
      } else flash(data.message || "Помилка", "error");
    } catch (e) { flash("" + e, "error"); }
  });

  $("btn-check-all").addEventListener("click", async function () {
    var sp = currentSpeaker() || enrollSpeaker.value.trim().toLowerCase();
    if (!sp) { flash("Вкажіть спікера", "error"); return; }
    $("quality-box").classList.remove("hidden");
    $("quality-box").innerHTML = "<p class=\"empty\">Перевірка…</p>";
    var form = new FormData();
    form.append("speaker", sp);
    try {
      var res = await fetch("./api/check_quality", { method: "POST", body: form });
      var data = await res.json();
      if (!data.scores || !data.scores.length) {
        $("quality-box").innerHTML = "<p class=\"empty\">" + (data.message || "Немає") + "</p>";
        return;
      }
      var html = "<p class=\"hint\">" + (data.message || "") + "</p><ul class=\"quality-list\">";
      data.scores.forEach(function (s) {
        var b = s.quality === "ok" ? "ok" : (s.quality === "weak" ? "weak" : "bad");
        html += "<li class=\"q-" + b + "\"><strong>" + s.file + "</strong> — " + (s.note || s.quality);
        if (s.duration_s != null) html += " [" + s.duration_s + "с]";
        html += "</li>";
      });
      html += "</ul>";
      if (data.recommendation) html += "<p class=\"hint\">" + data.recommendation + "</p>";
      $("quality-box").innerHTML = html;
    } catch (e) {
      $("quality-box").innerHTML = "<p class=\"empty\">" + e + "</p>";
    }
  });

  $("btn-enroll").addEventListener("click", async function () {
    var sp = (enrollSpeaker.value || currentSpeaker() || "").trim().toLowerCase();
    if (!sp) { alert("Вкажіть спікера перед Enrollment."); return; }
    if (pendingEnrollment === false) {
      // still allow re-enroll
    }
    $("btn-enroll").disabled = true;
    $("enroll-log").classList.remove("hidden", "ok", "err");
    $("enroll-log").textContent = "Enrollment…\n";
    var form = new FormData();
    form.append("speaker", sp);
    try {
      var res = await fetch("./enroll", { method: "POST", body: form });
      var data = await res.json();
      $("enroll-log").textContent = data.log || "";
      $("enroll-log").classList.add(data.ok ? "ok" : "err");
      if (data.ok) {
        pendingEnrollment = false;
        setNeedsRestart(true);
        await refreshStatus();
        flash("Enrollment успішний. Зробіть Restart аддона (кнопка нижче).", "success");
      }
    } catch (e) {
      $("enroll-log").textContent = "" + e;
      $("enroll-log").classList.add("err");
    } finally {
      $("btn-enroll").disabled = false;
    }
  });

  function setRestartStatus(msg, type) {
    var el = $("restart-status");
    if (!el) return;
    el.textContent = msg || "";
    el.classList.remove("warn");
    if (type === "warn") el.classList.add("warn");
    if (type === "ok") el.style.color = "var(--success)";
    else if (type === "err") el.style.color = "var(--danger)";
    else el.style.color = "";
  }

  $("btn-restart").addEventListener("click", async function () {
    if (pendingEnrollment && !confirm("Є збережені зразки без Enrollment. Все одно перезапустити аддон?")) {
      return;
    }
    var btn = $("btn-restart");
    btn.disabled = true;
    var prev = btn.textContent;
    btn.textContent = "⏳ Перезапуск…";
    setRestartStatus("Надсилаємо команду Restart у Supervisor…");
    try {
      var res = await fetch("./api/restart", { method: "POST" });
      var data = await res.json();
      if (data.ok) {
        setNeedsRestart(false);
        setRestartStatus("✓ " + (data.message || "Restart надіслано. Зачекайте 5–15 с — сторінка може оновитися сама."), "ok");
        flash(data.message || "Restart надіслано", "success");
      } else {
        setRestartStatus("✗ " + (data.message || "Не вдалося"), "err");
        flash(data.message || "Помилка Restart", "error");
      }
    } catch (e) {
      setRestartStatus("✗ Авто-restart не вдався. Відкрийте сторінку аддона.", "err");
      flash("Авто-restart не вдався. Відкрийте сторінку аддона і натисніть Restart. " + e, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = prev;
    }
  });

  $("btn-addon-page").addEventListener("click", async function () {
    setRestartStatus("Шукаємо адресу сторінки аддона…");
    var paths = [
      "/config/app/voice_match/info",
      "/hassio/addon/voice_match/info",
    ];
    try {
      var res = await fetch("./api/addon_info");
      var data = await res.json();
      if (data.paths && data.paths.length) paths = data.paths.concat(paths);
      if (data.slug) {
        paths.unshift("/config/app/" + data.slug + "/info");
        paths.unshift("/hassio/addon/" + data.slug + "/info");
      }
    } catch (e) { /* use defaults */ }

    // unique preserve order
    var seen = {}, uniq = [];
    paths.forEach(function (p) {
      if (!seen[p]) { seen[p] = true; uniq.push(p); }
    });

    // Prefer modern /config/app/ path first if slug looks like hash_slug
    uniq.sort(function (a, b) {
      var sa = a.indexOf("/config/app/") === 0 ? 0 : 1;
      var sb = b.indexOf("/config/app/") === 0 ? 0 : 1;
      return sa - sb;
    });

    var target = uniq[0];
    setRestartStatus("Перехід: " + target);
    try {
      if (window.top && window.top !== window) {
        window.top.location.href = target;
      } else {
        window.location.href = target;
      }
    } catch (e) {
      // cross-origin — open in same tab via relative root
      window.open(target, "_top");
    }
  });

  $("btn-scan").addEventListener("click", async function () {
    $("scan-results").classList.remove("hidden");
    $("scan-results").innerHTML = "<p class=\"empty\">Сканування…</p>";
    try {
      var res = await fetch("./api/scan_stt");
      var data = await res.json();
      if (!data.found || !data.found.length) {
        $("scan-results").innerHTML = "<p class=\"empty\">Нічого не знайдено. Спробуйте tcp://homeassistant:10300 у Configuration.</p>";
        return;
      }
      var html = "<ul class=\"scan-list\">";
      data.found.forEach(function (item) {
        html += "<li><code class=\"uri\">" + item.uri + "</code> " +
          (item.wyoming_ok ? "✓" : "?") +
          (item.current ? ' <span class="badge current">поточний</span>' : "") +
          ' <button type="button" class="btn small secondary" data-copy="' + item.uri + '">Копіювати</button></li>';
      });
      html += "</ul>";
      $("scan-results").innerHTML = html;
      $("scan-results").querySelectorAll("[data-copy]").forEach(function (btn) {
        btn.addEventListener("click", function () {
          navigator.clipboard.writeText(btn.dataset.copy).then(function () {
            flash("Скопійовано: " + btn.dataset.copy, "success");
          });
        });
      });
    } catch (e) {
      $("scan-results").innerHTML = "<p class=\"empty\">" + e + "</p>";
    }
  });

  async function refreshStatus() {
    try {
      var res = await fetch("./api/status");
      var data = await res.json();
      fillSpeakerSelect(data.speakers || []);
      renderEnrollment(data.enrollment || []);
      renderVoiceprints(data.voiceprints || []);
      if (data.upstream_uri) $("current-upstream").textContent = data.upstream_uri;
      // if there are samples but no matching voiceprint for that speaker — pending
      var speakersWithSamples = (data.enrollment || []).map(function (s) { return s.name; });
      var vps = data.voiceprints || [];
      if (speakersWithSamples.some(function (n) { return vps.indexOf(n) < 0; })) {
        pendingEnrollment = true;
      }
    } catch (e) { console.error(e); }
  }

  function renderEnrollment(list) {
    var el = $("enrollment-list");
    if (!list.length) { el.innerHTML = '<p class="empty">Немає зразків. Запишіть або завантажте аудіо.</p>'; return; }
    var html = "";
    list.forEach(function (s) {
      html += '<div class="speaker-block">';
      html += '<div class="speaker-head"><strong>' + s.name + '</strong> <span class="hint" style="margin:0">(' + s.count + ')</span>';
      html += ' <button type="button" class="btn small danger" data-del-samples="' + s.name + '">🗑 Видалити всі</button></div>';
      html += '<ul class="file-clean-list">';
      (s.files || []).forEach(function (f) {
        var name = typeof f === "string" ? f : f.name;
        var kb = typeof f === "object" && f.size_kb != null ? " (" + f.size_kb + " KB)" : "";
        html += '<li><span class="file-name">' + name + kb + '</span>' +
          '<button type="button" class="btn small danger" data-del-file="' + name +
          '" data-speaker="' + s.name + '">🗑 Видалити</button></li>';
      });
      html += "</ul></div>";
    });
    el.innerHTML = html;
    el.querySelectorAll("[data-del-samples]").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        if (!confirm("Видалити всі зразки «" + btn.dataset.delSamples + "»?")) return;
        var form = new FormData(); form.append("speaker", btn.dataset.delSamples);
        await fetch("./delete_samples", { method: "POST", body: form });
        await refreshStatus();
      });
    });
    el.querySelectorAll("[data-del-file]").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        if (!confirm("Видалити файл «" + btn.dataset.delFile + "»?")) return;
        var form = new FormData();
        form.append("speaker", btn.dataset.speaker);
        form.append("filename", btn.dataset.delFile);
        await fetch("./delete_file", { method: "POST", body: form });
        await refreshStatus();
      });
    });
  }

  function renderVoiceprints(list) {
    var el = $("voiceprint-list");
    if (!list.length) { el.innerHTML = '<p class="empty">Немає voiceprint. Зробіть Enrollment після зразків.</p>'; return; }
    var html = '<ul class="voiceprint-list">';
    list.forEach(function (name) {
      html += '<li><span class="badge">✓</span> <span class="vp-name"><strong>' + name +
        '</strong></span> <button type="button" class="btn small danger" data-del-vp="' + name + '">🗑 Видалити</button></li>';
    });
    html += "</ul>";
    el.innerHTML = html;
    el.querySelectorAll("[data-del-vp]").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        if (!confirm("Видалити voiceprint «" + btn.dataset.delVp + "»? Після цього потрібен Restart.")) return;
        var form = new FormData(); form.append("speaker", btn.dataset.delVp);
        await fetch("./delete_voiceprint", { method: "POST", body: form });
        setNeedsRestart(true);
        await refreshStatus();
      });
    });
  }

  refreshStatus();
})();
