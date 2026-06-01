const state = {
  recommendItems: [],
  recommendSource: "tmdb",
  recommendCategory: "trend_day",
  recommendCategories: { tmdb: [], douban: [] },
  recommendSearchMode: false,
  recommendCache: new Map(),
  tmdbSearchCache: new Map(),
  detailCache: new Map(),

  resources: [],
  filtered: [],
  currentPage: 1,
  pageSize: 30,
  resultSelectMode: false,
  selectedResultIds: new Set(),
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
  resourceFilterRules: [],
  cleanupPreviewTokens: { cloud: "", local: "" },
  cleanupTarget: {
    cloudProvider: "115",
    parentId: "0",
    parentPath: "/",
    localRoot: "",
  },
  cleanupPhase: { cloud: "preview", local: "preview" },
  cleanupAbort: { local: null },
  cleanupSelected: [],
  cleanupLogTail: {
    timer: null,
    startedAt: "",
    seen: new Set(),
  },
  imageMode: "direct",
  pendingTransferRow: null,
  dirPicker: {
    stack: [{ id: "0", path: "/" }],
    provider: "115",
    sourceUri: "",
    onConfirm: null,
    renderSeq: 0,
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
];

const STORAGE_PROVIDER_LABELS = {
  "115": "115 网盘",
  quark: "夸克网盘",
  tianyi: "天翼云盘",
  "123": "123 网盘",
  baidu: "百度网盘",
  aliyun: "阿里云盘",
  uc: "UC 网盘",
  mobile: "移动云盘",
  xunlei: "迅雷网盘",
};
const CLEANUP_IMPLEMENTED_PROVIDERS = new Set(["115", "quark"]);

const DEFAULT_RESOURCE_FILTER_RULES = [
  {
    id: "doc-text-files",
    name: "文档和文本文件",
    enabled: true,
    glob: "*.txt",
    min_size_mb: null,
    max_size_mb: null,
    applies_to: "both",
  },
  {
    id: "doc-word-files",
    name: "Word 文档",
    enabled: true,
    glob: "*.docx",
    min_size_mb: null,
    max_size_mb: null,
    applies_to: "both",
  },
  {
    id: "ad-video-mp4",
    name: "广告视频-mp4",
    enabled: true,
    glob: "*.mp4",
    min_size_mb: null,
    max_size_mb: 5,
    applies_to: "both",
  },
  {
    id: "ad-video-mkv",
    name: "广告视频-mkv",
    enabled: true,
    glob: "*.mkv",
    min_size_mb: null,
    max_size_mb: 5,
    applies_to: "both",
  },
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
const LOGIN_REMEMBER_KEY = "cmp_login_remember_v1";
const modalFocusStack = new Map();

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

function formatBytes(size) {
  if (typeof size !== "number" || !Number.isFinite(size) || size <= 0) return "-";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = size;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const digits = value >= 100 || unitIndex === 0 ? 0 : value >= 10 ? 1 : 2;
  return `${value.toFixed(digits)} ${units[unitIndex]}`;
}

function deepClone(value) {
  return JSON.parse(JSON.stringify(value));
}

function defaultResourceFilterRules() {
  return deepClone(DEFAULT_RESOURCE_FILTER_RULES);
}

function parseResourceFilterRules(raw) {
  if (!raw) return defaultResourceFilterRules();
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return defaultResourceFilterRules();
    return parsed.map((item, index) => {
      let min = item.min_size_mb;
      if (min === null || min === undefined || min === "") {
        if (item.min_size_bytes !== null && item.min_size_bytes !== undefined && item.min_size_bytes !== "") {
          min = Math.round(Number(item.min_size_bytes) / (1024 * 1024));
        } else {
          min = null;
        }
      }
      let max = item.max_size_mb;
      if (max === null || max === undefined || max === "") {
        if (item.max_size_bytes !== null && item.max_size_bytes !== undefined && item.max_size_bytes !== "") {
          max = Math.round(Number(item.max_size_bytes) / (1024 * 1024));
        } else {
          max = null;
        }
      }
      return {
        id: String(item.id || `custom-${index + 1}`),
        name: String(item.name || `规则 ${index + 1}`),
        enabled: item.enabled !== false,
        glob: String(item.glob || "*"),
        min_size_mb: min,
        max_size_mb: max,
        applies_to: ["transfer", "cleanup", "both"].includes(item.applies_to) ? item.applies_to : "both",
      };
    });
  } catch {
    return defaultResourceFilterRules();
  }
}

function loadRememberedLogin() {
  try {
    const raw = localStorage.getItem(LOGIN_REMEMBER_KEY);
    if (!raw) return { remember: false, username: "", password: "" };
    const parsed = JSON.parse(raw);
    return {
      remember: !!parsed.remember,
      username: String(parsed.username || ""),
      password: String(parsed.password || ""),
    };
  } catch {
    return { remember: false, username: "", password: "" };
  }
}

function saveRememberedLogin(username, password) {
  localStorage.setItem(
    LOGIN_REMEMBER_KEY,
    JSON.stringify({
      remember: true,
      username: String(username || ""),
      password: String(password || ""),
    })
  );
}

function clearRememberedLogin() {
  localStorage.removeItem(LOGIN_REMEMBER_KEY);
}

function syncRememberedLoginForm() {
  const remembered = loadRememberedLogin();
  const usernameInput = document.getElementById("loginUsername");
  const passwordInput = document.getElementById("loginPassword");
  const rememberInput = document.getElementById("loginRemember");
  if (!usernameInput || !passwordInput || !rememberInput) return;
  rememberInput.checked = remembered.remember;
  if (remembered.username) usernameInput.value = remembered.username;
  if (remembered.password) passwordInput.value = remembered.password;
}

function getImageMode() {
  const selected = document.querySelector('input[name="imgMode"]:checked');
  return selected ? selected.value : "direct";
}

function posterSrc(url) {
  if (!url) return IMG_FALLBACK;
  if (getImageMode() === "proxy" || String(url).includes("doubanio.com")) {
    return "/tmdb/image?url=" + encodeURIComponent(url);
  }
  return url;
}

function getRecommendCacheKey(source, category) {
  return `${source}:${category}`;
}

function getRecommendCache(source, category) {
  const cached = state.recommendCache.get(getRecommendCacheKey(source, category));
  if (!cached || !Array.isArray(cached.items) || !cached.ts) return null;
  if (Date.now() - cached.ts > 6 * 3600 * 1000) return null;
  return cached.items;
}

function setRecommendCache(source, category, items) {
  state.recommendCache.set(getRecommendCacheKey(source, category), {
    ts: Date.now(),
    items: items || [],
  });
}

function clearRecommendCache(source, category) {
  state.recommendCache.delete(getRecommendCacheKey(source, category));
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
    ed2k: "磁力",
    mobile: "移动",
    xunlei: "迅雷",
    baidu: "百度",
    aliyun: "阿里",
    uc: "UC",
  };
  return map[value] || "其他";
}

function setVisiblePage(pageId) {
  document.querySelectorAll("section[data-page]").forEach((el) => {
    el.hidden = el.dataset.page !== pageId;
  });
  nav.querySelectorAll("button").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.page === pageId);
  });
}

