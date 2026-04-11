const state = {
  recommendItems: [],
  recommendSource: "tmdb",
  recommendCategory: "trend_day",
  recommendCategories: { tmdb: [], douban: [] },
  recommendSearchMode: false,
  tmdbSearchCache: new Map(),

  resources: [],
  filtered: [],
  renderedCount: 0,
  pageSize: 30,
  sourceFilter: "all",
  cloudTypeFilter: "all",
  sortBy: "score_desc",
  resultView: "list",

  settings: {
    c115_target_dir_id: "0",
    c115_target_dir_path: "/",
  },
  secretMasks: {
    tmdb: "",
    prowlarr: "",
    c115: "",
    pansou: "",
    system: "",
    quark: "",
    tianyi: "",
    pan123: "",
  },

  pansouCloudTypes: [],
  imageMode: "direct",
  pendingTransferRow: null,
  dirPicker: {
    stack: [{ id: "0", path: "/" }],
    provider: "115",
    sourceUri: "",
    onConfirm: null,
  },
  transfer: {
    sourceUri: "",
    provider: "",
    selectedIds: [],
    items: [],
    title: "",
    stack: [{ id: "", name: "全部资源" }],
    defaultDirId: "0",
    defaultDirPath: "/",
  },
};

const PANSOU_CLOUD_TYPE_OPTIONS = [
  ["baidu", "百度网盘"],
  ["quark", "夸克网盘"],
  ["aliyun", "阿里云盘"],
  ["tianyi", "天翼云盘"],
  ["123", "123网盘"],
  ["uc", "UC网盘"],
  ["115", "115网盘"],
  ["mobile", "移动云盘"],
  ["xunlei", "迅雷网盘"],
  ["magnet", "磁力"],
  ["ed2k", "ed2k"],
];

const IMG_FALLBACK =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="600">' +
      '<rect width="100%" height="100%" fill="#1b2f50"/>' +
      '<text x="50%" y="50%" fill="#9fb7da" font-size="22" text-anchor="middle">Poster</text>' +
    "</svg>"
  );

const statusBox = document.getElementById("status");
const nav = document.getElementById("nav");

function setStatus(message, level = "ok") {
  statusBox.hidden = false;
  statusBox.className = "status " + level;
  statusBox.textContent = message;
  clearTimeout(setStatus.timer);
  setStatus.timer = setTimeout(() => {
    statusBox.hidden = true;
  }, 4200);
}

function setTransferToast(message, level = "ok") {
  const el = document.getElementById("transferToast");
  if (!el) return;
  el.hidden = false;
  el.className = "transfer-toast " + (level === "warn" ? "warn" : "");
  el.textContent = message;
  clearTimeout(setTransferToast.timer);
  setTransferToast.timer = setTimeout(() => {
    el.hidden = true;
  }, 3800);
}

async function api(path, options) {
  const res = await fetch(path, {
    headers: { "content-type": "application/json" },
    credentials: "include",
    ...options,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || data.message || data.code || "HTTP " + res.status);
  }
  return res.json();
}

function setButtonLoading(btn, loading) {
  if (!btn) return;
  btn.disabled = !!loading;
  btn.classList.toggle("loading", !!loading);
}

async function runWithButtonLoading(btn, fn) {
  setButtonLoading(btn, true);
  try {
    return await fn();
  } finally {
    setButtonLoading(btn, false);
  }
}

function escapeHtml(input) {
  return String(input || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function getImageMode() {
  const selected = document.querySelector('input[name="imgMode"]:checked');
  return selected ? selected.value : "direct";
}

function posterSrc(url) {
  if (!url) return IMG_FALLBACK;
  if (getImageMode() === "proxy") {
    return "/tmdb/image?url=" + encodeURIComponent(url);
  }
  return url;
}

function getRecommendCacheKey(source, category) {
  return `cmp_recommend_cache_v3:${source}:${category}`;
}

function getRecommendCache(source, category) {
  try {
    const raw = localStorage.getItem(getRecommendCacheKey(source, category));
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || !Array.isArray(parsed.items) || !parsed.ts) return null;
    if (Date.now() - parsed.ts > 6 * 3600 * 1000) return null;
    return parsed.items;
  } catch {
    return null;
  }
}

function setRecommendCache(source, category, items) {
  try {
    localStorage.setItem(
      getRecommendCacheKey(source, category),
      JSON.stringify({ ts: Date.now(), items: items || [] })
    );
  } catch {}
}

function clearRecommendCache(source, category) {
  try {
    localStorage.removeItem(getRecommendCacheKey(source, category));
  } catch {}
}

function mediaTypeLabel(type) {
  if (type === "movie") return "电影";
  if (type === "series") return "剧集";
  return "影视";
}

function cloudTypeName(value) {
  const map = {
    magnet: "磁力",
    quark: "夸克",
    tianyi: "天翼",
    123: "123",
    "115": "115",
    other: "其他",
    ed2k: "ed2k",
    mobile: "移动",
    xunlei: "迅雷",
    baidu: "百度",
    aliyun: "阿里",
    uc: "UC",
  };
  return map[value] || "其他";
}

function showPage(pageId) {
  document.querySelectorAll("section[data-page]").forEach((el) => {
    el.hidden = el.dataset.page !== pageId;
  });
  nav.querySelectorAll("button").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.page === pageId);
  });
  if (pageId === "recommend") {
    loadRecommend().catch((error) => setStatus("加载推荐失败：" + error.message, "warn"));
  }
  history.replaceState(null, "", "#" + pageId);
}

