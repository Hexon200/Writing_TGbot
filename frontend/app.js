const tg = window.Telegram?.WebApp;
const content = document.querySelector("#content");
const viewTitle = document.querySelector("#viewTitle");
const searchInput = document.querySelector("#globalSearch");
const searchResults = document.querySelector("#searchResults");
const sheet = document.querySelector("#phraseSheet");
const backdrop = document.querySelector("#sheetBackdrop");
const syncButton = document.querySelector("#syncButton");

const subtypeLabels = {
  line_graph: "Line graph",
  bar_chart: "Bar chart",
  pie_chart: "Pie chart",
  table: "Table",
  process_diagram: "Process",
  maps: "Maps",
  mixed_charts: "Mixed charts",
  opinion_agree_disagree: "Opinion",
  discussion_both_views: "Discussion",
  problem_solution: "Problem-solution",
  advantage_disadvantage: "Advantages",
  two_part_question: "Two-part",
};

const categoryLabels = {
  describing_trends: "Trends",
  comparing_contrasting: "Compare",
  giving_opinion: "Opinion",
  hedging: "Hedging",
  concluding_overview: "Overview",
  cohesion_linking: "Linking",
  paraphrasing_prompts: "Paraphrase",
  maps_process: "Maps/process",
  band_descriptors: "Band descriptors",
  task_1_structure: "Task 1",
  task_2_structure: "Task 2",
  common_mistakes: "Mistakes",
  time_management: "Timing",
  phrase_bank: "Phrase bank",
};

const state = {
  tab: "task1",
  filters: {
    task1: "all",
    task2: "all",
    phrases: "all",
    tips: "all",
  },
  bookmarks: new Set(),
  userId: getUserId(),
};

const cache = new Map();

init();

function init() {
  tg?.ready();
  tg?.expand();
  applyTelegramTheme();
  bindEvents();
  loadBookmarks().finally(() => renderTab("task1"));
}

function applyTelegramTheme() {
  const p = tg?.themeParams || {};
  const root = document.documentElement;
  if (p.bg_color) root.style.setProperty("--bg", p.bg_color);
  if (p.secondary_bg_color) root.style.setProperty("--surface", p.secondary_bg_color);
  if (p.text_color) root.style.setProperty("--text", p.text_color);
  if (p.hint_color) root.style.setProperty("--muted", p.hint_color);
  if (p.button_color) root.style.setProperty("--accent", p.button_color);
  if (p.link_color) root.style.setProperty("--accent-2", p.link_color);
}

function bindEvents() {
  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => renderTab(button.dataset.tab));
  });
  searchInput.addEventListener("input", debounce(handleSearch, 220));
  syncButton.addEventListener("click", async () => {
    cache.clear();
    await loadBookmarks();
    await renderTab(state.tab);
  });
  backdrop.addEventListener("click", closePhraseSheet);
}

function getUserId() {
  const telegramId = tg?.initDataUnsafe?.user?.id;
  if (telegramId) return String(telegramId);
  const key = "ielts-demo-user-id";
  let localId = localStorage.getItem(key);
  if (!localId) {
    localId = `demo-${crypto.randomUUID()}`;
    localStorage.setItem(key, localId);
  }
  return localId;
}

async function renderTab(tab) {
  state.tab = tab;
  document.querySelectorAll(".tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tab);
  });
  searchResults.classList.add("hidden");
  searchInput.value = "";
  content.focus({ preventScroll: true });

  if (tab === "task1") {
    viewTitle.textContent = "Task 1";
    return renderSampleList(1, "task1");
  }
  if (tab === "task2") {
    viewTitle.textContent = "Task 2";
    return renderSampleList(2, "task2");
  }
  if (tab === "phrases") {
    viewTitle.textContent = "Phrases";
    return renderPhrases();
  }
  if (tab === "quiz") {
    viewTitle.textContent = "Quiz";
    return renderQuiz();
  }
  if (tab === "tips") {
    viewTitle.textContent = "Tips";
    return renderTips();
  }
  viewTitle.textContent = "Bookmarks";
  return renderBookmarks();
}

