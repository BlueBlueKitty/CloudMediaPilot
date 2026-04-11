const pages = [
  { id: "recommend", label: "推荐" },
  { id: "search", label: "搜索" },
  { id: "settings", label: "设置" },
];

const state = {
  recommendItems: [],
  resources: [],
  settings: { c115_target_dir_id: "0" },
  tmdbContext: null,
};

const nav = document.getElementById("nav");
const statusBox = document.getElementById("status");

function setStatus(message, level = "ok") {
  statusBox.hidden = false;
  statusBox.className = "status " + level;
  statusBox.textContent = message;
  window.clearTimeout(setStatus.timer);
  setStatus.timer = window.setTimeout(() => {
    statusBox.hidden = true;
  }, 3500);
}

async function api(path, options) {
  const res = await fetch(path, {
    headers: { "content-type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.message || data.code || "HTTP " + res.status);
  }
  return res.json();
}

function formatBytes(size) {
  if (!size) return "-";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = size;
  let idx = 0;
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024;
    idx += 1;
  }
  return value.toFixed(1) + " " + units[idx];
}

function safeUrl(url, allowMagnet = false) {
  if (typeof url !== "string" || !url) return "";
  if (allowMagnet && url.startsWith("magnet:")) return url;
  try {
    const parsed = new URL(url);
    if (parsed.protocol === "http:" || parsed.protocol === "https:") return parsed.toString();
  } catch (_error) {
    return "";
  }
  return "";
}

function createCell(row, text) {
  const td = document.createElement("td");
  td.textContent = text;
  row.appendChild(td);
  return td;
}

function showPage(pageId) {
  document.querySelectorAll("[data-page]").forEach((el) => {
    el.hidden = el.dataset.page !== pageId;
  });
  nav.querySelectorAll("button").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.page === pageId);
  });
  history.replaceState(null, "", "#" + pageId);
}

function renderNav() {
  nav.textContent = "";
  pages.forEach((item) => {
    const button = document.createElement("button");
    button.textContent = item.label;
    button.dataset.page = item.id;
    button.onclick = () => showPage(item.id);
    nav.appendChild(button);
  });
}

function renderRecommendCards() {
  const root = document.getElementById("recommendGrid");
  root.textContent = "";
  if (state.recommendItems.length === 0) {
    root.innerHTML = '<div class="panel">暂无推荐内容。</div>';
    return;
  }
  state.recommendItems.forEach((item) => {
    const card = document.createElement("article");
    card.className = "poster-card";

    const img = document.createElement("img");
    img.className = "poster";
    const posterUrl = safeUrl(item.poster_url);
    img.src = posterUrl || "data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=";
    if (!posterUrl) {
      img.style.objectFit = "contain";
      img.style.padding = "12px";
    }
    img.alt = item.title || "poster";
    card.appendChild(img);

    const body = document.createElement("div");
    body.className = "body";
    const title = document.createElement("strong");
    title.textContent = item.title || "unknown";
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent =
      (item.year || "-") + " · " + (item.media_type || "unknown") + " · ⭐ " + (item.rating || "-");
    const overview = document.createElement("div");
    overview.className = "overview";
    overview.textContent = item.overview || "暂无简介";
    const btn = document.createElement("button");
    btn.textContent = "搜索资源";
    btn.onclick = async () => {
      const context = {
        tmdb_id: item.tmdb_id,
        title: item.title || "",
        year: item.year,
        media_type: item.media_type || "unknown",
      };
      applyTmdbContext(context);
      showPage("search");
      document.getElementById("resourceKeyword").value = item.title || "";
      await doResourceSearch(item.title || "", context);
    };
    body.append(title, meta, overview, btn);
    card.appendChild(body);
    root.appendChild(card);
  });
}

function filteredResources() {
  const source = document.getElementById("filterSource").value;
  const cloudType = document.getElementById("filterCloudType").value;
  const keyword = document.getElementById("filterKeyword").value.trim().toLowerCase();
  return state.resources.filter((row) => {
    const matchSource = source === "all" || row.source === source;
    const matchCloudType = cloudType === "all" || row.cloud_type === cloudType;
    const matchKeyword = keyword.length === 0 || (row.title || "").toLowerCase().includes(keyword);
    return matchSource && matchCloudType && matchKeyword;
  });
}