function showPage(pageId) {
  setVisiblePage(pageId);
  if (pageId === "recommend") {
    loadRecommend(true).catch((error) => setStatus("加载推荐失败：" + error.message, "warn"));
  }
  writeUiStateToUrl({ page: pageId });
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
    card.tabIndex = 0;
    card.setAttribute("aria-expanded", "false");
    card.dataset.title = item.title || "";
    const tags = [];
    const isValidText = (v) => !!v && !String(v).includes("未知");
    if (item.year) tags.push(String(item.year));
    if (isValidText(item.country)) tags.push(String(item.country));
    if (isValidText(item.language)) tags.push(String(item.language).toUpperCase());
    if (item.episodes) tags.push(`${item.episodes}集`);
    if (state.recommendSource === "douban" && isValidText(item.overview)) tags.push(String(item.overview));
    const cachedDetail = state.detailCache.get(item.title || "");
    card.innerHTML = `
      <div class="poster-wrap">
        <img alt="${escapeHtml(item.title)}" width="400" height="600" loading="lazy" src="${escapeHtml(posterSrc(item.poster_url))}" />
        <div class="poster-blur" style="background-image:url('${escapeHtml(posterSrc(item.poster_url))}')"></div>
        <div class="poster-overlay">
          <button type="button" class="poster-search-btn" title="搜索资源" aria-label="搜索 ${escapeHtml(item.title || "该资源")}">搜索资源</button>
          <div class="poster-detail">${escapeHtml(cachedDetail || "详情预加载中...")}</div>
        </div>
        <span class="badge-score">★ ${item.rating || "-"}</span>
      </div>
      <div class="trend-body">
        <div class="trend-title">${escapeHtml(item.title)}</div>
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
    const detailBox = card.querySelector(".poster-detail");
    if (detailBox) {
      detailBox.addEventListener("click", (event) => {
        if (!window.matchMedia("(hover: none)").matches) return;
        event.preventDefault();
        event.stopPropagation();
        const expanded = card.classList.contains("expanded");
        if (expanded) {
          card.classList.remove("expanded");
          card.setAttribute("aria-expanded", "false");
        }
      });
    }
    card.addEventListener("click", (event) => {
      if (event.target && event.target.closest(".poster-search-btn")) return;
      const expanded = card.classList.toggle("expanded");
      card.setAttribute("aria-expanded", expanded ? "true" : "false");
      if (expanded) loadRecommendDetail(item, card);
    });
    card.addEventListener("focus", () => {
      if (window.matchMedia("(hover: none)").matches) return;
      card.classList.add("expanded");
      card.setAttribute("aria-expanded", "true");
      loadRecommendDetail(item, card);
    });
    card.addEventListener("blur", () => {
      if (window.matchMedia("(hover: none)").matches) return;
      card.classList.remove("expanded");
      card.setAttribute("aria-expanded", "false");
    });
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        card.click();
      }
    });
    card.onmouseenter = () => loadRecommendDetail(item, card);
    root.appendChild(card);
  });
  prefetchRecommendDetails(items);
}

async function loadRecommendDetail(item, card) {
  const box = card.querySelector(".poster-detail");
  if (!box || !item.title) return;
  if (state.detailCache.has(item.title)) {
    box.textContent = state.detailCache.get(item.title);
    return;
  }
  try {
    let data = {};
    if (state.recommendSource === "tmdb" && Number(item.tmdb_id) > 0) {
      data = await api(
        `/recommend/detail/by-id?tmdb_id=${encodeURIComponent(item.tmdb_id)}&media_type=${encodeURIComponent(item.media_type || "")}`
      );
    } else {
      data = await api(`/recommend/detail?title=${encodeURIComponent(item.title)}`);
    }
    const parts = [];
    if (data.year) parts.push(String(data.year));
    if (data.country) parts.push(String(data.country));
    if (Array.isArray(data.genres)) parts.push(...data.genres.slice(0, 3));
    if (data.director) parts.push(data.director);
    if (Array.isArray(data.cast)) parts.push(data.cast.slice(0, 4).join(" "));
    const text = parts.filter(Boolean).join(" / ") || `${item.title}${item.rating ? " / " + item.rating : ""}`;
    state.detailCache.set(item.title, text);
    document.querySelectorAll(`.trend-card[data-title="${CSS.escape(item.title)}"] .poster-detail`).forEach((el) => {
      el.textContent = text;
    });
  } catch {
    box.textContent = `${item.title}${item.rating ? " / " + item.rating : ""}`;
  }
}

function prefetchRecommendDetails(items) {
  if (state.recommendSource !== "tmdb") return;
  const queue = items.filter((item) => item.title && !state.detailCache.has(item.title)).slice(0, 12);
  let index = 0;
  const workers = Array.from({ length: 3 }, async () => {
    while (index < queue.length) {
      const item = queue[index++];
      const card = document.querySelector(`.trend-card[data-title="${CSS.escape(item.title)}"]`);
      await loadRecommendDetail(item, card || document.createElement("div"));
    }
  });
  setTimeout(() => Promise.allSettled(workers), 30);
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
  state.currentPage = 1;
  renderSummary();
  renderResourceList();
  writeUiStateToUrl();
}

function resultId(row) {
  return `${row.source || ""}|${row.source_id || ""}|${row.link || ""}|${row.magnet || ""}`;
}

function validPublishTime(value) {
  if (!value) return null;
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime()) || dt.getFullYear() <= 1971) return null;
  return dt;
}

function formatPublishTime(value) {
  const dt = validPublishTime(value);
  return dt ? dt.toLocaleString() : "-";
}

function visiblePageRows() {
  const start = (state.currentPage - 1) * state.pageSize;
  return state.filtered.slice(start, start + state.pageSize);
}

function setResultSelected(row, selected) {
  const id = resultId(row);
  if (selected) state.selectedResultIds.add(id);
  else state.selectedResultIds.delete(id);
}

function renderSearchBulkControls() {
  const box = document.getElementById("searchBulkControls");
  if (!box) return;
  const pageRows = visiblePageRows();
  const selectedOnPage = pageRows.filter((row) => state.selectedResultIds.has(resultId(row))).length;
  box.hidden = !state.resultSelectMode;
  box.innerHTML = `
    <button id="selectPageResultsBtn" type="button">全选本页</button>
    <button id="selectAllResultsBtn" type="button">全部选择</button>
    <button id="batchTransferBtn" type="button">一键转存选中</button>
    <button id="clearResultSelectionBtn" type="button">取消选择</button>
    <span>已选 ${state.selectedResultIds.size} 个，本页 ${selectedOnPage}/${pageRows.length}</span>
  `;
  document.getElementById("selectPageResultsBtn").onclick = () => {
    const allSelected = pageRows.length > 0 && selectedOnPage === pageRows.length;
    pageRows.forEach((row) => setResultSelected(row, !allSelected));
    renderResourceList();
  };
  document.getElementById("clearResultSelectionBtn").onclick = () => {
    state.selectedResultIds.clear();
    renderResourceList();
  };
  document.getElementById("selectAllResultsBtn").onclick = () => {
    const allSelected = state.filtered.length > 0 && state.filtered.every((row) => state.selectedResultIds.has(resultId(row)));
    state.filtered.forEach((row) => setResultSelected(row, !allSelected));
    renderResourceList();
  };
  document.getElementById("batchTransferBtn").onclick = batchTransferSelected;
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
  const id = resultId(row);
  item.classList.toggle("is-selected", state.selectedResultIds.has(id));
  const sourceText = row.magnet || row.link || row.source_id || "-";
  const sourceDetail = row.source_detail || "-";
  item.innerHTML = `
    ${state.resultSelectMode ? `<label class="result-check"><input type="checkbox" ${state.selectedResultIds.has(id) ? "checked" : ""} /></label>` : ""}
    <div class="resource-main">
      <div class="trend-meta">
        <span class="tag">${escapeHtml(row.source || "-")}</span>
        <span class="tag">${escapeHtml(sourceDetail)}</span>
        <span class="tag">${escapeHtml(cloudTypeName(row.cloud_type || "other"))}</span>
      </div>
      <div class="resource-title">${escapeHtml(row.title || "-")}</div>
      <div class="resource-sub resource-source-line">来源：<span class="truncate-one" title="${escapeHtml(sourceText)}">${escapeHtml(sourceText)}</span><button class="btn-copy-source" type="button">复制</button></div>
    </div>
    <div class="resource-side">
      <div class="meta-line">大小/热度：${row.size ? Math.round(row.size / 1024 / 1024) + " MB" : "-"} / ${Math.round(row.score || 0)}</div>
      <div class="meta-line">时间：${formatPublishTime(row.publish_time)}</div>
      <div class="resource-actions">
        <button class="btn-save" type="button">一键转存</button>
        <button class="btn-open" type="button">打开链接</button>
      </div>
    </div>
  `;
  const check = item.querySelector(".result-check input");
  if (check) {
    check.onchange = (e) => {
      setResultSelected(row, e.currentTarget.checked);
      item.classList.toggle("is-selected", e.currentTarget.checked);
      renderSearchBulkControls();
    };
    item.addEventListener("click", (e) => {
      if (e.target === check || e.target.closest("button") || e.target.closest("a")) return;
      check.checked = !check.checked;
      check.dispatchEvent(new Event("change"));
    });
  }
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
  const id = resultId(row);
  card.classList.toggle("is-selected", state.selectedResultIds.has(id));
  const img = posterSrc(row.tmdb_poster || "");
  const sourceDetail = row.source_detail || "-";
  card.innerHTML = `
    ${state.resultSelectMode ? `<label class="result-check poster-check"><input type="checkbox" ${state.selectedResultIds.has(id) ? "checked" : ""} /></label>` : ""}
    <img src="${escapeHtml(img)}" alt="${escapeHtml(row.title || "-")}" />
    <div class="body">
      <div class="title">${escapeHtml(row.title || "-")}</div>
      <div class="meta">${escapeHtml(row.source || "-")} / ${escapeHtml(sourceDetail)} / ${escapeHtml(cloudTypeName(row.cloud_type || "other"))}</div>
      <div class="meta">${row.size ? Math.round(row.size / 1024 / 1024) + " MB" : "-"}</div>
      <div class="actions">
        <button class="btn-save" type="button">一键转存</button>
        <button class="btn-open" type="button">打开链接</button>
      </div>
    </div>
  `;
  const check = card.querySelector(".result-check input");
  if (check) {
    check.onchange = (e) => {
      setResultSelected(row, e.currentTarget.checked);
      card.classList.toggle("is-selected", e.currentTarget.checked);
      renderSearchBulkControls();
    };
    card.addEventListener("click", (e) => {
      if (e.target === check || e.target.closest("button") || e.target.closest("a")) return;
      check.checked = !check.checked;
      check.dispatchEvent(new Event("change"));
    });
  }
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
  list.textContent = "";
  list.className = state.resultView === "poster" ? "poster-result-grid" : "resource-list";

  if (!state.filtered.length) {
    list.className = "resource-list";
    list.innerHTML = '<div class="card">暂无搜索结果</div>';
    renderPagination();
    renderSearchBulkControls();
    return;
  }

  visiblePageRows().forEach((row) => {
    list.appendChild(state.resultView === "poster" ? renderPosterCard(row) : renderListItem(row));
  });

  renderPagination();
  renderSearchBulkControls();
}

function renderPagination() {
  const box = document.getElementById("resultPagination");
  if (!box) return;
  const totalPages = Math.max(1, Math.ceil(state.filtered.length / state.pageSize));
  state.currentPage = Math.min(Math.max(1, state.currentPage), totalPages);
  if (!state.filtered.length) {
    box.hidden = true;
    return;
  }
  const makePageButton = (page, label = String(page)) =>
    `<button type="button" data-page="${page}" class="${page === state.currentPage ? "active" : ""}">${label}</button>`;
  const pages = [];
  const start = Math.max(1, state.currentPage - 2);
  const end = Math.min(totalPages, state.currentPage + 2);
  if (start > 1) pages.push(makePageButton(1));
  if (start > 2) pages.push("<span>...</span>");
  for (let page = start; page <= end; page += 1) pages.push(makePageButton(page));
  if (end < totalPages - 1) pages.push("<span>...</span>");
  if (end < totalPages) pages.push(makePageButton(totalPages));

  box.hidden = false;
  box.innerHTML = `
    <button type="button" data-page="${state.currentPage - 1}" ${state.currentPage <= 1 ? "disabled" : ""}>上一页</button>
    ${pages.join("")}
    <button type="button" data-page="${state.currentPage + 1}" ${state.currentPage >= totalPages ? "disabled" : ""}>下一页</button>
    <span>第 ${state.currentPage}/${totalPages} 页，共 ${state.filtered.length} 条</span>
  `;
  box.querySelectorAll("button[data-page]").forEach((btn) => {
    btn.onclick = () => {
      const page = Number(btn.dataset.page);
      if (!Number.isFinite(page)) return;
      state.currentPage = Math.min(Math.max(1, page), totalPages);
      renderResourceList();
      writeUiStateToUrl();
    };
  });
}

function writeUiStateToUrl(extra = {}) {
  const url = new URL(window.location.href);
  const currentPageName = extra.page || document.querySelector("section[data-page]:not([hidden])")?.dataset.page || "recommend";
  url.hash = `#${currentPageName}`;
  const params = url.searchParams;
  params.set("page", currentPageName);
  params.set("source", state.sourceFilter || "all");
  params.set("cloud", state.cloudTypeFilter || "all");
  params.set("sort", state.sortBy || "score_desc");
  params.set("view", state.resultView || "list");
  params.set("p", String(state.currentPage || 1));
  history.replaceState(null, "", `${url.pathname}?${params.toString()}${url.hash}`);
}

function applyUiStateFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const page = params.get("page");
  const source = params.get("source");
  const cloud = params.get("cloud");
  const sort = params.get("sort");
  const view = params.get("view");
  const p = Number(params.get("p"));
  if (source) state.sourceFilter = source;
  if (cloud) state.cloudTypeFilter = cloud;
  if (sort) state.sortBy = sort;
  if (view) state.resultView = view;
  if (Number.isFinite(p) && p > 0) state.currentPage = Math.floor(p);
  return page || location.hash.replace("#", "") || "recommend";
}

function setModalVisibility(modalId, visible) {
  const modal = document.getElementById(modalId);
  if (!modal) return;
  if (visible) {
    modalFocusStack.set(modalId, document.activeElement);
    modal.hidden = false;
    const firstFocusable = modal.querySelector("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])");
    if (firstFocusable) firstFocusable.focus();
    return;
  }
  modal.hidden = true;
  const prev = modalFocusStack.get(modalId);
  if (prev && typeof prev.focus === "function") prev.focus();
  modalFocusStack.delete(modalId);
}

function bindModalEscapeClose() {
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const modals = ["logsModal", "transferItemsModal", "dirPickerModal"];
    const opened = modals.find((id) => !document.getElementById(id)?.hidden);
    if (!opened) return;
    event.preventDefault();
    if (opened === "logsModal") setModalVisibility("logsModal", false);
    if (opened === "transferItemsModal") closeTransferItemsModal();
    if (opened === "dirPickerModal") closeDirPicker();
  });
}

function bindHeaderCondenseBehavior() {
  const main = document.querySelector(".main");
  if (!main) return;
  const refresh = () => {
    main.classList.toggle("is-condensed", main.scrollTop > 36);
  };
  main.addEventListener("scroll", refresh, { passive: true });
  refresh();
}

function syncSearchFilterToggleButtonText() {
  const searchBtn = document.getElementById("searchFilterToggleBtn");
  const searchHead = document.querySelector(".search-head");
  const recommendBtn = document.getElementById("recommendFilterToggleBtn");
  const recommendHead = document.querySelector(".hero");
  const isMobile = window.matchMedia("(max-width: 980px)").matches;
  if (searchBtn && searchHead) {
    const opened = searchHead.classList.contains("search-advanced-open");
    searchBtn.textContent = isMobile && opened ? "收起筛选" : "筛选";
  }
  if (recommendBtn && recommendHead) {
    const opened = recommendHead.classList.contains("recommend-advanced-open");
    recommendBtn.textContent = isMobile && opened ? "收起筛选" : "筛选";
  }
}