async function renderSampleList(taskType, filterKey) {
  content.innerHTML = "";
  const samples = await getJson(`/api/samples?task=${taskType}`, `samples-${taskType}`);
  const subtypes = ["all", ...unique(samples.items.map((item) => item.subtype))];
  content.append(chips(subtypes, state.filters[filterKey], (value) => {
    state.filters[filterKey] = value;
    renderSampleList(taskType, filterKey);
  }));
  const visible = state.filters[filterKey] === "all"
    ? samples.items
    : samples.items.filter((item) => item.subtype === state.filters[filterKey]);
  content.append(grid(visible.map(sampleCard)));
}

async function renderPhrases() {
  content.innerHTML = "";
  const phrases = await getJson("/api/phrases", "phrases", true);
  const categories = ["all", ...unique(phrases.items.map((item) => item.category))];
  content.append(chips(categories, state.filters.phrases, (value) => {
    state.filters.phrases = value;
    renderPhrases();
  }));
  const visible = state.filters.phrases === "all"
    ? phrases.items
    : phrases.items.filter((item) => item.category === state.filters.phrases);
  content.append(grid(visible.map(phraseCard)));
}

async function renderTips() {
  content.innerHTML = "";
  const tips = await getJson("/api/tips", "tips", true);
  const categories = ["all", ...unique(tips.items.map((item) => item.category))];
  content.append(chips(categories, state.filters.tips, (value) => {
    state.filters.tips = value;
    renderTips();
  }));
  const visible = state.filters.tips === "all"
    ? tips.items
    : tips.items.filter((item) => item.category === state.filters.tips);
  content.append(grid(visible.map(tipCard)));
}

async function renderBookmarks() {
  content.innerHTML = "";
  await loadBookmarks();
  const data = await fetchJson(`/api/bookmarks?telegram_user_id=${encodeURIComponent(state.userId)}`);
  if (!data.items.length) {
    content.append(emptyState("No bookmarks yet."));
    return;
  }
  const grouped = groupBy(data.items, (entry) => entry.item_type);
  for (const [type, entries] of Object.entries(grouped)) {
    const heading = document.createElement("div");
    heading.className = "section-title";
    heading.textContent = `${type}s`;
    content.append(heading);
    const cards = entries.map((entry) => {
      if (entry.item_type === "sample") return sampleCard(entry.item);
      if (entry.item_type === "phrase") return phraseCard(entry.item);
      return tipCard(entry.item);
    });
    content.append(grid(cards));
  }
}

async function renderQuiz() {
  clearSearch();
  content.innerHTML = "";
  const data = await fetchJson(`/api/quiz/next?telegram_user_id=${encodeURIComponent(state.userId)}`);
  if (data.source !== "due_bookmark") {
    content.append(caughtUpPanel(data));
  }
  content.append(quizCard(data));
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function caughtUpPanel(data) {
  const stats = data.stats || {};
  const total = stats.total_bookmarked || 0;
  const reviewed = stats.reviewed_count || 0;
  const percent = total ? Math.round((reviewed / total) * 100) : 100;
  const panel = el("section", "caught-up detail-panel");
  panel.innerHTML = `
    <div class="meta"><span class="pill">${data.is_new ? "Discovery" : "Review"}</span></div>
    <h2 class="title">You are all caught up.</h2>
    <p class="muted">${data.is_new ? "No phrase bookmarks yet. Try this starter card and it will enter your review queue." : "No bookmarked phrases are due right now. This practice card keeps the rhythm warm."}</p>
    <div class="progress-meter" aria-label="Review progress">
      <span style="width: ${percent}%"></span>
    </div>
    <div class="progress-bars" aria-hidden="true">
      ${[0, 1, 2, 3, 4].map((index) => `<span class="${index * 20 < percent ? "active" : ""}"></span>`).join("")}
    </div>
    <div class="meta">
      <span>${stats.due_count || 0} due</span>
      <span>${total} saved phrases</span>
      <span>${percent}% clear</span>
    </div>
  `;
  return panel;
}

function quizCard(data) {
  const phrase = data.phrase;
  const card = el("article", "quiz-card");
  card.innerHTML = `
    <div class="card-header">
      <div>
        <div class="meta">
          <span class="pill">${data.source === "due_bookmark" ? "Due now" : data.is_new ? "New phrase" : "Practice"}</span>
          <span>${labelFor(phrase.category)}</span>
        </div>
        <div class="quiz-prompt">${escapeHtml(phrase.phrase)}</div>
      </div>
    </div>
    <div class="quiz-answer hidden">
      <p class="phrase-example">${escapeHtml(phrase.example)}</p>
      ${phrase.band_note ? `<p class="band-note">${escapeHtml(phrase.band_note)}</p>` : ""}
    </div>
    <div class="quiz-actions">
      <button type="button" class="primary-action">Show example</button>
      <div class="rating-row hidden">
        <button type="button" class="rating-button again" data-quality="1">Again</button>
        <button type="button" class="rating-button good" data-quality="3">Good</button>
        <button type="button" class="rating-button easy" data-quality="5">Easy</button>
      </div>
    </div>
    <div class="quiz-feedback muted" aria-live="polite"></div>
  `;
  const answer = card.querySelector(".quiz-answer");
  const flip = card.querySelector(".primary-action");
  const ratings = card.querySelector(".rating-row");
  const feedback = card.querySelector(".quiz-feedback");
  flip.addEventListener("click", () => {
    answer.classList.remove("hidden");
    ratings.classList.remove("hidden");
    flip.classList.add("hidden");
    card.classList.add("flipped");
  });
  ratings.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", async () => {
      const quality = Number(button.dataset.quality);
      card.classList.add("reviewed");
      feedback.textContent = "Scheduling...";
      const result = await fetchJson("/api/quiz/answer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          telegram_user_id: state.userId,
          item_id: data.item_id,
          quality,
        }),
      });
      state.bookmarks.add(bookmarkKey("phrase", data.item_id));
      feedback.textContent = `Next review in ${result.interval} day${result.interval === 1 ? "" : "s"}.`;
      tg?.HapticFeedback?.notificationOccurred?.("success");
      window.setTimeout(() => renderQuiz(), 700);
    });
  });
  return card;
}