function renderResources() {
  const body = document.getElementById("resultBody");
  body.textContent = "";
  const rows = filteredResources();
  if (!rows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 6;
    td.textContent = "暂无资源";
    tr.appendChild(td);
    body.appendChild(tr);
    return;
  }
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    const titleCell = document.createElement("td");
    const link = document.createElement("a");
    link.href = safeUrl(row.link, true);
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = row.title || "unknown";
    titleCell.appendChild(link);
    tr.appendChild(titleCell);
    createCell(tr, row.source || "-");
    createCell(tr, row.cloud_type || "-");
    createCell(tr, formatBytes(row.size));
    createCell(tr, row.publish_time ? new Date(row.publish_time).toLocaleString() : "-");

    const actionCell = document.createElement("td");
    const btn = document.createElement("button");
    btn.textContent = "离线下载";
    btn.onclick = async () => {
      try {
        const inputDir = document.getElementById("resourceTargetDirId").value.trim();
        const targetDirId = inputDir || state.settings.c115_target_dir_id || "";
        const payload = { source_uri: row.magnet || row.link };
        if (targetDirId) payload.target_dir_id = targetDirId;
        const result = await api("/tasks/offline", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        setStatus("任务已创建: " + result.task_id);
        await loadTasks();
      } catch (error) {
        setStatus("创建任务失败: " + error.message, "warn");
      }
    };
    actionCell.appendChild(btn);
    tr.appendChild(actionCell);
    body.appendChild(tr);
  });
}

function renderTmdbContext() {
  const box = document.getElementById("tmdbContextBox");
  if (!state.tmdbContext) {
    box.hidden = true;
    box.textContent = "";
    return;
  }
  box.hidden = false;
  box.innerHTML = "";
  const label = document.createElement("span");
  label.className = "pill";
  label.textContent = "精准筛选: " + state.tmdbContext.title + (state.tmdbContext.year ? " (" + state.tmdbContext.year + ")" : "");
  const clear = document.createElement("button");
  clear.type = "button";
  clear.textContent = "清除";
  clear.onclick = () => {
    state.tmdbContext = null;
    renderTmdbContext();
  };
  box.append(label, clear);
}

function applyTmdbContext(context) {
  state.tmdbContext = context && context.title ? context : null;
  renderTmdbContext();
}

async function doRecommendSearch(query) {
  const text = query.trim();
  if (!text) {
    const hot = await api("/tmdb/trending?limit=24");
    state.recommendItems = hot.results || [];
    renderRecommendCards();
    return;
  }
  const data = await api("/tmdb/search?query=" + encodeURIComponent(text) + "&limit=24");
  state.recommendItems = data.results || [];
  renderRecommendCards();
}