function applyFormAccessibilityDefaults() {
  const typeAutocompleteMap = {
    password: "current-password",
    email: "email",
    tel: "tel",
    url: "url",
    search: "off",
  };
  document.querySelectorAll("input, select, textarea").forEach((el) => {
    if (!el.name && el.id) el.name = el.id;
    if (el.tagName === "INPUT" && !el.autocomplete) {
      const byType = typeAutocompleteMap[el.type];
      el.autocomplete = byType || "off";
    }
    if (!el.getAttribute("aria-label")) {
      const label = el.closest("label")?.querySelector("span")?.textContent?.trim();
      if (label) el.setAttribute("aria-label", label);
    }
  });
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
    state.selectedResultIds.clear();
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

function serializeFilterRules() {
  return JSON.stringify(
    state.resourceFilterRules.map((rule, index) => ({
      id: String(rule.id || `rule-${index + 1}`),
      name: String(rule.name || `规则 ${index + 1}`),
      enabled: !!rule.enabled,
      glob: String(rule.glob || "*"),
      min_size_mb:
        rule.min_size_mb === null || rule.min_size_mb === undefined || rule.min_size_mb === ""
          ? null
          : Number(rule.min_size_mb),
      max_size_mb:
        rule.max_size_mb === null || rule.max_size_mb === undefined || rule.max_size_mb === ""
          ? null
          : Number(rule.max_size_mb),
      applies_to: ["transfer", "cleanup", "both"].includes(rule.applies_to) ? rule.applies_to : "both",
    }))
  );
}

function renderFilterRules() {
  const root = document.getElementById("filterRulesList");
  if (!root) return;
  root.innerHTML = "";
  if (!state.resourceFilterRules.length) {
    root.innerHTML = '<div class="cleanup-preview-empty">暂无规则，点击“新增规则”开始配置。</div>';
    return;
  }
  state.resourceFilterRules.forEach((rule, index) => {
    const row = document.createElement("div");
    row.className = "filter-rule-row";
    row.innerHTML = `
      <div class="filter-rule-grid">
        <label><span>规则名</span><input data-key="name" value="${escapeHtml(rule.name || "")}" /></label>
        <label><span>Glob</span><input data-key="glob" value="${escapeHtml(rule.glob || "")}" placeholder="*.txt" /></label>
        <label><span>最小体积 (MB)</span><input data-key="min_size_mb" type="number" min="0" step="1" value="${rule.min_size_mb ?? ""}" placeholder="MB" /></label>
        <label><span>最大体积 (MB)</span><input data-key="max_size_mb" type="number" min="0" step="1" value="${rule.max_size_mb ?? ""}" placeholder="MB" /></label>
        <div class="filter-rule-actions">
          <button type="button" data-action="remove">删除</button>
          <label class="filter-rule-toggle"><input type="checkbox" data-key="enabled" ${rule.enabled ? "checked" : ""} /> 启用</label>
        </div>
      </div>
    `;
    row.querySelectorAll("[data-key]").forEach((input) => {
      input.onchange = () => {
        const key = input.getAttribute("data-key");
        if (!key) return;
        const next = { ...state.resourceFilterRules[index] };
        if (key === "enabled") next.enabled = !!input.checked;
        else if (key === "min_size_mb" || key === "max_size_mb") {
          next[key] = input.value === null || input.value === undefined || input.value === "" ? null : Number(input.value);
        } else {
          next[key] = input.value;
        }
        next.applies_to = "both";
        state.resourceFilterRules[index] = next;
        renderFilterRules();
      };
    });
    row.querySelector('[data-action="remove"]').onclick = () => {
      state.resourceFilterRules.splice(index, 1);
      renderFilterRules();
    };
    root.appendChild(row);
  });
}

function cleanupLocalRoots() {
  return (state.settings.resource_cleanup_local_roots || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function renderCleanupLocalRoots() {
  const select = document.getElementById("cleanupLocalRootSelect");
  if (!select) return;
  const roots = cleanupLocalRoots();
  select.innerHTML = "";
  roots.forEach((root) => {
    const op = document.createElement("option");
    op.value = root;
    op.textContent = root;
    select.appendChild(op);
  });
  select.value = roots.includes(state.cleanupTarget.localRoot) ? state.cleanupTarget.localRoot : "";
  if (!select.value && roots.length) select.value = roots[0];
  state.cleanupTarget.localRoot = select.value || "";
}

function renderCleanupTarget() {
  renderCleanupLocalRoots();
  const localPath = document.getElementById("cleanupLocalPath");
  if (localPath) localPath.textContent = state.cleanupTarget.localRoot || "未选择";
}

function renderCleanupCloudProviderOptions() {
  const select = document.getElementById("cleanupCloudProvider");
  if (!select) return;
  if (!select) return;
  const configured = String(state.settings.storage_providers || "")
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
  const providers = configured.length ? configured : ["115", "quark"];
  select.innerHTML = "";
  providers.forEach((provider) => {
    const op = document.createElement("option");
    op.value = provider;
    const label = STORAGE_PROVIDER_LABELS[provider] || provider;
    op.textContent = CLEANUP_IMPLEMENTED_PROVIDERS.has(provider)
      ? label
      : `${label}（暂未支持清理）`;
    op.disabled = !CLEANUP_IMPLEMENTED_PROVIDERS.has(provider);
    select.appendChild(op);
  });
  const available = providers.find((x) => CLEANUP_IMPLEMENTED_PROVIDERS.has(x)) || "115";
  const next = providers.includes(state.cleanupTarget.cloudProvider)
    ? state.cleanupTarget.cloudProvider
    : available;
  state.cleanupTarget.cloudProvider = next;
  select.value = next;
}

function appendCleanupLog(message) {
  const box = document.getElementById("cleanupLogBox");
  if (!box) return;
  const ts = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  box.value = `${box.value}${box.value ? "\n" : ""}[${ts}] ${message}`;
  box.scrollTop = box.scrollHeight;
}

function stopCleanupLogTail() {
  if (state.cleanupLogTail.timer) {
    clearInterval(state.cleanupLogTail.timer);
    state.cleanupLogTail.timer = null;
  }
}

function resetCleanupLogTail() {
  stopCleanupLogTail();
  state.cleanupLogTail.startedAt = new Date().toISOString();
  state.cleanupLogTail.seen = new Set();
}

function formatCleanupScanLog(row) {
  const match = String(row.message || "").match(/^cleanup_scan_dir provider=([^\s]+) path=(.+)$/);
  if (!match) return "";
  const provider = match[1];
  const path = match[2];
  return `${provider} 扫描目录: ${path}`;
}

async function pumpCleanupLogs() {
  const startedAt = state.cleanupLogTail.startedAt;
  if (!startedAt) return;
  try {
    const data = await api("/logs?level=info&limit=300");
    for (const row of data.items || []) {
      if (row.logger !== "cleanup") continue;
      if (!row.time || row.time < startedAt) continue;
      const key = `${row.time}|${row.message}`;
      if (state.cleanupLogTail.seen.has(key)) continue;
      state.cleanupLogTail.seen.add(key);
      const message = formatCleanupScanLog(row);
      if (message) appendCleanupLog(message);
    }
  } catch {}
}

function startCleanupLogTail() {
  resetCleanupLogTail();
  state.cleanupLogTail.timer = setInterval(() => {
    void pumpCleanupLogs();
  }, 800);
}

function setCleanupActionButton(targetType) {
  if (targetType === "cloud") {
    const btn = document.getElementById("cleanupCloudActionBtn");
    if (!btn) return;
    const phase = state.cleanupPhase.cloud;
    btn.textContent = phase === "execute" ? "执行网盘清理" : "预览网盘清理";
  }
}

function buildCleanupRuleStatsFromItems(items) {
  const statMap = new Map();
  (items || []).forEach((item) => {
    const ruleId = String(item.rule_id || "unknown");
    const ruleName = String(item.rule_name || "未命名规则");
    const key = `${ruleId}::${ruleName}`;
    const current = statMap.get(key) || { rule_id: ruleId, rule_name: ruleName, count: 0, total_size: 0 };
    current.count += 1;
    current.total_size += item.size || 0;
    statMap.set(key, current);
  });
  return Array.from(statMap.values()).sort((a, b) => b.count - a.count);
}

function renderCleanupPreview(data) {
  const root = document.getElementById("cleanupPreviewPanel");
  if (!root) return;
  if (!data) {
    root.innerHTML = "";
    return;
  }
  const items = (data.items || []).slice(0, 120);
  const allIds = items.map((x) => x.id);
  if (data.preview_token) state.cleanupSelected = allIds;
  const stats = `
    <div class="transfer-browser-stats">
      <div class="transfer-browser-stat"><span class="label">命中文件</span><span class="value">${data.total_matches || 0}</span></div>
      <div class="transfer-browser-stat"><span class="label">总体积</span><span class="value">${formatBytes(data.total_size || 0)}</span></div>
      <div class="transfer-browser-stat"><span class="label">已选</span><span class="value" id="cleanupSelectedCount">${allIds.length}</span></div>
    </div>
  `;
  const ruleStats = (data.rules && data.rules.length) ? data.rules : buildCleanupRuleStatsFromItems(items);
  const rules = ruleStats
    .map((rule) => `<div class="cleanup-rule-chip"><strong>${escapeHtml(rule.rule_name)}</strong><span>${rule.count} 项 / ${formatBytes(rule.total_size || 0)}</span></div>`)
    .join("");
  const itemRows = items
    .map((item) => {
      const checked = state.cleanupSelected.includes(item.id) ? "checked" : "";
      return `<label class="cleanup-preview-item cleanup-preview-selectable"><input type="checkbox" class="cleanup-item-cb" value="${escapeHtml(item.id)}" ${checked} /><span><strong>${escapeHtml(item.name)}</strong><div class="meta">${escapeHtml(item.path)} / ${escapeHtml(item.rule_name)} / ${formatBytes(item.size || 0)}</div></span></label>`;
    })
    .join("");
  root.innerHTML = `
    ${stats}
    <div class="bulk-controls" style="margin-top:6px">
      <button type="button" id="cleanupSelectAllBtn" class="btn-small">全选</button>
      <button type="button" id="cleanupDeselectAllBtn" class="btn-small">取消全选</button>
    </div>
    <div class="cleanup-preview-list cleanup-rule-stats-line">${rules || '<div class="cleanup-preview-empty">暂无规则命中统计</div>'}</div>
    <div class="cleanup-preview-list cleanup-preview-checklist">${itemRows || '<div class="cleanup-preview-empty">未命中任何可清理文件</div>'}</div>
  `;
  root.querySelectorAll(".cleanup-item-cb").forEach((cb) => {
    cb.onchange = () => {
      const id = cb.value;
      if (cb.checked) {
        if (!state.cleanupSelected.includes(id)) state.cleanupSelected.push(id);
      } else {
        state.cleanupSelected = state.cleanupSelected.filter((x) => x !== id);
      }
      const countEl = document.getElementById("cleanupSelectedCount");
      if (countEl) countEl.textContent = state.cleanupSelected.length;
    };
  });
  const selBtn = document.getElementById("cleanupSelectAllBtn");
  if (selBtn) selBtn.onclick = () => {
    state.cleanupSelected = allIds;
    root.querySelectorAll(".cleanup-item-cb").forEach((cb) => { cb.checked = true; });
    const countEl = document.getElementById("cleanupSelectedCount");
    if (countEl) countEl.textContent = allIds.length;
  };
  const deselBtn = document.getElementById("cleanupDeselectAllBtn");
  if (deselBtn) deselBtn.onclick = () => {
    state.cleanupSelected = [];
    root.querySelectorAll(".cleanup-item-cb").forEach((cb) => { cb.checked = false; });
    const countEl = document.getElementById("cleanupSelectedCount");
    if (countEl) countEl.textContent = "0";
  };
}

function isMaskedSecret(value) {
  return !!value && /^\*+/.test(value);
}

function showMaskedHint(elId, _label, _masked) {
  const el = document.getElementById(elId);
  if (!el) return;
  el.textContent = "";
}

function setSecretInput(id, masked) {
  const input = document.getElementById(id);
  if (!input) return;
  input.value = masked || "";
  input.placeholder = "";
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
  setSecretInput("tmdbApiKey", data.tmdb_api_key || data.tmdb_api_key_masked || "");
  document.getElementById("tmdbUseProxy").checked = !!data.tmdb_use_proxy;

  document.getElementById("enablePansou").checked = !!data.enable_pansou;
  document.getElementById("pansouBaseUrl").value = data.pansou_base_url || "";
  document.getElementById("pansouSearchPath").value = data.pansou_search_path || "/api/search";
  document.getElementById("pansouSearchMethod").value = (data.pansou_search_method || "POST").toUpperCase();
  document.getElementById("pansouUseProxy").checked = !!data.pansou_use_proxy;
  document.getElementById("pansouEnableAuth").checked = !!data.pansou_enable_auth;
  document.getElementById("pansouUsername").value = data.pansou_username || "";
  setSecretInput("pansouPassword", data.pansou_password || data.pansou_password_masked || "");
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
  setSecretInput("prowlarrApiKey", data.prowlarr_api_key || data.prowlarr_api_key_masked || "");

  document.getElementById("c115BaseUrl").value = data.c115_base_url || "";
  setSecretInput("c115Cookie", data.c115_cookie || data.c115_cookie_masked || "");
  setSecretInput("quarkCookie", data.quark_cookie || data.quark_cookie_masked || "");
  document.getElementById("tianyiUsername").value = data.tianyi_username || "";
  setSecretInput("tianyiPassword", data.tianyi_password || data.tianyi_password_masked || "");
  document.getElementById("pan123Username").value = data.pan123_username || "";
  setSecretInput("pan123Password", data.pan123_password || data.pan123_password_masked || "");
  document.getElementById("resourceFilterEnabled").checked = data.resource_filter_enabled !== false;
  state.resourceFilterRules = parseResourceFilterRules(data.resource_filter_rules || "");
  renderFilterRules();
  state.settings.resource_cleanup_local_roots = data.resource_cleanup_local_roots || "";
  state.settings.storage_providers = data.storage_providers || state.settings.storage_providers || "";
  renderCleanupCloudProviderOptions();
  renderCleanupLocalRoots();

  document.getElementById("systemUsername").value = data.system_username || "admin";
  setSecretInput("systemPassword", "");
  document.getElementById("systemProxyEnabled").checked = !!data.system_proxy_enabled;
  const proxy = splitProxyUrl(data.system_proxy_url || "");
  document.getElementById("systemProxyScheme").value = proxy.scheme;
  document.getElementById("systemProxyAddr").value = proxy.addr;
  renderCleanupTarget();
  state.cleanupPhase.cloud = "preview";
  state.cleanupPhase.local = "preview";
  setCleanupActionButton("cloud");
  setCleanupActionButton("local");

  showMaskedHint("tmdbApiKeyHint", "TMDB Key", data.tmdb_api_key_masked || "");
  showMaskedHint("prowlarrApiKeyHint", "Prowlarr Key", data.prowlarr_api_key_masked || "");
  showMaskedHint("pansouPasswordHint", "PanSou 密码", data.pansou_password_masked || "");
  showMaskedHint("systemPasswordHint", "设置新密码", "");
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
    storage_providers: state.settings.storage_providers || "115,quark,tianyi,123",
    resource_filter_enabled: document.getElementById("resourceFilterEnabled").checked,
    resource_filter_rules: serializeFilterRules(),
    resource_cleanup_local_roots: state.settings.resource_cleanup_local_roots || "",
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

  const passwordChanged = !!systemPassword && !isMaskedSecret(systemPassword);
  try {
    await api("/settings", { method: "PUT", body: JSON.stringify(payload) });
    if (passwordChanged) {
      setStatus("设置已保存，请重新登录");
      setTimeout(() => { window.location.href = "/"; }, 1500);
      return;
    }
    await loadSettings();
    setStatus("设置已保存");
  } catch (error) {
    if (passwordChanged) {
      setStatus("设置已保存，请重新登录");
      setTimeout(() => { window.location.href = "/"; }, 1500);
    } else {
      setStatus(`保存设置失败：${error.message}`, "warn");
    }
  }
}

async function testProvider(provider) {
  const resultEl = document.getElementById(`testResult-${provider}`);
  const btn = document.querySelector(`.btn-test-provider[data-provider="${provider}"]`);
  const writeResult = (text, level = "ok") => {
    if (!resultEl) return;
    resultEl.textContent = text;
    resultEl.className = "test-result " + (level === "warn" ? "warn" : "ok");
  };
  writeResult("正在测试...");
  setButtonLoading(btn, true);
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
  } finally {
    setButtonLoading(btn, false);
  }
}

async function loadAppInfo() {
  try {
    const data = await api("/app/info");
    document.getElementById("appVersion").textContent = `${data.name || "CloudMediaPilot"} v${data.version || "-"}`;
  } catch {}
}

async function doLogout() {
  await api("/auth/logout", { method: "POST", body: "{}" });
  location.reload();
}

async function loadLogs() {
  const level = document.getElementById("logLevelFilter").value;
  const data = await api(`/logs?level=${encodeURIComponent(level)}&limit=300`);
  const root = document.getElementById("logsList");
  root.innerHTML = (data.items || [])
    .slice()
    .reverse()
    .map((row) => {
      const time = new Date(row.time).toLocaleString();
      return `<div class="log-row ${escapeHtml(String(row.level || "").toLowerCase())}"><span>${escapeHtml(time)}</span><b>${escapeHtml(row.level)}</b><code>${escapeHtml(row.message)}</code></div>`;
    })
    .join("") || '<div class="dir-item">暂无日志</div>';
}

async function ensureAuth() {
  const auth = await api("/auth/me");
  const overlay = document.getElementById("loginOverlay");
  if (auth.authenticated) {
    overlay.hidden = true;
    return true;
  }
  syncRememberedLoginForm();
  overlay.hidden = false;
  return false;
}

async function doLogin(event) {
  event.preventDefault();
  const loginError = document.getElementById("loginError");
  if (loginError) {
    loginError.hidden = true;
    loginError.textContent = "";
  }
  const username = document.getElementById("loginUsername").value.trim();
  const password = document.getElementById("loginPassword").value;
  const remember = document.getElementById("loginRemember").checked;
  if (!username || !password) {
    setStatus("请输入用户名和密码", "warn");
    return;
  }
  try {
    await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    if (remember) {
      saveRememberedLogin(username, password);
    } else {
      clearRememberedLogin();
    }
    document.getElementById("loginOverlay").hidden = true;
    if (!remember) {
      document.getElementById("loginPassword").value = "";
    }
    await bootstrapAfterLogin();
    setStatus("登录成功");
  } catch (error) {
    if (loginError) {
      loginError.hidden = false;
      loginError.textContent = "登录失败：" + error.message;
    }
    setStatus("登录失败：" + error.message, "warn");
  }
}

async function loadDirList(parentId, provider) {
  if (provider === "local") {
    return await api(`/storage/local-dirs?parent_path=${encodeURIComponent(parentId || "")}`);
  }
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

function syncDirPickerBackButton() {
  const btn = document.getElementById("dirPickerBackBtn");
  if (btn) btn.disabled = state.dirPicker.stack.length <= 1;
}

function normalizeDirPickerStack(data, current) {
  const ancestors = Array.isArray(data.ancestors) ? data.ancestors : [];
  const stack = ancestors
    .filter((item) => item && item.id)
    .map((item) => ({
      id: String(item.id),
      path: item.path || "/",
    }));
  const currentId = String(current.id || "0");
  const currentPath = data.parent_path || current.path || "/";
  const last = stack[stack.length - 1];
  if (!last || last.id !== currentId) {
    stack.push({ id: currentId, path: currentPath });
  }
  return stack;
}

async function openDirPicker(initialId, initialPath, provider, sourceUri, onConfirm) {
  state.dirPicker.stack = [{ id: initialId || "0", path: initialPath || "/" }];
  state.dirPicker.provider = provider || "115";
  state.dirPicker.sourceUri = sourceUri || "";
  state.dirPicker.onConfirm = onConfirm;
  setModalVisibility("dirPickerModal", true);
  syncDirPickerBackButton();
  await renderDirPicker();
}

async function renderDirPicker() {
  const renderSeq = ++state.dirPicker.renderSeq;
  let current = state.dirPicker.stack[state.dirPicker.stack.length - 1];
  const listBox = document.getElementById("dirPickerList");
  document.getElementById("dirPickerPath").textContent = current.path || "/";
  listBox.innerHTML = '<div class="dir-item">加载中...</div>';
  try {
    const data = await loadDirList(current.id, state.dirPicker.provider || "115");
    if (renderSeq !== state.dirPicker.renderSeq) return;
    const nextStack = normalizeDirPickerStack(data, current);
    if (nextStack.length) {
      state.dirPicker.stack = nextStack;
      current = state.dirPicker.stack[state.dirPicker.stack.length - 1];
    }
    current.path = data.parent_path || current.path || "/";
    document.getElementById("dirPickerPath").textContent = current.path;
    syncDirPickerBackButton();
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
        const nextPath = state.dirPicker.provider === "local"
          ? (item.id || item.name || "/")
          : ((current.path === "/" ? "" : current.path) + "/" + item.name).replaceAll("//", "/");
        state.dirPicker.stack.push({ id: item.id, path: nextPath });
        await renderDirPicker();
      };
      listBox.appendChild(btn);
    });
  } catch (error) {
    listBox.innerHTML = `<div class="dir-item">加载失败：${escapeHtml(error.message)}</div>`;
  }
}