function sampleCard(sample) {
  const card = el("article", "card");
  card.innerHTML = `
    <div class="card-header">
      <div>
        <div class="meta">
          <span class="pill">Task ${sample.task_type}</span>
          <span>Band ${sample.band_score}</span>
          <span>${labelFor(sample.subtype)}</span>
        </div>
        <h2 class="title">${escapeHtml(sample.title)}</h2>
      </div>
    </div>
    <div class="preview">${escapeHtml(sample.preview)}</div>
  `;
  const bookmark = bookmarkButton("sample", sample.id);
  card.querySelector(".card-header").append(bookmark);
  card.addEventListener("click", (event) => {
    if (event.target.closest("button")) return;
    renderSampleDetail(sample.id);
  });
  return card;
}

async function renderSampleDetail(sampleId) {
  clearSearch();
  const sample = await fetchJson(`/api/samples/${sampleId}`);
  viewTitle.textContent = `Band ${sample.band_score}`;
  content.innerHTML = "";
  const panel = el("article", "detail-panel");
  const image = sample.prompt_image_url
    ? `<img class="prompt-image" src="${escapeAttribute(sample.prompt_image_url)}" alt="">`
    : "";
  panel.innerHTML = `
    <div class="detail-header">
      <div>
        <div class="meta">
          <span class="pill">Task ${sample.task_type}</span>
          <span>${labelFor(sample.subtype)}</span>
        </div>
        <h2 class="title">${escapeHtml(sample.title)}</h2>
      </div>
    </div>
    <p class="prompt-text">${escapeHtml(sample.prompt_text)}</p>
    ${image}
    <div class="answer"></div>
    <div class="section-title">Structure</div>
    <div class="breakdown"></div>
  `;
  panel.querySelector(".detail-header").append(bookmarkButton("sample", sample.id));
  renderBodySegments(panel.querySelector(".answer"), sample.body_segments);
  const breakdown = panel.querySelector(".breakdown");
  sample.structure_breakdown.forEach((row) => {
    const item = el("div", "breakdown-row");
    item.innerHTML = `<strong>${escapeHtml(row.label)}</strong><span>${escapeHtml(row.note)}</span>`;
    breakdown.append(item);
  });
  content.append(panel);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function phraseCard(phrase) {
  const card = el("article", "card");
  card.innerHTML = `
    <div class="card-header">
      <div>
        <div class="meta"><span class="pill">${labelFor(phrase.category)}</span></div>
        <div class="phrase-text">${escapeHtml(phrase.phrase)}</div>
      </div>
    </div>
    <div class="phrase-example">${escapeHtml(phrase.example)}</div>
    ${phrase.band_note ? `<div class="band-note">${escapeHtml(phrase.band_note)}</div>` : ""}
  `;
  const actions = el("div", "sheet-actions");
  actions.append(copyButton(phrase.phrase), bookmarkButton("phrase", phrase.id));
  card.querySelector(".card-header").append(actions);
  card.addEventListener("click", (event) => {
    if (event.target.closest("button")) return;
    openPhraseSheet(phrase);
  });
  return card;
}

function tipCard(tip) {
  const card = el("article", "card");
  card.innerHTML = `
    <div class="card-header">
      <div>
        <div class="meta">
          <span class="pill">${labelFor(tip.category)}</span>
          ${tip.descriptor ? `<span>${escapeHtml(tip.descriptor)}</span>` : ""}
        </div>
        <h2 class="title">${escapeHtml(tip.title)}</h2>
      </div>
    </div>
    <div class="tip-body">${escapeHtml(tip.body)}</div>
  `;
  card.querySelector(".card-header").append(bookmarkButton("tip", tip.id));
  return card;
}

function renderSingleTip(tip) {
  clearSearch();
  viewTitle.textContent = "Tip";
  content.innerHTML = "";
  content.append(tipCard(tip));
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderBodySegments(container, segments) {
  let paragraph = document.createElement("p");
  container.append(paragraph);
  for (const segment of segments) {
    const parts = segment.text.split("\n\n");
    parts.forEach((part, index) => {
      if (part) {
        if (segment.type === "phrase" && segment.phrase) {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "inline-phrase";
          button.textContent = part;
          button.addEventListener("click", () => openPhraseSheet(segment.phrase));
          paragraph.append(button);
        } else {
          paragraph.append(document.createTextNode(part));
        }
      }
      if (index < parts.length - 1) {
        paragraph = document.createElement("p");
        container.append(paragraph);
      }
    });
  }
}

async function openPhraseSheet(phrase) {
  const full = phrase.id ? await fetchJson(`/api/phrases/${phrase.id}`) : phrase;
  sheet.innerHTML = `
    <div class="sheet-header">
      <div>
        <div class="meta"><span class="pill">${labelFor(full.category)}</span></div>
        <div class="phrase-text">${escapeHtml(full.phrase)}</div>
      </div>
      <div class="sheet-actions"></div>
    </div>
    <p class="phrase-example">${escapeHtml(full.example)}</p>
    ${full.band_note ? `<p class="band-note">${escapeHtml(full.band_note)}</p>` : ""}
    <div class="related"></div>
  `;
  const actions = sheet.querySelector(".sheet-actions");
  actions.append(copyButton(full.phrase), bookmarkButton("phrase", full.id), closeButton());
  const related = sheet.querySelector(".related");
  if (full.related_slugs?.length) {
    const phrases = await getJson("/api/phrases", "phrases", true);
    full.related_slugs
      .map((slug) => phrases.items.find((item) => item.slug === slug))
      .filter(Boolean)
      .forEach((item) => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = item.phrase;
        button.addEventListener("click", () => openPhraseSheet(item));
        related.append(button);
      });
  }
  sheet.classList.remove("hidden");
  backdrop.classList.remove("hidden");
}

function closePhraseSheet() {
  sheet.classList.add("hidden");
  backdrop.classList.add("hidden");
}

async function handleSearch() {
  const q = searchInput.value.trim();
  if (q.length < 2) {
    searchResults.classList.add("hidden");
    searchResults.innerHTML = "";
    return;
  }
  const data = await fetchJson(`/api/search?q=${encodeURIComponent(q)}`);
  searchResults.innerHTML = "";
  const panel = el("section", "search-panel");
  const total = data.samples.length + data.phrases.length + data.tips.length;
  if (!total) {
    panel.append(emptyState("No results."));
  } else {
    panel.append(searchSection("Samples", data.samples, (item) => `Task ${item.task_type} \u00b7 Band ${item.band_score}`, (item) => renderSampleDetail(item.id)));
    panel.append(searchSection("Phrases", data.phrases, (item) => labelFor(item.category), (item) => openPhraseSheet(item)));
    panel.append(searchSection("Tips", data.tips, (item) => labelFor(item.category), (item) => renderSingleTip(item)));
  }
  searchResults.append(panel);
  searchResults.classList.remove("hidden");
}

function searchSection(title, items, subtitle, action) {
  const wrapper = document.createElement("div");
  if (!items.length) return wrapper;
  const heading = el("div", "section-title");
  heading.textContent = title;
  wrapper.append(heading);
  const list = el("div", "result-list");
  items.forEach((item) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "result-row";
    row.innerHTML = `
      <strong>${escapeHtml(item.title || item.phrase)}</strong>
      <span class="muted">${escapeHtml(subtitle(item))}</span>
    `;
    row.addEventListener("click", () => {
      clearSearch();
      action(item);
    });
    list.append(row);
  });
  wrapper.append(list);
  return wrapper;
}