async function doResourceSearch(keyword, contextOverride = null) {
  const text = keyword.trim();
  if (!text) return;
  const usePrecision = document.getElementById("useTmdbPrecision").checked;
  const context = contextOverride || (usePrecision ? state.tmdbContext : null);
  const payload = { keyword: text, limit: 200 };
  if (context && context.title) {
    payload.tmdb_context = context;
  }
  const data = await api("/search", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  state.resources = data.results || [];
  renderResources();
  setStatus("资源检索完成，共 " + data.total + " 条");
}

async function loadTasks() {
  const data = await api("/tasks?limit=50");
  const body = document.getElementById("taskBody");
  body.textContent = "";
  if (!data.tasks.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 5;
    td.textContent = "暂无任务";
    tr.appendChild(td);
    body.appendChild(tr);
    return;
  }
  data.tasks.forEach((task) => {
    const tr = document.createElement("tr");
    createCell(tr, task.task_id);
    const statusCell = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = "badge " + task.status;
    badge.textContent = task.status;
    statusCell.appendChild(badge);
    tr.appendChild(statusCell);
    createCell(tr, task.source_uri.length > 32 ? task.source_uri.slice(0, 32) + "..." : task.source_uri);
    createCell(tr, task.target_dir_id || "-");
    createCell(tr, new Date(task.created_at).toLocaleString());
    body.appendChild(tr);
  });
}

async function loadSettings() {
  const data = await api("/settings");
  state.settings = data;
  document.getElementById("enableTmdb").checked = !!data.enable_tmdb;
  document.getElementById("enableProwlarr").checked = !!data.enable_prowlarr;
  document.getElementById("enablePansou").checked = !!data.enable_pansou;

  document.getElementById("tmdbBaseUrl").value = data.tmdb_base_url || "";
  document.getElementById("prowlarrBaseUrl").value = data.prowlarr_base_url || "";
  document.getElementById("pansouBaseUrl").value = data.pansou_base_url || "";
  document.getElementById("c115BaseUrl").value = data.c115_base_url || "";
  document.getElementById("c115TargetDirId").value = data.c115_target_dir_id || "";
  document.getElementById("c115AllowedActions").value = data.c115_allowed_actions || "";
  document.getElementById("c115OfflineAddPath").value = data.c115_offline_add_path || "";
  document.getElementById("c115OfflineListPath").value = data.c115_offline_list_path || "";

  document.getElementById("tmdbApiKey").value = "";
  document.getElementById("prowlarrApiKey").value = "";
  document.getElementById("c115Cookie").value = "";

  const dirInput = document.getElementById("resourceTargetDirId");
  if (dirInput && !dirInput.value.trim()) {
    dirInput.value = data.c115_target_dir_id || "";
  }

  document.getElementById("settingsHints").textContent =
    "TMDB: " + (data.enable_tmdb ? "启用" : "禁用") + ", Key=" + (data.has_tmdb_api_key ? data.tmdb_api_key_masked : "未设置") + "\n" +
    "Prowlarr: " + (data.enable_prowlarr ? "启用" : "禁用") + ", Key=" + (data.has_prowlarr_api_key ? data.prowlarr_api_key_masked : "未设置") + "\n" +
    "PanSou: " + (data.enable_pansou ? "启用" : "禁用") + ", URL=" + (data.pansou_base_url || "-") + "\n" +
    "115 Cookie: " + (data.has_c115_cookie ? data.c115_cookie_masked : "未设置") + "\n" +
    "密钥字段默认不回显，留空表示保持现值。";
}

async function saveSettings(event) {
  event.preventDefault();
  const payload = {
    enable_tmdb: document.getElementById("enableTmdb").checked,
    enable_prowlarr: document.getElementById("enableProwlarr").checked,
    enable_pansou: document.getElementById("enablePansou").checked,
    tmdb_base_url: document.getElementById("tmdbBaseUrl").value.trim(),
    prowlarr_base_url: document.getElementById("prowlarrBaseUrl").value.trim(),
    pansou_base_url: document.getElementById("pansouBaseUrl").value.trim(),
    c115_base_url: document.getElementById("c115BaseUrl").value.trim(),
    c115_target_dir_id: document.getElementById("c115TargetDirId").value.trim(),
    c115_allowed_actions: document.getElementById("c115AllowedActions").value.trim(),
    c115_offline_add_path: document.getElementById("c115OfflineAddPath").value.trim(),
    c115_offline_list_path: document.getElementById("c115OfflineListPath").value.trim(),
  };
  const tmdbApiKey = document.getElementById("tmdbApiKey").value.trim();
  const prowlarrApiKey = document.getElementById("prowlarrApiKey").value.trim();
  const c115Cookie = document.getElementById("c115Cookie").value.trim();
  if (tmdbApiKey) payload.tmdb_api_key = tmdbApiKey;
  if (prowlarrApiKey) payload.prowlarr_api_key = prowlarrApiKey;
  if (c115Cookie) payload.c115_cookie = c115Cookie;

  await api("/settings", { method: "PUT", body: JSON.stringify(payload) });
  await loadSettings();
  setStatus("设置已保存");
}

async function testConnections() {
  const data = await api("/settings/test", {
    method: "POST",
    body: JSON.stringify({ provider: "all" }),
  });
  const text = data.results
    .map((row) => row.provider + ": " + (row.ok ? "ok" : "fail") + " (" + row.message + ")")
    .join(" | ");
  setStatus(text, data.results.every((x) => x.ok) ? "ok" : "warn");
}

function bindEvents() {
  document.getElementById("recommendForm").onsubmit = async (event) => {
    event.preventDefault();
    const query = document.getElementById("recommendQuery").value.trim();
    await doRecommendSearch(query);
  };
  document.getElementById("loadTrending").onclick = async () => {
    document.getElementById("recommendQuery").value = "";
    await doRecommendSearch("");
  };
  document.getElementById("resourceForm").onsubmit = async (event) => {
    event.preventDefault();
    const keyword = document.getElementById("resourceKeyword").value.trim();
    await doResourceSearch(keyword);
  };
  document.getElementById("filterSource").onchange = renderResources;
  document.getElementById("filterCloudType").onchange = renderResources;
  document.getElementById("filterKeyword").oninput = renderResources;
  document.getElementById("refreshTasks").onclick = loadTasks;
  document.getElementById("settingsForm").onsubmit = saveSettings;
  document.getElementById("testConnections").onclick = testConnections;
}

async function init() {
  renderNav();
  bindEvents();
  showPage(location.hash.replace("#", "") || "recommend");
  await loadSettings();
  await doRecommendSearch("");
  await loadTasks();
  renderTmdbContext();
}

init().catch((error) => setStatus("初始化失败: " + error.message, "warn"));