function renderRecommendGrid(items) {
  const root = document.getElementById("recommendGrid");
  root.textContent = "";
  if (!items.length) {
    root.innerHTML = '<div class="card">暂无内容</div>';
    return;
  }
  items.forEach((item) => {
    const card = document.createElement("article");
    card.className = "trend-card";
    const tags = [];
    const isValidText = (v) => !!v && !String(v).includes("未知");
    if (item.year) tags.push(String(item.year));
    if (isValidText(item.country)) tags.push(String(item.country));
    if (isValidText(item.language)) tags.push(String(item.language).toUpperCase());
    if (item.episodes) tags.push(`${item.episodes}集`);
    if (state.recommendSource === "douban" && isValidText(item.overview)) tags.push(String(item.overview));
    card.innerHTML = `
      <div class="poster-wrap">
        <img alt="${escapeHtml(item.title)}" src="${escapeHtml(posterSrc(item.poster_url))}" />
        <span class="badge-type">${mediaTypeLabel(item.media_type)}</span>
        <span class="badge-score">★ ${item.rating || "-"}</span>
        <button type="button" class="poster-search-btn" title="搜索资源">🔍</button>
      </div>
      <div class="trend-body">
        <div class="trend-title">${escapeHtml(item.title)}</div>
        <div class="trend-meta">${tags.map((x) => `<span class="tag">${escapeHtml(x)}</span>`).join("")}</div>
      </div>
    `;
    const poster = card.querySelector("img");
    poster.onerror = () => {
      poster.onerror = null;
      poster.src = IMG_FALLBACK;
    };
    card.querySelector(".poster-search-btn").onclick = async () => {
      document.getElementById("resourceKeyword").value = item.title || "";
      showPage("search");
      setStatus("正在搜索资源...");
      await doResourceSearch(item.title || "", document.getElementById("resourceSearchBtn"));
    };
    root.appendChild(card);
  });
}

function updateRecommendCategoryOptions() {
  const select = document.getElementById("recommendCategory");
  const rows = state.recommendCategories[state.recommendSource] || [];
  select.innerHTML = "";
  rows.forEach((row) => {
    const opt = document.createElement("option");
    opt.value = row.id;
    opt.textContent = row.name;
    select.appendChild(opt);
  });
  if (!rows.find((x) => x.id === state.recommendCategory)) {
    state.recommendCategory = rows[0]?.id || "";
  }
  select.value = state.recommendCategory;
}

async function loadRecommendCategories() {
  const data = await api("/recommend/categories");
  state.recommendCategories = data;
  updateRecommendCategoryOptions();
}

function currentRecommendCategoryName() {
  const rows = state.recommendCategories[state.recommendSource] || [];
  return rows.find((x) => x.id === state.recommendCategory)?.name || "推荐结果";
}

async function loadRecommend(forceRefresh = false) {
  if (!state.recommendCategories.tmdb.length) {
    await loadRecommendCategories();
  }
  if (state.recommendSearchMode) return;

  const source = state.recommendSource;
  const category = state.recommendCategory;
  const cached = forceRefresh ? null : getRecommendCache(source, category);
  if (cached) {
    state.recommendItems = cached;
    document.getElementById("recommendSectionTitle").textContent = currentRecommendCategoryName();
    renderRecommendGrid(cached);
    return;
  }
  let items = [];

  if (source === "tmdb") {
    if (category === "trend_day") {
      items = (await api("/tmdb/trending?timeframe=day&limit=120")).results || [];
    } else if (category === "trend_week") {
      items = (await api("/tmdb/trending?timeframe=week&limit=120")).results || [];
    } else {
      items = (await api(`/tmdb/discover?category=${encodeURIComponent(category)}&limit=120`)).results || [];
    }
  } else {
    const [mediaType, tag] = category.split("|");
    items = (
      await api(
        `/douban/hot?media_type=${encodeURIComponent(mediaType || "movie")}&tag=${encodeURIComponent(tag || "热门")}&page_start=0&page_limit=100`
      )
    ).results || [];
  }

  state.recommendItems = items;
  setRecommendCache(source, category, items);
  document.getElementById("recommendSectionTitle").textContent = currentRecommendCategoryName();
  renderRecommendGrid(items);
}

async function doRecommendSearch(_, buttonEl) {
  const query = document.getElementById("recommendQuery").value.trim();
  if (!query) {
    state.recommendSearchMode = false;
    await loadRecommend();
    return;
  }
  await runWithButtonLoading(buttonEl, async () => {
    setStatus("正在搜索推荐...");
    const key = query.toLowerCase();
    if (state.tmdbSearchCache.has(key)) {
      state.recommendSearchMode = true;
      state.recommendItems = state.tmdbSearchCache.get(key);
      document.getElementById("recommendSectionTitle").textContent = `TMDB搜索：${query}`;
      renderRecommendGrid(state.recommendItems);
      setStatus("已命中TMDB搜索缓存");
      return;
    }
    const data = await api(`/tmdb/search?query=${encodeURIComponent(query)}&limit=120`);
    state.recommendSearchMode = true;
    state.recommendItems = data.results || [];
    state.tmdbSearchCache.set(key, state.recommendItems);
    document.getElementById("recommendSectionTitle").textContent = `TMDB搜索：${query}`;
    renderRecommendGrid(state.recommendItems);
  });
}

