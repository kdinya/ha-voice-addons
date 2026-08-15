(function () {
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("files");
  const fileList = document.getElementById("file-list");
  const btnUpload = document.getElementById("btn-upload");
  const btnEnroll = document.getElementById("btn-enroll");
  const btnScan = document.getElementById("btn-scan");
  const speakerInput = document.getElementById("speaker");
  const enrollSpeaker = document.getElementById("enroll-speaker");
  const enrollLog = document.getElementById("enroll-log");
  const flashBox = document.getElementById("flash-box");
  const scanResults = document.getElementById("scan-results");
  const currentUpstream = document.getElementById("current-upstream");

  function flash(msg, type) {
    flashBox.innerHTML = '<div class="flash ' + type + '">' + msg + "</div>";
    setTimeout(function () { flashBox.innerHTML = ""; }, 8000);
  }

  speakerInput.addEventListener("input", function () {
    enrollSpeaker.value = speakerInput.value.trim().toLowerCase();
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

  btnUpload.addEventListener("click", async function () {
    var speaker = (speakerInput.value || "").trim().toLowerCase();
    if (!speaker) { flash("Вкажіть ім'я спікера", "error"); return; }
    if (!fileInput.files || fileInput.files.length === 0) {
      flash("Виберіть файли", "error"); return;
    }
    btnUpload.disabled = true;
    btnUpload.textContent = "⏳ Завантаження…";
    var form = new FormData();
    form.append("speaker", speaker);
    Array.from(fileInput.files).forEach(function (f) { form.append("files", f); });
    try {
      var res = await fetch("./upload", { method: "POST", body: form });
      var data = await res.json();
      if (data.ok) {
        flash(data.message || "Завантажено", "success");
        fileInput.value = "";
        fileList.innerHTML = "";
        await refreshStatus();
      } else {
        flash(data.message || "Помилка", "error");
      }
    } catch (err) {
      flash("Помилка запиту: " + err, "error");
    } finally {
      btnUpload.disabled = false;
      btnUpload.textContent = "Завантажити";
    }
  });

  btnEnroll.addEventListener("click", async function () {
    var speaker = (enrollSpeaker.value || "").trim().toLowerCase();
    if (!speaker) { alert("Вкажіть ім'я спікера"); return; }
    btnEnroll.disabled = true;
    btnEnroll.textContent = "⏳ Обробка…";
    enrollLog.classList.remove("hidden", "ok", "err");
    enrollLog.textContent = "Запуск enrollment…\n";
    try {
      var form = new FormData();
      form.append("speaker", speaker);
      var res = await fetch("./enroll", { method: "POST", body: form });
      var data = await res.json();
      enrollLog.textContent = data.log || "(немає виводу)";
      enrollLog.classList.add(data.ok ? "ok" : "err");
      if (data.ok) await refreshStatus();
    } catch (err) {
      enrollLog.textContent = "Помилка запиту: " + err;
      enrollLog.classList.add("err");
    } finally {
      btnEnroll.disabled = false;
      btnEnroll.textContent = "▶ Запустити enrollment";
    }
  });

  btnScan.addEventListener("click", async function () {
    btnScan.disabled = true;
    btnScan.textContent = "⏳ Сканування…";
    scanResults.classList.remove("hidden");
    scanResults.innerHTML = "<p class=\"empty\">Перевірка типових хостів і портів…</p>";
    try {
      var res = await fetch("./api/scan_stt");
      var data = await res.json();
      if (!data.found || !data.found.length) {
        scanResults.innerHTML =
          "<p class=\"empty\">Нічого не знайдено. Переконайтеся, що STT-аддон запущений " +
          "і використовуйте вручну <code>tcp://homeassistant:10300</code>.</p>";
      } else {
        var html = "<ul class=\"scan-list\">";
        data.found.forEach(function (item) {
          var badge = item.current ? ' <span class="badge current">поточний</span>' : "";
          html +=
            "<li>" +
            "<code class=\"uri\">" + item.uri + "</code>" +
            badge +
            ' <button type="button" class="btn small" data-copy="' + item.uri +
            '">Копіювати</button>' +
            "</li>";
        });
        html += "</ul>";
        if (data.hint) {
          html += "<p class=\"hint\">" + data.hint + "</p>";
        }
        scanResults.innerHTML = html;
        scanResults.querySelectorAll("[data-copy]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var uri = btn.dataset.copy;
            if (navigator.clipboard && navigator.clipboard.writeText) {
              navigator.clipboard.writeText(uri).then(function () {
                flash("Скопійовано: " + uri, "success");
              });
            } else {
              flash("URI: " + uri, "success");
            }
          });
        });
      }
    } catch (err) {
      scanResults.innerHTML = "<p class=\"empty\">Помилка сканування: " + err + "</p>";
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
      if (data.upstream_uri) {
        currentUpstream.textContent = data.upstream_uri;
      }
    } catch (err) { console.error(err); }
  }

  function renderEnrollment(list) {
    var el = document.getElementById("enrollment-list");
    if (!list.length) {
      el.innerHTML = '<p class="empty">Поки немає завантажених зразків.</p>';
      return;
    }
    var html = '<div class="table-wrap"><table><thead><tr><th>Спікер</th><th>Файлів</th><th>Список</th><th></th></tr></thead><tbody>';
    list.forEach(function (s) {
      html += "<tr><td><strong>" + s.name + "</strong></td><td>" + s.count +
        '</td><td class="files">' + (s.files || []).join(", ") +
        '</td><td><button type="button" class="btn small danger" data-del-samples="' +
        s.name + '">Видалити</button></td></tr>';
    });
    html += "</tbody></table></div>";
    el.innerHTML = html;
    el.querySelectorAll("[data-del-samples]").forEach(function (btn) {
      btn.addEventListener("click", function () { deleteSamples(btn.dataset.delSamples); });
    });
  }

  function renderVoiceprints(list) {
    var el = document.getElementById("voiceprint-list");
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

  async function deleteSamples(speaker) {
    if (!confirm("Видалити всі зразки «" + speaker + "»?")) return;
    var form = new FormData();
    form.append("speaker", speaker);
    await fetch("./delete_samples", { method: "POST", body: form });
    flash("Видалено зразки «" + speaker + "»", "success");
    await refreshStatus();
  }

  async function deleteVoiceprint(speaker) {
    if (!confirm("Видалити voiceprint «" + speaker + "»?")) return;
    var form = new FormData();
    form.append("speaker", speaker);
    await fetch("./delete_voiceprint", { method: "POST", body: form });
    flash("Voiceprint «" + speaker + "» видалено", "success");
    await refreshStatus();
  }

  refreshStatus();
})();