function closeDirPicker() {
  setModalVisibility("dirPickerModal", false);
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
  setModalVisibility("transferItemsModal", true);
  renderTransferItemsModal();
}

function transferItemsPath() {
  return state.transfer.stack.map((x) => x.name).join(" / ");
}

function syncCurrentTransferChecks() {
  state.transfer.selectedIds = Array.from(
    Array.from(document.querySelectorAll("#transferItemsList input[type='checkbox']:checked"))
      .map((el) => el.getAttribute("data-id") || "")
      .filter(Boolean)
  );
}

function updateTransferSelectionSummary() {
  const currentItems = state.transfer.items || [];
  const selectedInCurrent = currentItems.filter((x) => state.transfer.selectedIds.includes(x.id)).length;
  const summary = document.getElementById("transferSelectSummary");
  if (summary) summary.textContent = `已选 ${state.transfer.selectedIds.length} 个，当前目录 ${selectedInCurrent}/${currentItems.length}`;
  const btn = document.getElementById("transferSelectAllBtn");
  if (btn) btn.disabled = currentItems.length === 0;
}

function renderTransferStats() {
  const root = document.getElementById("transferItemsStats");
  if (!root) return;
  const items = state.transfer.items || [];
  const files = items.filter((item) => !item.is_dir);
  const dirs = items.filter((item) => item.is_dir);
  const selected = items.filter((item) => state.transfer.selectedIds.includes(item.id));
  const selectedSize = selected.reduce((sum, item) => sum + (item.is_dir ? 0 : item.size || 0), 0);
  const stats = [
    { label: "当前目录", value: `${items.length} 项` },
    { label: "文件夹", value: `${dirs.length} 个` },
    { label: "文件", value: `${files.length} 个` },
    { label: "已选体积", value: formatBytes(selectedSize) },
  ];
  root.innerHTML = stats
    .map(
      (item) => `
        <div class="transfer-browser-stat">
          <span class="label">${escapeHtml(item.label)}</span>
          <span class="value">${escapeHtml(item.value)}</span>
        </div>
      `
    )
    .join("");
}