function renderSummary() {
  const total = state.resources.length;
  const filtered = state.filtered.length;
  const sourceMap = {};
  const cloudMap = {};
  state.resources.forEach((row) => {
    sourceMap[row.source || "unknown"] = (sourceMap[row.source || "unknown"] || 0) + 1;
    cloudMap[row.cloud_type || "other"] = (cloudMap[row.cloud_type || "other"] || 0) + 1;
  });

  const sourceText = Object.entries(sourceMap)
    .map(([k, v]) => `${k}:${v}`)
    .join(" / ");
  const cloudText = Object.entries(cloudMap)
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => `${cloudTypeName(k)}:${v}`)
    .join(" / ");

  document.getElementById("resultSummary").innerHTML = `
    <div class="summary-item"><div class="k">总结果</div><div class="v">${total}</div></div>
    <div class="summary-item"><div class="k">当前筛选</div><div class="v">${filtered}</div></div>
    <div class="summary-item"><div class="k">来源分布</div><div class="v">${escapeHtml(sourceText || "-")}</div></div>
    <div class="summary-item"><div class="k">网盘分布</div><div class="v">${escapeHtml(cloudText || "-")}</div></div>
  `;
}

function applyFilters() {
  let rows = state.resources.slice();
  if (state.sourceFilter !== "all") rows = rows.filter((row) => row.source === state.sourceFilter);
  if (state.cloudTypeFilter !== "all") {
    rows = rows.filter((row) => (row.cloud_type || "other") === state.cloudTypeFilter);
  }

  rows.sort((a, b) => {
    if (state.sortBy === "size_desc") return (b.size || 0) - (a.size || 0);
    if (state.sortBy === "size_asc") return (a.size || 0) - (b.size || 0);
    if (state.sortBy === "time_desc") return new Date(b.publish_time || 0) - new Date(a.publish_time || 0);
    if (state.sortBy === "time_asc") return new Date(a.publish_time || 0) - new Date(b.publish_time || 0);
    return (b.score || 0) - (a.score || 0);
  });

  state.filtered = rows;
  state.renderedCount = 0;
  renderSummary();
  renderResourceList();
}

async function copyText(text) {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const input = document.createElement("textarea");
    input.value = text;
    document.body.appendChild(input);
    input.select();
    document.execCommand("copy");
    document.body.removeChild(input);
  }
  setStatus("复制成功");
}

function renderListItem(row) {
  const item = document.createElement("article");
  item.className = "resource-item";
  const sourceText = row.magnet || row.link || row.source_id || "-";
  item.innerHTML = `
    <div class="resource-main">
      <div class="trend-meta">
        <span class="tag">${escapeHtml(row.source || "-")}</span>
        <span class="tag">${escapeHtml(cloudTypeName(row.cloud_type || "other"))}</span>
      </div>
      <div class="resource-title">${escapeHtml(row.title || "-")}</div>
      <div class="resource-sub resource-source-line">来源：<span class="truncate-one" title="${escapeHtml(sourceText)}">${escapeHtml(sourceText)}</span><button class="btn-copy-source" type="button">复制</button></div>
    </div>
    <div class="resource-side">
      <div class="meta-line">大小/热度：${row.size ? Math.round(row.size / 1024 / 1024) + " MB" : "-"} / ${Math.round(row.score || 0)}</div>
      <div class="meta-line">时间：${row.publish_time ? new Date(row.publish_time).toLocaleString() : "-"}</div>
      <div class="resource-actions">
        <button class="btn-save" type="button">一键转存</button>
        <button class="btn-open" type="button">打开链接</button>
      </div>
    </div>
  `;
  const linkSpan = item.querySelector(".truncate-one");
  linkSpan.addEventListener("contextmenu", async (e) => {
    e.preventDefault();
    await copyText(sourceText);
  });
  item.querySelector(".btn-copy-source").onclick = (e) => {
    const btn = e.currentTarget;
    copyText(sourceText);
    const backup = btn.textContent;
    btn.textContent = "已复制";
    setTimeout(() => {
      btn.textContent = backup;
    }, 1200);
  };
  item.querySelector(".btn-save").onclick = () => openTransferModal(row);
  item.querySelector(".btn-open").onclick = () => {
    const url = row.magnet || row.link;
    if (url) window.open(url, "_blank", "noopener,noreferrer");
  };
  return item;
}

function renderPosterCard(row) {
  const card = document.createElement("article");
  card.className = "poster-result-card";
  const img = posterSrc(row.tmdb_poster || "");
  card.innerHTML = `
    <img src="${escapeHtml(img)}" alt="${escapeHtml(row.title || "-")}" />
    <div class="body">
      <div class="title">${escapeHtml(row.title || "-")}</div>
      <div class="meta">${escapeHtml(cloudTypeName(row.cloud_type || "other"))} / ${escapeHtml(row.source || "-")}</div>
      <div class="meta">${row.size ? Math.round(row.size / 1024 / 1024) + " MB" : "-"}</div>
      <div class="actions">
        <button class="btn-save" type="button">一键转存</button>
        <button class="btn-open" type="button">打开链接</button>
      </div>
    </div>
  `;
  const poster = card.querySelector("img");
  poster.onerror = () => {
    poster.onerror = null;
    poster.src = IMG_FALLBACK;
  };
  card.querySelector(".btn-save").onclick = () => openTransferModal(row);
  card.querySelector(".btn-open").onclick = () => {
    const url = row.magnet || row.link;
    if (url) window.open(url, "_blank", "noopener,noreferrer");
  };
  return card;
}