function bookmarkButton(type, id) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "bookmark-button";
  button.title = "Bookmark";
  const key = bookmarkKey(type, id);
  button.textContent = state.bookmarks.has(key) ? "\u2605" : "\u2606";
  button.addEventListener("click", async (event) => {
    event.stopPropagation();
    await toggleBookmark(type, id);
    button.textContent = state.bookmarks.has(key) ? "\u2605" : "\u2606";
  });
  return button;
}

function copyButton(text) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "copy-button";
  button.title = "Copy";
  button.textContent = "\u29c9";
  button.addEventListener("click", async (event) => {
    event.stopPropagation();
    await copyText(text);
    tg?.HapticFeedback?.notificationOccurred?.("success");
    button.textContent = "\u2713";
    window.setTimeout(() => {
      button.textContent = "\u29c9";
    }, 900);
  });
  return button;
}

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.append(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

function clearSearch() {
  searchInput.value = "";
  searchResults.innerHTML = "";
  searchResults.classList.add("hidden");
}

function closeButton() {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "close-button";
  button.title = "Close";
  button.textContent = "\u00d7";
  button.addEventListener("click", closePhraseSheet);
  return button;
}

async function toggleBookmark(type, id) {
  const key = bookmarkKey(type, id);
  const bookmarked = state.bookmarks.has(key);
  const method = bookmarked ? "DELETE" : "POST";
  await fetchJson("/api/bookmarks", {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      telegram_user_id: state.userId,
      item_type: type,
      item_id: id,
    }),
  });
  if (bookmarked) state.bookmarks.delete(key);
  else state.bookmarks.add(key);
  tg?.HapticFeedback?.impactOccurred?.("light");
}

