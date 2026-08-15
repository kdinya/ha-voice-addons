(function () {
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("files");
  const fileList = document.getElementById("file-list");
  const btnUpload = document.getElementById("btn-upload");
  const btnEnroll = document.getElementById("btn-enroll");
  const speakerInput = document.getElementById("speaker");
  const enrollSpeaker = document.getElementById("enroll-speaker");
  const enrollLog = document.getElementById("enroll-log");
  const flashBox = document.getElementById("flash-box");

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

  async function refreshStatus() {
    try {
      var res = await fetch("./api/status");
      var data = await res.json();
      renderEnrollment(data.enrollment || []);
      renderVoiceprints(data.voiceprints || []);
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