function renderResourceList() {
  const list = document.getElementById("resourceList");
  if (state.renderedCount === 0) {
    list.textContent = "";
    list.className = state.resultView === "poster" ? "poster-result-grid" : "resource-list";
  }

  if (!state.filtered.length) {
    list.className = "resource-list";
    list.innerHTML = '<div class="card">暂无搜索结果</div>';
    document.getElementById("loadMoreBtn").hidden = true;
    return;
  }

  const start = state.renderedCount;
  const end = Math.min(state.filtered.length, start + state.pageSize);
  for (let i = start; i < end; i += 1) {
    const row = state.filtered[i];
    list.appendChild(state.resultView === "poster" ? renderPosterCard(row) : renderListItem(row));
  }

  state.renderedCount = end;
  document.getElementById("loadMoreBtn").hidden = state.renderedCount >= state.filtered.length;
}

async function doResourceSearch(keyword, buttonEl) {
  const text = keyword.trim();
  if (!text) return;
  await runWithButtonLoading(buttonEl, async () => {
    setStatus("正在搜索资源...");
    const data = await api("/search", {
      method: "POST",
      body: JSON.stringify({ keyword: text, limit: 500 }),
    });
    state.resources = data.results || [];
    applyFilters();
    if (Array.isArray(data.warnings) && data.warnings.length) {
      setStatus(`检索完成 ${data.total || 0} 条；告警：${data.warnings.join("；")}`, "warn");
    } else {
      setStatus("检索完成，共 " + (data.total || 0) + " 条");
    }
  });
}

function switchSettingsTab(tabName) {
  document.querySelectorAll("#settingsTabs button").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tabName);
  });
  document.querySelectorAll("[data-tab-pane]").forEach((pane) => {
    pane.hidden = pane.dataset.tabPane !== tabName;
  });
}

function renderPansouCloudTypeSelect() {
  const select = document.getElementById("pansouCloudTypeSelect");
  select.innerHTML = "<option value=''>请选择网盘类型</option>";
  PANSOU_CLOUD_TYPE_OPTIONS.forEach(([value, label]) => {
    const op = document.createElement("option");
    op.value = value;
    op.textContent = label;
    select.appendChild(op);
  });
}

function renderPansouCloudTypeChips() {
  const root = document.getElementById("pansouCloudTypeChips");
  root.textContent = "";
  const map = Object.fromEntries(PANSOU_CLOUD_TYPE_OPTIONS);
  state.pansouCloudTypes.forEach((value) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.innerHTML = `${escapeHtml(map[value] || value)} <button type="button">×</button>`;
    chip.querySelector("button").onclick = () => {
      state.pansouCloudTypes = state.pansouCloudTypes.filter((x) => x !== value);
      syncPansouCloudTypesField();
      renderPansouCloudTypeChips();
    };
    root.appendChild(chip);
  });
}

function syncPansouCloudTypesField() {
  document.getElementById("pansouCloudTypes").value = state.pansouCloudTypes.join(",");
}

function isMaskedSecret(value) {
  return !!value && /^\*+/.test(value);
}

function showMaskedHint(elId, _label, _masked) {
  const el = document.getElementById(elId);
  if (!el) return;
  el.textContent = "";
}

function splitProxyUrl(proxyUrl) {
  const raw = (proxyUrl || "").trim();
  if (!raw) return { scheme: "http://", addr: "" };
  if (raw.startsWith("socks5://")) return { scheme: "socks5://", addr: raw.slice(9) };
  if (raw.startsWith("http://")) return { scheme: "http://", addr: raw.slice(7) };
  if (raw.startsWith("https://")) return { scheme: "http://", addr: raw.slice(8) };
  return { scheme: "http://", addr: raw };
}

function combineProxyUrl() {
  const scheme = document.getElementById("systemProxyScheme").value;
  const addr = document.getElementById("systemProxyAddr").value.trim();
  return addr ? scheme + addr : "";
}