async function loadBookmarks() {
  const data = await fetchJson(`/api/bookmarks?telegram_user_id=${encodeURIComponent(state.userId)}`);
  state.bookmarks = new Set(data.items.map((entry) => bookmarkKey(entry.item_type, entry.item.id)));
}

function bookmarkKey(type, id) {
  return `${type}:${id}`;
}

function chips(values, active, onClick) {
  const wrap = el("div", "chips");
  values.forEach((value) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `chip${value === active ? " active" : ""}`;
    button.textContent = value === "all" ? "All" : labelFor(value);
    button.addEventListener("click", () => onClick(value));
    wrap.append(button);
  });
  return wrap;
}

function grid(items) {
  const wrap = el("div", "grid");
  if (!items.length) {
    wrap.append(emptyState("Nothing here yet."));
    return wrap;
  }
  items.forEach((item) => wrap.append(item));
  return wrap;
}

function emptyState(text) {
  const node = el("div", "empty-state");
  node.textContent = text;
  return node;
}

async function getJson(url, key, persistent = false) {
  if (cache.has(key)) return cache.get(key);
  if (persistent) {
    const cached = localStorage.getItem(`cache:${key}`);
    if (cached) {
      try {
        const parsed = JSON.parse(cached);
        cache.set(key, parsed);
        fetchJson(url).then((fresh) => {
          cache.set(key, fresh);
          localStorage.setItem(`cache:${key}`, JSON.stringify(fresh));
        });
        return parsed;
      } catch {
        localStorage.removeItem(`cache:${key}`);
      }
    }
  }
  const data = await fetchJson(url);
  cache.set(key, data);
  if (persistent) localStorage.setItem(`cache:${key}`, JSON.stringify(data));
  return data;
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json();
}

function labelFor(value) {
  return categoryLabels[value] || subtypeLabels[value] || value.replaceAll("_", " ");
}

function unique(values) {
  return Array.from(new Set(values));
}

function groupBy(items, getter) {
  return items.reduce((acc, item) => {
    const key = getter(item);
    acc[key] ||= [];
    acc[key].push(item);
    return acc;
  }, {});
}

function debounce(fn, delay) {
  let id;
  return (...args) => {
    clearTimeout(id);
    id = setTimeout(() => fn(...args), delay);
  };
}

function el(tag, className) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  return node;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}