function renderTransferItemsModal() {
  const list = document.getElementById("transferItemsList");
  document.getElementById("transferItemsTitle").textContent =
    `${state.transfer.title || "请选择要转存的资源"}：${transferItemsPath()}`;
  document.getElementById("transferItemsBackBtn").disabled = state.transfer.stack.length <= 1;
  list.innerHTML = "";
  updateTransferSelectionSummary();
  renderTransferStats();
  if (!state.transfer.items.length) {
    list.innerHTML = '<div class="dir-item">当前目录没有可选择资源</div>';
    return;
  }
  state.transfer.items.forEach((item) => {
    const row = document.createElement("div");
    row.className = "dir-item transfer-item-row";
    row.dataset.kind = item.is_dir ? "dir" : "file";
    const metaText = item.is_dir ? "文件夹" : formatBytes(item.size);
    const checked = state.transfer.selectedIds.includes(item.id) ? "checked" : "";
    if (item.is_dir) {
      row.innerHTML = `
        <input type="checkbox" data-id="${escapeHtml(item.id)}" ${checked} />
        <div class="transfer-item-main">
          <div class="transfer-item-title">
            <span class="transfer-item-icon">📁</span>
            <span class="transfer-item-name">${escapeHtml(item.name)}</span>
          </div>
          <div class="transfer-item-sub">进入此目录浏览并选择子资源</div>
        </div>
        <div class="transfer-item-meta">
          <span class="label">类型</span>
          <span class="value">${metaText}</span>
        </div>
      `;
      const checkbox = row.querySelector("input");
      checkbox.onchange = () => {
        syncCurrentTransferChecks();
        row.classList.toggle("is-selected", checkbox.checked);
        updateTransferSelectionSummary();
        renderTransferStats();
      };
      checkbox.onclick = (e) => e.stopPropagation();
      row.onclick = async (e) => {
        if (e.target === checkbox) return;
        syncCurrentTransferChecks();
        list.innerHTML = '<div class="dir-item">加载中...</div>';
        try {
          const data = await loadTransferItems(item.id);
          state.transfer.items = data.items || [];
          state.transfer.stack.push({ id: item.id, name: item.name || item.id });
          state.transfer.selectedIds = (state.transfer.items || []).map((x) => x.id);
          renderTransferItemsModal();
        } catch (error) {
          list.innerHTML = `<div class="dir-item">加载失败：${escapeHtml(error.message)}</div>`;
        }
      };
      row.classList.toggle("is-selected", checkbox.checked);
    } else {
      row.innerHTML = `
        <input type="checkbox" data-id="${escapeHtml(item.id)}" ${checked} />
        <div class="transfer-item-main">
          <div class="transfer-item-title">
            <span class="transfer-item-icon">📄</span>
            <span class="transfer-item-name">${escapeHtml(item.name)}</span>
          </div>
          <div class="transfer-item-sub">勾选后将加入本次转存任务</div>
        </div>
        <div class="transfer-item-meta">
          <span class="label">体积</span>
          <span class="value">${metaText}</span>
        </div>
      `;
      const checkbox = row.querySelector("input");
      checkbox.onchange = () => {
        syncCurrentTransferChecks();
        row.classList.toggle("is-selected", checkbox.checked);
        updateTransferSelectionSummary();
        renderTransferStats();
      };
      checkbox.onclick = (e) => e.stopPropagation();
      row.classList.toggle("is-selected", checkbox.checked);
      row.onclick = (e) => {
        if (e.target === checkbox) return;
        checkbox.checked = !checkbox.checked;
        checkbox.dispatchEvent(new Event("change"));
      };
    }
    list.appendChild(row);
  });
}

function closeTransferItemsModal() {
  setModalVisibility("transferItemsModal", false);
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
    const summary = [`任务ID: ${result.task_id}`];
    if (typeof result.kept_count === "number") summary.push(`保留 ${result.kept_count} 项`);
    if (typeof result.skipped_count === "number" && result.skipped_count > 0) {
      summary.push(`跳过 ${result.skipped_count} 项`);
    }
    if (Array.isArray(result.skipped_rules_summary) && result.skipped_rules_summary.length) {
      summary.push(`规则 ${result.skipped_rules_summary.join("，")}`);
    }
    setTransferToast("转存成功，" + summary.join(" / "));
  } catch (error) {
    setTransferToast("转存失败: " + error.message, "warn");
  }
}