async function loadSettings() {
  const data = await api("/settings");
  state.settings = data;
  state.imageMode = data.tmdb_use_proxy ? "proxy" : "direct";
  const modeRadio = document.querySelector(`input[name="imgMode"][value="${state.imageMode}"]`);
  if (modeRadio) modeRadio.checked = true;

  state.secretMasks.tmdb = data.tmdb_api_key_masked || "";
  state.secretMasks.prowlarr = data.prowlarr_api_key_masked || "";
  state.secretMasks.c115 = data.c115_cookie_masked || "";
  state.secretMasks.pansou = data.pansou_password_masked || "";
  state.secretMasks.system = data.system_password_masked || "";
  state.secretMasks.quark = data.quark_cookie_masked || "";
  state.secretMasks.tianyi = data.tianyi_password_masked || "";
  state.secretMasks.pan123 = data.pan123_password_masked || "";

  document.getElementById("tmdbBaseUrl").value = data.tmdb_base_url || "";
  document.getElementById("tmdbImageBaseUrl").value = data.tmdb_image_base_url || "";
  document.getElementById("tmdbApiKey").value = "";
  document.getElementById("tmdbApiKey").placeholder = "留空=保持不变";
  document.getElementById("tmdbUseProxy").checked = !!data.tmdb_use_proxy;

  document.getElementById("enablePansou").checked = !!data.enable_pansou;
  document.getElementById("pansouBaseUrl").value = data.pansou_base_url || "";
  document.getElementById("pansouSearchPath").value = data.pansou_search_path || "/api/search";
  document.getElementById("pansouSearchMethod").value = (data.pansou_search_method || "POST").toUpperCase();
  document.getElementById("pansouUseProxy").checked = !!data.pansou_use_proxy;
  document.getElementById("pansouEnableAuth").checked = !!data.pansou_enable_auth;
  document.getElementById("pansouUsername").value = data.pansou_username || "";
  document.getElementById("pansouPassword").value = "";
  document.getElementById("pansouPassword").placeholder = "留空=保持不变";
  document.getElementById("pansouSource").value = data.pansou_source || "all";
  state.pansouCloudTypes = (data.pansou_cloud_types || "")
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
  syncPansouCloudTypesField();
  renderPansouCloudTypeChips();

  document.getElementById("enableProwlarr").checked = !!data.enable_prowlarr;
  document.getElementById("prowlarrBaseUrl").value = data.prowlarr_base_url || "";
  document.getElementById("prowlarrUseProxy").checked = !!data.prowlarr_use_proxy;
  document.getElementById("prowlarrApiKey").value = "";
  document.getElementById("prowlarrApiKey").placeholder = "留空=保持不变";

  document.getElementById("c115BaseUrl").value = data.c115_base_url || "";
  document.getElementById("c115Cookie").value = "";
  document.getElementById("c115Cookie").placeholder = "留空=保持不变";
  document.getElementById("quarkCookie").value = "";
  document.getElementById("quarkCookie").placeholder = "留空=保持不变";
  document.getElementById("tianyiUsername").value = data.tianyi_username || "";
  document.getElementById("tianyiPassword").value = "";
  document.getElementById("tianyiPassword").placeholder = "留空=保持不变";
  document.getElementById("pan123Username").value = data.pan123_username || "";
  document.getElementById("pan123Password").value = "";
  document.getElementById("pan123Password").placeholder = "留空=保持不变";

  document.getElementById("systemUsername").value = data.system_username || "admin";
  document.getElementById("systemPassword").value = "";
  document.getElementById("systemPassword").placeholder = "留空=保持不变";
  document.getElementById("systemProxyEnabled").checked = !!data.system_proxy_enabled;
  const proxy = splitProxyUrl(data.system_proxy_url || "");
  document.getElementById("systemProxyScheme").value = proxy.scheme;
  document.getElementById("systemProxyAddr").value = proxy.addr;

  showMaskedHint("tmdbApiKeyHint", "TMDB Key", data.tmdb_api_key_masked || "");
  showMaskedHint("prowlarrApiKeyHint", "Prowlarr Key", data.prowlarr_api_key_masked || "");
  showMaskedHint("pansouPasswordHint", "PanSou 密码", data.pansou_password_masked || "");
  showMaskedHint("systemPasswordHint", "登录密码", data.system_password_masked || "");
}

async function saveSettings(event) {
  if (event) event.preventDefault();

  const payload = {
    tmdb_base_url: document.getElementById("tmdbBaseUrl").value.trim(),
    tmdb_image_base_url: document.getElementById("tmdbImageBaseUrl").value.trim(),
    tmdb_use_proxy: document.getElementById("tmdbUseProxy").checked,

    enable_pansou: document.getElementById("enablePansou").checked,
    pansou_base_url: document.getElementById("pansouBaseUrl").value.trim(),
    pansou_search_path: document.getElementById("pansouSearchPath").value.trim() || "/api/search",
    pansou_search_method: document.getElementById("pansouSearchMethod").value,
    pansou_cloud_types: document.getElementById("pansouCloudTypes").value.trim(),
    pansou_source: document.getElementById("pansouSource").value,
    pansou_use_proxy: document.getElementById("pansouUseProxy").checked,
    pansou_enable_auth: document.getElementById("pansouEnableAuth").checked,
    pansou_username: document.getElementById("pansouUsername").value.trim(),

    enable_prowlarr: document.getElementById("enableProwlarr").checked,
    prowlarr_base_url: document.getElementById("prowlarrBaseUrl").value.trim(),
    prowlarr_use_proxy: document.getElementById("prowlarrUseProxy").checked,

    c115_base_url: document.getElementById("c115BaseUrl").value.trim(),
    storage_providers: "115,quark,tianyi,123",
    tianyi_username: document.getElementById("tianyiUsername").value.trim(),
    pan123_username: document.getElementById("pan123Username").value.trim(),

    system_username: document.getElementById("systemUsername").value.trim(),
    system_proxy_enabled: document.getElementById("systemProxyEnabled").checked,
    system_proxy_url: combineProxyUrl(),
  };

  const tmdbApiKey = document.getElementById("tmdbApiKey").value.trim();
  const prowlarrApiKey = document.getElementById("prowlarrApiKey").value.trim();
  const c115Cookie = document.getElementById("c115Cookie").value.trim();
  const pansouPassword = document.getElementById("pansouPassword").value.trim();
  const systemPassword = document.getElementById("systemPassword").value.trim();
  const quarkCookie = document.getElementById("quarkCookie").value.trim();
  const tianyiPassword = document.getElementById("tianyiPassword").value.trim();
  const pan123Password = document.getElementById("pan123Password").value.trim();

  if (tmdbApiKey && !isMaskedSecret(tmdbApiKey)) payload.tmdb_api_key = tmdbApiKey;
  if (prowlarrApiKey && !isMaskedSecret(prowlarrApiKey)) payload.prowlarr_api_key = prowlarrApiKey;
  if (c115Cookie && !isMaskedSecret(c115Cookie)) payload.c115_cookie = c115Cookie;
  if (pansouPassword && !isMaskedSecret(pansouPassword)) payload.pansou_password = pansouPassword;
  if (systemPassword && !isMaskedSecret(systemPassword)) payload.system_password = systemPassword;
  if (quarkCookie && !isMaskedSecret(quarkCookie)) payload.quark_cookie = quarkCookie;
  if (tianyiPassword && !isMaskedSecret(tianyiPassword)) payload.tianyi_password = tianyiPassword;
  if (pan123Password && !isMaskedSecret(pan123Password)) payload.pan123_password = pan123Password;

  await api("/settings", { method: "PUT", body: JSON.stringify(payload) });
  await loadSettings();
  state.recommendSearchMode = false;
  await loadRecommend();
  setStatus("设置已保存");
}

