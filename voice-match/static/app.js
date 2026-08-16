(function () {
  const $ = (id) => document.getElementById(id);
  const speakerInput = $("speaker");
  const speakerSelect = $("speaker-select");
  const enrollSpeaker = $("enroll-speaker");
  const flashBox = $("flash-box");

  let mediaRecorder = null, recChunks = [], recBlob = null, recording = false;
  let pendingEnrollment = false;

  // --- Live silence meter ---
  let meterStream = null, meterCtx = null, meterAnalyser = null, meterData = null;
  let meterRaf = null, meterMax = 0, measuring = false, measureTimer = null;

  function flash(msg, type) {
    flashBox.innerHTML = '<div class="flash ' + type + '">' + msg + "</div>";
    setTimeout(function () { flashBox.innerHTML = ""; }, 9000);
  }

  function rmsFromAnalyser() {
    if (!meterAnalyser || !meterData) return 0;
    meterAnalyser.getByteTimeDomainData(meterData);
    // Convert 0-255 centered at 128 to approximate RMS-like level 0-400+
    var sum = 0;
    for (var i = 0; i < meterData.length; i++) {
      var v = (meterData[i] - 128) / 128;
      sum += v * v;
    }
    var rms = Math.sqrt(sum / meterData.length);
    // Scale to roughly match our server-side peak RMS range (50-400)
    return Math.min(500, Math.round(rms * 450));
  }

  function updateMeterUI(level) {
    var bar = $("meter-bar");
    var pct = Math.min(100, (level / 400) * 100);
    bar.style.width = pct + "%";
    $("meter-current").textContent = level;
    if (level > meterMax) {
      meterMax = level;
      $("meter-max").textContent = meterMax;
    }
  }

  function meterLoop() {
    var level = rmsFromAnalyser();
    updateMeterUI(level);
    meterRaf = requestAnimationFrame(meterLoop);
  }

  async function startMeter() {
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error("getUserMedia не підтримується в цьому контексті");
      }
      meterStream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false }
      });
      meterCtx = new (window.AudioContext || window.webkitAudioContext)();
      if (meterCtx.state === "suspended") {
        await meterCtx.resume();
      }
      var source = meterCtx.createMediaStreamSource(meterStream);
      meterAnalyser = meterCtx.createAnalyser();
      meterAnalyser.fftSize = 2048;
      source.connect(meterAnalyser);
      meterData = new Uint8Array(meterAnalyser.fftSize);
      meterMax = 0;
      $("meter-max").textContent = "0";
      $("meter-status").textContent = "Слухаю…";
      $("btn-meter-toggle").textContent = "⏹ Вимкнути індикатор";
      meterLoop();
    } catch (err) {
      var msg = (err && err.message) ? err.message : String(err);
      var name = (err && err.name) ? err.name : "";
      var hint = "";
      if (name === "NotAllowedError" || name === "PermissionDeniedError" || /permission|denied|NotAllowed/i.test(msg)) {
        hint = " Дозвіл на мікрофон заблоковано. Відкрийте цю сторінку в новій вкладці (кнопка «Відкрити в новій вкладці» біля Ingress) і дозвольте мікрофон.";
      } else if (window.self !== window.top) {
        hint = " Сторінка в iframe (HA Ingress). Часто мікрофон блокується. Відкрийте Ingress у новій вкладці браузера.";
      }
      flash("Мікрофон: " + msg + hint, "error");
      $("meter-status").textContent = "Помилка мікрофона — відкрийте в новій вкладці";
      console.error("startMeter failed", err);
    }
  }

  function stopMeter() {
    if (meterRaf) cancelAnimationFrame(meterRaf);
    meterRaf = null;
    if (measureTimer) { clearTimeout(measureTimer); measureTimer = null; }
    measuring = false;
    if (meterStream) {
      meterStream.getTracks().forEach(function (t) { t.stop(); });
      meterStream = null;
    }
    if (meterCtx) {
      try { meterCtx.close(); } catch (e) {}
      meterCtx = null;
    }
    meterAnalyser = null;
    meterData = null;
    $("meter-bar").style.width = "0%";
    $("meter-current").textContent = "—";
    $("meter-status").textContent = "Мікрофон вимкнено";
    $("btn-meter-toggle").textContent = "▶ Увімкнути індикатор";
  }

  $("btn-meter-toggle").addEventListener("click", function () {
    if (meterStream) stopMeter();
    else startMeter();
  });

  $("btn-measure-silence").addEventListener("click", async function () {
    if (measuring) return;
    $("measure-result").textContent = "Вимірювання 3 с… будь ласка, мовчіть";
    if (!meterStream) await startMeter();
    if (!meterStream) return;
    measuring = true;
    meterMax = 0;
    $("meter-max").textContent = "0";
    var start = Date.now();
    measureTimer = setTimeout(function () {
      measuring = false;
      measureTimer = null;
      var rec = "Рекомендований поріг тиші: ≈ " + Math.min(400, Math.max(80, meterMax + 40));
      $("measure-result").textContent =
        "Виміряно за 3 с — поточне ≈ " + ($("meter-current").textContent) +
        ", максимальне = " + meterMax + ". " + rec +
        ". Поставте це значення в Configuration → Поріг тиші.";
      flash("Макс під час тиші: " + meterMax + ". Рекомендований поріг ≈ " + Math.min(400, meterMax + 40), "success");
    }, 3000);
  });

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

  window.addEventListener("beforeunload", function (e) {
    if (recording || recBlob || pendingEnrollment) {
      e.preventDefault();
      e.returnValue = "";
    }
  });

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
        await refreshStatus();
        flash("Enrollment успішний. Voiceprint активний одразу (hot-reload).", "success");
      }
    } catch (e) {
      $("enroll-log").textContent = "" + e;
      $("enroll-log").classList.add("err");
    } finally {
      $("btn-enroll").disabled = false;
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
        if (!confirm("Видалити voiceprint «" + btn.dataset.delVp + "»?")) return;
        var form = new FormData(); form.append("speaker", btn.dataset.delVp);
        await fetch("./delete_voiceprint", { method: "POST", body: form });
        await refreshStatus();
        flash("Voiceprint видалено. Зміни активні одразу (hot-reload).", "success");
      });
    });
  }

  refreshStatus();
})();