async function previewCleanup(targetType) {
  const provider =
    targetType === "local"
      ? "local"
      : document.getElementById("cleanupCloudProvider").value;
  if (targetType === "local") {
    if (!state.cleanupTarget.localRoot) throw new Error("请先选择本地目录");
    appendCleanupLog(`本地开始扫描目录: ${state.cleanupTarget.localRoot}`);
    const es = new EventSource(`/cleanup/stream?local_root=${encodeURIComponent(state.cleanupTarget.localRoot)}`, { withCredentials: true });
    state.cleanupAbort.local = () => {
      stopped = true;
      es.close();
    };
    document.getElementById("cleanupLocalStopBtn").hidden = false;
    document.getElementById("cleanupLocalExecuteBtn").disabled = true;
    let lastResult = null;
    let stopped = false;
    let matchItems = [];
    let matchToken = "";
    await new Promise((resolve, reject) => {
      es.addEventListener("start", (e) => {
        matchToken = e.data;
        state.cleanupPreviewTokens.local = e.data;
      });
      es.addEventListener("log", (e) => {
        if (stopped) return;
        appendCleanupLog(e.data);
      });
      es.addEventListener("match", (e) => {
        if (stopped) return;
        const item = JSON.parse(e.data);
        matchItems.push(item);
        appendCleanupLog(`命中: ${item.name} (${item.rule_name})`);
      });
      es.addEventListener("result", (e) => {
        lastResult = JSON.parse(e.data);
        es.close();
        resolve();
      });
      es.addEventListener("error", (e) => {
        const msg = (e && e.data) || "连接异常";
        if (stopped) { resolve(); return; }
        appendCleanupLog(`扫描错误：${msg}`);
        es.close();
        reject(new Error(msg));
      });
      es.onerror = () => {
        if (es.readyState === EventSource.CLOSED && !lastResult) {
          if (stopped) { resolve(); return; }
          if (state.cleanupPreviewTokens.local) {
            resolve();
            return;
          }
          es.close();
          reject(new Error("扫描连接中断"));
        }
      };
    });
    state.cleanupAbort.local = null;
    document.getElementById("cleanupLocalStopBtn").hidden = true;
    if (stopped || !lastResult) {
      if (state.cleanupPreviewTokens.local) {
        const stoppedRules = buildCleanupRuleStatsFromItems(matchItems);
        renderCleanupPreview({
          preview_token: state.cleanupPreviewTokens.local,
          total_matches: matchItems.length,
          total_size: matchItems.reduce((sum, item) => sum + (item.size || 0), 0),
          rules: stoppedRules,
          items: matchItems,
        });
        appendCleanupLog(`本地扫描已停止，已匹配 ${matchItems.length} 项`);
        const status = document.getElementById("cleanupLocalStatusText");
        if (status) status.textContent = `扫描已停止，${matchItems.length} 项`;
        document.getElementById("cleanupLocalExecuteBtn").disabled = matchItems.length === 0;
      } else {
        appendCleanupLog("本地扫描已停止");
      }
      return;
    }
    const data = lastResult;
    if (!data) throw new Error("未收到扫描结果");
    state.cleanupPreviewTokens.local = data.preview_token || "";
    renderCleanupPreview(data);
    const status = document.getElementById("cleanupLocalStatusText");
    if (status) status.textContent = `命中 ${data.total_matches || 0} 项`;
    appendCleanupLog(`本地预览完成：命中 ${data.total_matches || 0} 项`);
    document.getElementById("cleanupLocalExecuteBtn").disabled = false;
    return data;
  }
  if (!CLEANUP_IMPLEMENTED_PROVIDERS.has(provider)) {
    throw new Error("该网盘暂未支持清理");
  }
  appendCleanupLog(`网盘开始扫描目录: ${state.cleanupTarget.parentPath || "/"}`);
  startCleanupLogTail();
  let data;
  try {
    data = await api("/cleanup/preview", {
      method: "POST",
      body: JSON.stringify({ provider, parent_id: state.cleanupTarget.parentId || "0" }),
    });
    await pumpCleanupLogs();
  } finally {
    stopCleanupLogTail();
  }
  state.cleanupPreviewTokens.cloud = data.preview_token || "";
  renderCleanupPreview(data);
  const status = document.getElementById("cleanupCloudStatusText");
  if (status) status.textContent = `命中 ${data.total_matches || 0} 项`;
  appendCleanupLog(`网盘预览完成：命中 ${data.total_matches || 0} 项`);
  state.cleanupPhase.cloud = "execute";
  setCleanupActionButton("cloud");
  return data;
}