async function testProvider(provider) {
  const resultEl = document.getElementById(`testResult-${provider}`);
  const writeResult = (text, level = "ok") => {
    if (!resultEl) return;
    resultEl.textContent = text;
    resultEl.className = "test-result " + (level === "warn" ? "warn" : "ok");
  };
  try {
    const data = await api("/settings/test", {
      method: "POST",
      body: JSON.stringify({ provider }),
    });
    const first = (data.results || [])[0];
    if (!first) {
      writeResult("测试失败：无返回", "warn");
      return;
    }
    writeResult(
      `${first.provider}：${first.ok ? "OK" : "FAIL"} (${first.message})`,
      first.ok ? "ok" : "warn"
    );
  } catch (error) {
    writeResult(`测试失败：${error.message}`, "warn");
  }
}

async function ensureAuth() {
  const auth = await api("/auth/me");
  const overlay = document.getElementById("loginOverlay");
  if (auth.authenticated) {
    overlay.hidden = true;
    return true;
  }
  overlay.hidden = false;
  return false;
}

async function doLogin(event) {
  event.preventDefault();
  const username = document.getElementById("loginUsername").value.trim();
  const password = document.getElementById("loginPassword").value;
  if (!username || !password) {
    setStatus("请输入用户名和密码", "warn");
    return;
  }
  try {
    await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    document.getElementById("loginOverlay").hidden = true;
    document.getElementById("loginPassword").value = "";
    await bootstrapAfterLogin();
    setStatus("登录成功");
  } catch (error) {
    setStatus("登录失败：" + error.message, "warn");
  }
}

async function loadDirList(parentId, provider) {
  return await api(
    `/storage/dirs?parent_id=${encodeURIComponent(parentId)}&provider=${encodeURIComponent(provider)}`
  );
}

async function loadTransferItems(parentId = "") {
  return await api("/transfer/items", {
    method: "POST",
    body: JSON.stringify({
      source_uri: state.transfer.sourceUri,
      cloud_type: state.transfer.provider,
      parent_id: parentId || "",
    }),
  });
}

async function openDirPicker(initialId, initialPath, provider, sourceUri, onConfirm) {
  const modal = document.getElementById("dirPickerModal");
  state.dirPicker.stack = [{ id: initialId || "0", path: initialPath || "/" }];
  state.dirPicker.provider = provider || "115";
  state.dirPicker.sourceUri = sourceUri || "";
  state.dirPicker.onConfirm = onConfirm;
  modal.hidden = false;
  await renderDirPicker();
}

async function renderDirPicker() {
  const current = state.dirPicker.stack[state.dirPicker.stack.length - 1];
  const listBox = document.getElementById("dirPickerList");
  document.getElementById("dirPickerPath").textContent = current.path || "/";
  listBox.innerHTML = '<div class="dir-item">加载中...</div>';
  try {
    const data = await loadDirList(current.id, state.dirPicker.provider || "115");
    current.path = data.parent_path || current.path || "/";
    document.getElementById("dirPickerPath").textContent = current.path;
    if (!data.items || !data.items.length) {
      listBox.innerHTML = '<div class="dir-item">当前目录无子目录</div>';
      return;
    }
    listBox.innerHTML = "";
    data.items.forEach((item) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "dir-item";
      btn.textContent = item.name;
      btn.onclick = async () => {
        const nextPath = (current.path === "/" ? "" : current.path) + "/" + item.name;
        state.dirPicker.stack.push({ id: item.id, path: nextPath.replaceAll("//", "/") });
        await renderDirPicker();
      };
      listBox.appendChild(btn);
    });
  } catch (error) {
    listBox.innerHTML = `<div class="dir-item">加载失败：${escapeHtml(error.message)}</div>`;
  }
}

function closeDirPicker() {
  document.getElementById("dirPickerModal").hidden = true;
  state.dirPicker.onConfirm = null;
  state.dirPicker.sourceUri = "";
}

function getLastDir(provider) {
  try {
    const raw = localStorage.getItem(`cmp_last_dir_${provider}`);
    if (!raw) return null;
    const obj = JSON.parse(raw);
    if (!obj || !obj.id) return null;
    return obj;
  } catch {
    return null;
  }
}

function setLastDir(provider, choice) {
  try {
    localStorage.setItem(`cmp_last_dir_${provider}`, JSON.stringify(choice));
  } catch {}
}

function openTransferItemsModal() {
  const modal = document.getElementById("transferItemsModal");
  modal.hidden = false;
  renderTransferItemsModal();
}

function transferItemsPath() {
  return state.transfer.stack.map((x) => x.name).join(" / ");
}

function syncCurrentTransferChecks() {
  const checked = new Set(
    Array.from(document.querySelectorAll("#transferItemsList input[type='checkbox']:checked"))
      .map((el) => el.getAttribute("data-id") || "")
      .filter(Boolean)
  );
  const visibleFileIds = new Set((state.transfer.items || []).filter((x) => !x.is_dir).map((x) => x.id));
  state.transfer.selectedIds = state.transfer.selectedIds.filter((id) => !visibleFileIds.has(id));
  state.transfer.selectedIds.push(...Array.from(checked));
}

function renderTransferItemsModal() {
  const list = document.getElementById("transferItemsList");
  document.getElementById("transferItemsTitle").textContent =
    `${state.transfer.title || "请选择要转存的资源"}：${transferItemsPath()}`;
  document.getElementById("transferItemsBackBtn").disabled = state.transfer.stack.length <= 1;
  list.innerHTML = "";
  if (!state.transfer.items.length) {
    list.innerHTML = '<div class="dir-item">当前目录没有可选择资源</div>';
    return;
  }
  state.transfer.items.forEach((item) => {
    const row = document.createElement("div");
    row.className = "dir-item transfer-item-row";
    const sizeText = item.size ? ` (${Math.round(item.size / 1024 / 1024)} MB)` : "";
    if (item.is_dir) {
      row.innerHTML = `
        <span class="transfer-item-name">📁 ${escapeHtml(item.name)}</span>
        <button type="button" class="transfer-item-enter">进入</button>
      `;
      row.querySelector("button").onclick = async () => {
        syncCurrentTransferChecks();
        list.innerHTML = '<div class="dir-item">加载中...</div>';
        try {
          const data = await loadTransferItems(item.id);
          state.transfer.items = data.items || [];
          state.transfer.stack.push({ id: item.id, name: item.name || item.id });
          renderTransferItemsModal();
        } catch (error) {
          list.innerHTML = `<div class="dir-item">加载失败：${escapeHtml(error.message)}</div>`;
        }
      };
    } else {
      const checked = state.transfer.selectedIds.includes(item.id) ? "checked" : "";
      row.innerHTML = `
        <label>
          <input type="checkbox" data-id="${escapeHtml(item.id)}" ${checked} />
          <span class="transfer-item-name">📄 ${escapeHtml(item.name)}${sizeText}</span>
        </label>
      `;
    }
    list.appendChild(row);
  });
}

function closeTransferItemsModal() {
  document.getElementById("transferItemsModal").hidden = true;
}

async function doTransferCommit(sourceUri, targetDirId, selectedIds, cloudType) {
  try {
    const result = await api("/transfer/commit", {
      method: "POST",
      body: JSON.stringify({
        source_uri: sourceUri,
        target_dir_id: targetDirId || "0",
        selected_ids: selectedIds || [],
        cloud_type: cloudType || "",
      }),
    });
    setTransferToast("转存成功，任务ID: " + result.task_id);
  } catch (error) {
    setTransferToast("转存失败: " + error.message, "warn");
  }
}

async function openTransferModal(row) {
  state.pendingTransferRow = row;
  const sourceUri = row.magnet || row.link;
  if (!sourceUri) {
    setTransferToast("该条结果没有可转存链接", "warn");
    return;
  }
  try {
    const check = await api("/tasks/offline/check", {
      method: "POST",
      body: JSON.stringify({ source_uri: sourceUri, cloud_type: row.cloud_type || "" }),
    });
    if (!check.supported || !check.configured) {
      setTransferToast(check.message || "未配置对应网盘", "warn");
      return;
    }
    const provider =
      check.provider === "magnet" || check.provider === "ed2k" ? "115" : check.provider;
    const prepared = await api("/transfer/prepare", {
      method: "POST",
      body: JSON.stringify({ source_uri: sourceUri, cloud_type: row.cloud_type || "" }),
    });
    state.transfer.sourceUri = sourceUri;
    state.transfer.provider = provider;
    state.transfer.items = prepared.items || [];
    state.transfer.selectedIds = (prepared.items || []).filter((x) => !x.is_dir).map((x) => x.id);
    state.transfer.title = prepared.title || "选择资源";
    state.transfer.stack = [{ id: "", name: "全部资源" }];
    state.transfer.defaultDirId = prepared.default_dir_id || "0";
    state.transfer.defaultDirPath = prepared.default_dir_path || "/";

    const openDirAndCommit = async () => {
      const last = getLastDir(provider);
      const dirId = last?.id || state.transfer.defaultDirId || "0";
      const dirPath = last?.path || state.transfer.defaultDirPath || "/";
      await openDirPicker(dirId, dirPath, provider, sourceUri, async (choice) => {
        setLastDir(provider, choice);
        await doTransferCommit(
          sourceUri,
          choice.id || "0",
          state.transfer.selectedIds,
          row.cloud_type || provider
        );
      });
    };

    if (prepared.selectable && state.transfer.items.length) {
      openTransferItemsModal();
      document.getElementById("transferItemsNextBtn").onclick = async () => {
        syncCurrentTransferChecks();
        if (!state.transfer.selectedIds.length) {
          setTransferToast("请至少选择一个资源", "warn");
          return;
        }
        closeTransferItemsModal();
        await openDirAndCommit();
      };
      return;
    }
    await openDirPicker(
      getLastDir(provider)?.id || check.default_dir_id || "0",
      getLastDir(provider)?.path || check.default_dir_path || "/",
      provider,
      sourceUri,
      async (choice) => {
        setLastDir(provider, choice);
        await doTransferCommit(sourceUri, choice.id || "0", [], row.cloud_type || provider);
      }
    );
  } catch (error) {
    setTransferToast("转存准备失败: " + error.message, "warn");
  }
}