async function executeCleanup(targetType) {
  if (targetType === "local") {
    const token = state.cleanupPreviewTokens.local;
    if (!token) throw new Error("请先执行本地预览");
    const selectedIds = state.cleanupSelected.slice();
    appendCleanupLog(`本地清理开始: ${state.cleanupTarget.localRoot || "-"}`);
    const controller = new AbortController();
    state.cleanupAbort.local = () => { controller.abort(); };
    document.getElementById("cleanupLocalStopBtn").hidden = false;
    let data;
    try {
      data = await fetch("/cleanup/execute", {
        method: "POST",
        headers: { "content-type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ preview_token: token, selected_ids: selectedIds }),
        signal: controller.signal,
      }).then(r => { if (!r.ok) throw new Error("请求失败"); return r.json(); });
    } catch (err) {
      if (err.name === "AbortError") {
        appendCleanupLog("本地清理已停止");
        state.cleanupAbort.local = null;
        document.getElementById("cleanupLocalStopBtn").hidden = true;
        return;
      }
      throw err;
    }
    state.cleanupAbort.local = null;
    document.getElementById("cleanupLocalStopBtn").hidden = true;
    state.cleanupPreviewTokens.local = "";
    const status = document.getElementById("cleanupLocalStatusText");
    if (status) status.textContent = `已删除 ${data.deleted_count || 0} 项`;
    appendCleanupLog(`本地清理完成：删除 ${data.deleted_count || 0} 项`);
    state.cleanupPhase.local = "preview";
    document.getElementById("cleanupLocalExecuteBtn").disabled = true;
    return data;
  }
  if (!state.cleanupPreviewTokens.cloud) throw new Error("请先执行网盘扫描预览");
  appendCleanupLog("网盘清理开始");
  const data = await api("/cleanup/execute", {
    method: "POST",
    body: JSON.stringify({ preview_token: state.cleanupPreviewTokens.cloud }),
  });
  state.cleanupPreviewTokens.cloud = "";
  const status = document.getElementById("cleanupCloudStatusText");
  if (status) status.textContent = `已删除 ${data.deleted_count || 0} 项`;
  appendCleanupLog(`网盘清理完成：删除 ${data.deleted_count || 0} 项`);
  state.cleanupPhase.cloud = "preview";
  setCleanupActionButton("cloud");
  return data;
}

function selectedRows() {
  return state.filtered.filter((row) => state.selectedResultIds.has(resultId(row)));
}

async function batchTransferSelected() {
  const rows = selectedRows();
  if (!rows.length) {
    setTransferToast("请先选择要转存的搜索结果", "warn");
    return;
  }
  const checks = [];
  for (const row of rows) {
    const sourceUri = row.magnet || row.link;
    if (!sourceUri) continue;
    const check = await api("/tasks/offline/check", {
      method: "POST",
      body: JSON.stringify({ source_uri: sourceUri, cloud_type: row.cloud_type || "" }),
    });
    if (!check.supported || !check.configured) {
      setTransferToast(`${row.title || "资源"}：${check.message || "不可转存"}`, "warn");
      return;
    }
    checks.push({ row, check, provider: check.provider === "magnet" || check.provider === "ed2k" ? "115" : check.provider });
  }
  if (!checks.length) {
    setTransferToast("所选结果没有可转存链接", "warn");
    return;
  }
  const provider = checks[0].provider;
  if (!checks.every((x) => x.provider === provider)) {
    setTransferToast("批量转存暂只支持同一种目标网盘，请先筛选网盘类型", "warn");
    return;
  }
  const last = getLastDir(provider);
  const dirId = last?.id || checks[0].check.default_dir_id || "0";
  const dirPath = last?.path || checks[0].check.default_dir_path || "/";
  await openDirPicker(dirId, dirPath, provider, "", async (choice) => {
    setLastDir(provider, choice);
    let ok = 0;
    for (const item of checks) {
      const sourceUri = item.row.magnet || item.row.link;
      try {
        await api("/transfer/commit", {
          method: "POST",
          body: JSON.stringify({
            source_uri: sourceUri,
            target_dir_id: choice.id || "0",
            selected_ids: [],
            cloud_type: item.row.cloud_type || item.provider,
          }),
        });
        ok += 1;
      } catch (error) {
        setTransferToast(`批量转存部分失败：${error.message}`, "warn");
      }
    }
    setTransferToast(`批量转存已提交 ${ok}/${checks.length} 个任务`);
  });
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
    state.transfer.selectedIds = (state.transfer.items || []).map((x) => x.id);
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
    state.detailCache.clear();
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
  const searchFilterToggleBtn = document.getElementById("searchFilterToggleBtn");
  if (searchFilterToggleBtn) {
    searchFilterToggleBtn.onclick = () => {
      const head = document.querySelector(".search-head");
      const opened = head.classList.toggle("search-advanced-open");
      searchFilterToggleBtn.textContent = opened ? "收起筛选" : "筛选";
    };
  }
  const recommendFilterToggleBtn = document.getElementById("recommendFilterToggleBtn");
  if (recommendFilterToggleBtn) {
    recommendFilterToggleBtn.onclick = () => {
      const head = document.querySelector(".hero");
      const opened = head.classList.toggle("recommend-advanced-open");
      recommendFilterToggleBtn.textContent = opened ? "收起筛选" : "筛选";
    };
  }

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
      renderResourceList();
      writeUiStateToUrl();
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
  document.getElementById("toggleResultSelectBtn").onclick = () => {
    state.resultSelectMode = !state.resultSelectMode;
    document.getElementById("toggleResultSelectBtn").textContent = state.resultSelectMode ? "退出选择" : "选择结果";
    if (!state.resultSelectMode) state.selectedResultIds.clear();
    renderResourceList();
  };

  document.getElementById("settingsTabs").querySelectorAll("button").forEach((btn) => {
    btn.onclick = () => switchSettingsTab(btn.dataset.tab);
  });

  document.getElementById("settingsForm").onsubmit = saveSettings;
  document.getElementById("saveSettingsTop").onclick = saveSettings;
  document.querySelectorAll(".btn-secret-toggle[data-secret-target]").forEach((btn) => {
    btn.onclick = () => {
      const input = document.getElementById(btn.dataset.secretTarget);
      if (!input) return;
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      const nextLabel = show ? "隐藏内容" : "显示内容";
      btn.setAttribute("aria-label", nextLabel);
      btn.setAttribute("title", nextLabel);
      btn.setAttribute("aria-pressed", show ? "true" : "false");
      const text = btn.querySelector(".sr-only");
      if (text) text.textContent = nextLabel;
    };
  });
  document.getElementById("logoutBtn").onclick = doLogout;
  document.getElementById("showLogsBtn").onclick = async () => {
    setModalVisibility("logsModal", true);
    await loadLogs();
  };
  document.getElementById("refreshLogsBtn").onclick = loadLogs;
  document.getElementById("logLevelFilter").onchange = loadLogs;
  document.getElementById("closeLogsBtn").onclick = () => {
    setModalVisibility("logsModal", false);
  };

  document.querySelectorAll(".btn-test-provider").forEach((btn) => {
    btn.onclick = () => testProvider(btn.dataset.provider);
  });
  document.getElementById("loginRemember").onchange = (e) => {
    if (!e.target.checked) {
      clearRememberedLogin();
    }
  };

  renderPansouCloudTypeSelect();
  document.getElementById("addCloudTypeBtn").onclick = () => {
    const value = document.getElementById("pansouCloudTypeSelect").value;
    if (!value) return;
    if (!state.pansouCloudTypes.includes(value)) state.pansouCloudTypes.push(value);
    syncPansouCloudTypesField();
    renderPansouCloudTypeChips();
  };
  document.getElementById("addFilterRuleBtn").onclick = () => {
    state.resourceFilterRules.push({
      id: `custom-${Date.now()}`,
      name: "新规则",
      enabled: true,
      glob: "",
      min_size_mb: null,
      max_size_mb: null,
      applies_to: "both",
    });
    renderFilterRules();
  };
  document.getElementById("resetFilterRulesBtn").onclick = () => {
    state.resourceFilterRules = defaultResourceFilterRules();
    renderFilterRules();
  };
  document.getElementById("cleanupPickLocalDirBtn").onclick = async () => {
    await openDirPicker(
      state.cleanupTarget.localRoot || "",
      state.cleanupTarget.localRoot || "/",
      "local",
      "",
      async (choice) => {
        state.cleanupTarget.localRoot = choice.id || "";
        state.cleanupPreviewTokens.local = "";
        state.cleanupPhase.local = "preview";
        document.getElementById("cleanupLocalExecuteBtn").disabled = true;
        renderCleanupPreview(null);
        renderCleanupTarget();
        appendCleanupLog(`本地起始目录：${state.cleanupTarget.localRoot || "-"}`);
      }
    );
  };
  const cloudBtn = document.getElementById("cleanupCloudActionBtn");
  if (cloudBtn) cloudBtn.onclick = async () => {
    try {
      if (state.cleanupPhase.cloud === "preview") {
        await previewCleanup("cloud");
        setStatus("网盘清理预览完成");
      } else {
        if (!state.cleanupPreviewTokens.cloud) {
          appendCleanupLog("请先执行网盘扫描预览，再执行清理");
          setStatus("请先执行网盘扫描预览", "warn");
          return;
        }
        const data = await executeCleanup("cloud");
        setStatus(`网盘清理完成，已删除 ${data.deleted_count || 0} 项`);
        renderCleanupPreview(null);
      }
    } catch (error) {
      appendCleanupLog(`网盘清理失败：${error.message}`);
      setStatus(`网盘清理失败：${error.message}`, "warn");
    }
  };
  document.getElementById("cleanupLocalPreviewBtn").onclick = async () => {
    try {
      document.getElementById("cleanupLocalExecuteBtn").disabled = true;
      renderCleanupPreview(null);
      await previewCleanup("local");
      setStatus("本地清理预览完成");
    } catch (error) {
      appendCleanupLog(`本地清理失败：${error.message}`);
      setStatus(`清理失败：${error.message}`, "warn");
    }
  };
  document.getElementById("cleanupLocalExecuteBtn").onclick = async () => {
    try {
      if (!state.cleanupPreviewTokens.local) {
        appendCleanupLog("请先执行本地预览，再执行清理");
        setStatus("请先执行本地预览", "warn");
        return;
      }
      const data = await executeCleanup("local");
      setStatus(`本地清理完成，已删除 ${data.deleted_count || 0} 项`);
      renderCleanupPreview(null);
    } catch (error) {
      appendCleanupLog(`本地清理失败：${error.message}`);
      setStatus(`清理失败：${error.message}`, "warn");
    }
  };
  document.getElementById("cleanupLocalStopBtn").onclick = () => {
    const abort = state.cleanupAbort.local;
    if (abort) {
      appendCleanupLog("正在停止...");
      abort();
      state.cleanupAbort.local = null;
    }
    document.getElementById("cleanupLocalStopBtn").hidden = true;
  };

  document.getElementById("dirPickerBackBtn").onclick = async () => {
    if (state.dirPicker.stack.length > 1) {
      state.dirPicker.stack.pop();
      syncDirPickerBackButton();
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
  document.getElementById("transferSelectAllBtn").onclick = () => {
    syncCurrentTransferChecks();
    const currentItems = state.transfer.items || [];
    const allSelected = currentItems.length > 0 && currentItems.every((x) => state.transfer.selectedIds.includes(x.id));
    const currentIds = new Set(currentItems.map((x) => x.id));
    state.transfer.selectedIds = state.transfer.selectedIds.filter((id) => !currentIds.has(id));
    if (!allSelected) state.transfer.selectedIds.push(...currentItems.map((x) => x.id));
    renderTransferItemsModal();
  };
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
      state.transfer.selectedIds = (state.transfer.items || []).map((x) => x.id);
      renderTransferItemsModal();
    } catch (error) {
      list.innerHTML = `<div class="dir-item">加载失败：${escapeHtml(error.message)}</div>`;
    }
  };

  document.getElementById("loginForm").onsubmit = doLogin;
}

async function bootstrapAfterLogin() {
  const initialPage = location.hash.replace("#", "") || "search";
  await loadSettings();
  await loadRecommendCategories();
  await loadAppInfo();
  switchSettingsTab("media");
  showPage(initialPage);
}

async function init() {
  applyFormAccessibilityDefaults();
  bindModalEscapeClose();
  bindEvents();
  bindHeaderCondenseBehavior();
  syncSearchFilterToggleButtonText();
  window.addEventListener("resize", syncSearchFilterToggleButtonText);
  const initialPage = applyUiStateFromUrl();
  const sourceBtn = document.querySelector(`#sourceTabs button[data-source="${state.sourceFilter}"]`);
  if (sourceBtn) {
    document.getElementById("sourceTabs").querySelectorAll("button").forEach((x) => x.classList.remove("active"));
    sourceBtn.classList.add("active");
  }
  const viewBtn = document.querySelector(`#resultViewTabs button[data-view="${state.resultView}"]`);
  if (viewBtn) {
    document.getElementById("resultViewTabs").querySelectorAll("button").forEach((x) => x.classList.remove("active"));
    viewBtn.classList.add("active");
  }
  const cloudTypeFilter = document.getElementById("cloudTypeFilter");
  if (cloudTypeFilter) cloudTypeFilter.value = state.cloudTypeFilter;
  const sortBy = document.getElementById("sortBy");
  if (sortBy) sortBy.value = state.sortBy;
  setVisiblePage(initialPage);
  const ok = await ensureAuth();
  if (!ok) return;
  await bootstrapAfterLogin();
}

init().catch((error) => setStatus("初始化失败: " + error.message, "warn"));