function bindEvents() {
  nav.querySelectorAll("button").forEach((btn) => {
    btn.onclick = () => showPage(btn.dataset.page);
  });

  document.getElementById("recommendSearchBtn").onclick = () =>
    doRecommendSearch(undefined, document.getElementById("recommendSearchBtn"));
  document.getElementById("recommendQuery").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      document.getElementById("recommendSearchBtn").click();
    }
  });

  document.querySelectorAll('input[name="imgMode"]').forEach((radio) => {
    radio.onchange = () => renderRecommendGrid(state.recommendItems);
  });

  document.getElementById("recommendSourceTabs").querySelectorAll("button").forEach((btn) => {
    btn.onclick = async () => {
      document.getElementById("recommendSourceTabs").querySelectorAll("button").forEach((x) => x.classList.remove("active"));
      btn.classList.add("active");
      state.recommendSource = btn.dataset.source;
      state.recommendSearchMode = false;
      updateRecommendCategoryOptions();
      await loadRecommend();
    };
  });
  document.getElementById("recommendCategory").onchange = async (e) => {
    state.recommendCategory = e.target.value;
    state.recommendSearchMode = false;
    await loadRecommend();
  };
  document.getElementById("refreshRecommendBtn").onclick = async () => {
    clearRecommendCache(state.recommendSource, state.recommendCategory);
    await loadRecommend(true);
  };

  document.getElementById("resourceSearchBtn").onclick = () => {
    const keyword = document.getElementById("resourceKeyword").value.trim();
    doResourceSearch(keyword, document.getElementById("resourceSearchBtn"));
  };
  document.getElementById("resourceKeyword").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      document.getElementById("resourceSearchBtn").click();
    }
  });

  document.getElementById("sourceTabs").querySelectorAll("button").forEach((btn) => {
    btn.onclick = () => {
      document.getElementById("sourceTabs").querySelectorAll("button").forEach((x) => x.classList.remove("active"));
      btn.classList.add("active");
      state.sourceFilter = btn.dataset.source;
      applyFilters();
    };
  });

  document.getElementById("resultViewTabs").querySelectorAll("button").forEach((btn) => {
    btn.onclick = () => {
      document.getElementById("resultViewTabs").querySelectorAll("button").forEach((x) => x.classList.remove("active"));
      btn.classList.add("active");
      state.resultView = btn.dataset.view;
      state.renderedCount = 0;
      renderResourceList();
    };
  });

  document.getElementById("cloudTypeFilter").onchange = (e) => {
    state.cloudTypeFilter = e.target.value;
    applyFilters();
  };
  document.getElementById("sortBy").onchange = (e) => {
    state.sortBy = e.target.value;
    applyFilters();
  };
  document.getElementById("loadMoreBtn").onclick = renderResourceList;

  document.getElementById("settingsTabs").querySelectorAll("button").forEach((btn) => {
    btn.onclick = () => switchSettingsTab(btn.dataset.tab);
  });

  document.getElementById("settingsForm").onsubmit = saveSettings;
  document.getElementById("saveSettingsTop").onclick = saveSettings;

  document.querySelectorAll(".btn-test-provider").forEach((btn) => {
    btn.onclick = () => testProvider(btn.dataset.provider);
  });

  document.querySelectorAll(".btn-eye[data-toggle-target]").forEach((btn) => {
    btn.onclick = () => {
      const target = document.getElementById(btn.dataset.toggleTarget);
      if (!target) return;
      const visible = target.type === "password";
      target.type = visible ? "text" : "password";
      btn.classList.toggle("is-visible", visible);
      btn.textContent = visible ? "🙈" : "👁";
      btn.title = visible ? "隐藏明文" : "显示明文";
    };
  });

  renderPansouCloudTypeSelect();
  document.getElementById("addCloudTypeBtn").onclick = () => {
    const value = document.getElementById("pansouCloudTypeSelect").value;
    if (!value) return;
    if (!state.pansouCloudTypes.includes(value)) state.pansouCloudTypes.push(value);
    syncPansouCloudTypesField();
    renderPansouCloudTypeChips();
  };

  document.getElementById("dirPickerBackBtn").onclick = async () => {
    if (state.dirPicker.stack.length > 1) {
      state.dirPicker.stack.pop();
      await renderDirPicker();
    }
  };
  document.getElementById("dirPickerCancelBtn").onclick = closeDirPicker;
  document.getElementById("dirPickerConfirmBtn").onclick = async () => {
    const cur = state.dirPicker.stack[state.dirPicker.stack.length - 1];
    if (state.dirPicker.onConfirm) {
      await state.dirPicker.onConfirm({ id: cur.id, path: cur.path || "/" });
    }
    closeDirPicker();
  };
  document.getElementById("transferItemsCancelBtn").onclick = closeTransferItemsModal;
  document.getElementById("transferItemsBackBtn").onclick = async () => {
    if (state.transfer.stack.length <= 1) return;
    syncCurrentTransferChecks();
    state.transfer.stack.pop();
    const parent = state.transfer.stack[state.transfer.stack.length - 1];
    const list = document.getElementById("transferItemsList");
    list.innerHTML = '<div class="dir-item">加载中...</div>';
    try {
      const data = await loadTransferItems(parent.id || "");
      state.transfer.items = data.items || [];
      renderTransferItemsModal();
    } catch (error) {
      list.innerHTML = `<div class="dir-item">加载失败：${escapeHtml(error.message)}</div>`;
    }
  };

  document.getElementById("loginForm").onsubmit = doLogin;
}

async function bootstrapAfterLogin() {
  const initialPage = location.hash.replace("#", "") || "recommend";
  await loadSettings();
  await loadRecommendCategories();
  await loadRecommend();
  switchSettingsTab("media");
  showPage(initialPage);
}

async function init() {
  bindEvents();
  const ok = await ensureAuth();
  if (!ok) return;
  await bootstrapAfterLogin();
}

init().catch((error) => setStatus("初始化失败: " + error.message, "warn"));
