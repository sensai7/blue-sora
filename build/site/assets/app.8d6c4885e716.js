(() => {
  const root = document.documentElement;
  const toggle = document.querySelector("[data-theme-toggle]");
  if (!toggle) return;

  const saved = localStorage.getItem("blue-sora-theme");
  const preferredDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const initial = saved || (preferredDark ? "dark" : "light");

  function applyTheme(theme) {
    root.dataset.theme = theme;
    const dark = theme === "dark";
    toggle.setAttribute("aria-pressed", String(dark));
    toggle.setAttribute("aria-label", dark ? "Use light theme" : "Use dark theme");
  }

  applyTheme(initial);
  toggle.addEventListener("click", () => {
    const next = root.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(next);
    localStorage.setItem("blue-sora-theme", next);
  });
})();

(() => {
  const grid = document.querySelector("[data-library-grid]");
  const form = document.querySelector("[data-library-form]");
  if (!grid || !form) return;

  const status = document.querySelector("[data-library-status]");
  const empty = document.querySelector("[data-empty-state]");
  const pagination = document.querySelector("[data-pagination]");
  const summary = document.querySelector("[data-page-summary]");
  const previous = document.querySelector("[data-page-previous]");
  const next = document.querySelector("[data-page-next]");
  const activeFilters = document.querySelector("[data-active-filters]");
  const pageSize = 24;
  const allowed = {
    difficulty: ["approachable", "intermediate", "advanced", "unscored"],
    length: ["short", "medium", "long"],
    era: ["Meiji", "Taisho", "Showa"],
    metadata: ["scored", "illustrated", "old-orthography"],
    sort: ["title", "author", "length-asc", "length-desc", "difficulty-asc", "difficulty-desc"]
  };
  let works = [];
  let invalidParameters = [];

  const normalize = (value) => value.normalize("NFKC").toLocaleLowerCase("ja").trim();
  const field = (name) => form.elements.namedItem(name);

  function readState() {
    const params = new URLSearchParams(window.location.search);
    invalidParameters = [];
    const state = { q: params.get("q") || "", page: Number.parseInt(params.get("page") || "1", 10) };
    for (const name of ["difficulty", "length", "author", "era", "metadata", "sort"]) {
      state[name] = params.get(name) || "";
      if (name !== "author" && state[name] && !allowed[name].includes(state[name])) {
        invalidParameters.push(name);
        state[name] = "";
      }
    }
    const authorOptions = [...field("author").options].map((option) => option.value);
    if (state.author && !authorOptions.includes(state.author)) {
      invalidParameters.push("author");
      state.author = "";
    }
    if (!Number.isFinite(state.page) || state.page < 1) {
      invalidParameters.push("page");
      state.page = 1;
    }
    if (!state.sort) state.sort = "title";
    return state;
  }

  function syncForm(state) {
    for (const name of ["q", "difficulty", "length", "author", "era", "metadata", "sort"]) field(name).value = state[name];
  }

  function writeState(state, replace = false) {
    const params = new URLSearchParams();
    for (const name of ["q", "difficulty", "length", "author", "era", "metadata", "sort"]) {
      if (state[name] && !(name === "sort" && state[name] === "title")) params.set(name, state[name]);
    }
    if (state.page > 1) params.set("page", String(state.page));
    const url = `${window.location.pathname}${params.size ? `?${params}` : ""}${window.location.hash}`;
    window.history[replace ? "replaceState" : "pushState"]({}, "", url);
  }

  function matches(work, state) {
    if (state.q && !normalize(work.search).includes(normalize(state.q))) return false;
    if (state.author && !work.authors.some((author) => author.id === state.author)) return false;
    if (state.era && !work.eras.includes(state.era)) return false;
    if (state.difficulty === "unscored" && work.difficulty !== null) return false;
    if (state.difficulty === "approachable" && !(work.difficulty !== null && work.difficulty < 40)) return false;
    if (state.difficulty === "intermediate" && !(work.difficulty >= 40 && work.difficulty < 70)) return false;
    if (state.difficulty === "advanced" && !(work.difficulty >= 70)) return false;
    if (state.length === "short" && work.length >= 5000) return false;
    if (state.length === "medium" && !(work.length >= 5000 && work.length < 20000)) return false;
    if (state.length === "long" && work.length < 20000) return false;
    if (state.metadata === "scored" && work.difficulty === null) return false;
    if (state.metadata === "illustrated" && !work.illustrations) return false;
    if (state.metadata === "old-orthography" && !work.orthography.includes("旧")) return false;
    return true;
  }

  function sortWorks(items, order) {
    const collator = new Intl.Collator("ja", { numeric: true, sensitivity: "base" });
    const sorted = [...items];
    const difficulty = (work) => work.difficulty === null ? Number.POSITIVE_INFINITY : work.difficulty;
    sorted.sort((a, b) => {
      if (order === "author") return collator.compare(a.authors[0]?.name || "", b.authors[0]?.name || "") || collator.compare(a.title, b.title);
      if (order === "length-asc") return a.length - b.length;
      if (order === "length-desc") return b.length - a.length;
      if (order.startsWith("difficulty")) {
        if (a.difficulty === null && b.difficulty === null) return collator.compare(a.title, b.title);
        if (a.difficulty === null) return 1;
        if (b.difficulty === null) return -1;
        return order === "difficulty-asc" ? difficulty(a) - difficulty(b) : difficulty(b) - difficulty(a);
      }
      return collator.compare(a.reading || a.title, b.reading || b.title);
    });
    return sorted;
  }

  function textElement(tag, className, value) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = value;
    return element;
  }

  function renderCard(work) {
    const card = document.createElement("article");
    card.className = "work-card";
    card.dataset.workId = work.id;
    const cover = textElement("div", "book-cover book-cover--empty", work.title);
    cover.setAttribute("role", "img");
    cover.setAttribute("aria-label", `No cover available for ${work.title}`);
    const copy = document.createElement("div");
    copy.className = "work-card-copy";
    copy.append(textElement("p", "eyebrow", `${work.length.toLocaleString("en-US")} words`));
    const title = document.createElement("h3");
    title.lang = "ja";
    const titleLink = textElement("a", "", work.title);
    titleLink.href = `works/${work.slug}/index.html`;
    title.append(titleLink);
    copy.append(title);
    if (work.reading) {
      const reading = textElement("p", "reading", work.reading);
      reading.lang = "ja";
      copy.append(reading);
    }
    copy.append(textElement("p", "author", work.authors.map((author) => author.name).join(", ")));
    const metadata = document.createElement("p");
    metadata.className = "work-metadata";
    metadata.append(textElement("span", "", work.orthography));
    metadata.append(textElement("span", "", work.eras.join(" / ")));
    if (work.illustrations) metadata.append(textElement("span", "", "Illustrated"));
    copy.append(metadata);
    const score = document.createElement("p");
    score.className = work.difficulty === null ? "difficulty difficulty--unscored" : "difficulty";
    score.append(textElement("span", "", "Difficulty"));
    score.append(textElement("strong", "", work.difficulty === null ? "Review" : Math.round(work.difficulty).toString()));
    copy.append(score);
    card.append(cover, copy);
    return card;
  }

  function render(state, replaceUrl = false) {
    const filtered = sortWorks(works.filter((work) => matches(work, state)), state.sort);
    const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
    if (state.page > pageCount) state.page = pageCount;
    writeState(state, replaceUrl || invalidParameters.length > 0);
    syncForm(state);
    const start = (state.page - 1) * pageSize;
    const pageWorks = filtered.slice(start, start + pageSize);
    grid.replaceChildren(...pageWorks.map(renderCard));
    empty.hidden = filtered.length !== 0;
    pagination.hidden = filtered.length === 0 || pageCount === 1;
    previous.disabled = state.page === 1;
    next.disabled = state.page === pageCount;
    summary.textContent = `Page ${state.page} of ${pageCount}`;
    const range = filtered.length ? `${start + 1}–${Math.min(start + pageSize, filtered.length)} of ` : "";
    status.textContent = `${invalidParameters.length ? "Ignored invalid filters. " : ""}Showing ${range}${filtered.length} works.`;
    const labels = [];
    if (state.q) labels.push(`Search: “${state.q}”`);
    for (const name of ["difficulty", "length", "author", "era", "metadata"]) {
      if (state[name]) labels.push(field(name).selectedOptions[0].textContent);
    }
    activeFilters.textContent = labels.length ? `Active filters: ${labels.join(" · ")}` : "No filters applied.";
    invalidParameters = [];
  }

  function stateFromForm() {
    invalidParameters = [];
    return {
      q: field("q").value.trim(), difficulty: field("difficulty").value, length: field("length").value,
      author: field("author").value, era: field("era").value, metadata: field("metadata").value,
      sort: field("sort").value, page: 1
    };
  }

  form.addEventListener("submit", (event) => { event.preventDefault(); render(stateFromForm()); });
  form.addEventListener("change", () => render(stateFromForm()));
  let searchTimer;
  field("q").addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => render(stateFromForm(), true), 180);
  });
  document.querySelectorAll("[data-clear-filters]").forEach((button) => button.addEventListener("click", () => {
    form.reset();
    render({ q: "", difficulty: "", length: "", author: "", era: "", metadata: "", sort: "title", page: 1 });
    field("q").focus();
  }));
  previous.addEventListener("click", () => { const state = readState(); state.page -= 1; render(state); grid.scrollIntoView({ behavior: "smooth" }); });
  next.addEventListener("click", () => { const state = readState(); state.page += 1; render(state); grid.scrollIntoView({ behavior: "smooth" }); });
  window.addEventListener("popstate", () => render(readState(), true));

  fetch(grid.dataset.libraryUrl)
    .then((response) => { if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.json(); })
    .then((data) => { works = data.works; render(readState(), true); })
    .catch(() => { status.textContent = "The complete catalog could not be loaded. Showing the selected preview."; });
})();

(() => {
  const reader = document.querySelector("[data-reader]");
  const content = document.querySelector("[data-reader-content]");
  if (!reader || !content) return;

  const progress = document.querySelector("[data-reading-progress]");
  const resume = document.querySelector("[data-reader-resume]");
  const positionKey = `blue-sora-position:${reader.dataset.workId}`;
  const sizeKey = "blue-sora-reader-size";
  const sizes = ["small", "default", "large", "x-large"];
  let framePending = false;

  function storageGet(key) {
    try { return window.localStorage.getItem(key); } catch (_) { return null; }
  }

  function storageSet(key, value) {
    try { window.localStorage.setItem(key, value); } catch (_) { /* Reading remains usable without storage. */ }
  }

  function applySize(size) {
    const safeSize = sizes.includes(size) ? size : "default";
    content.dataset.textSize = safeSize;
    storageSet(sizeKey, safeSize);
  }

  function currentSizeIndex() {
    return Math.max(0, sizes.indexOf(content.dataset.textSize || "default"));
  }

  document.querySelector("[data-font-decrease]")?.addEventListener("click", () => {
    applySize(sizes[Math.max(0, currentSizeIndex() - 1)]);
  });
  document.querySelector("[data-font-increase]")?.addEventListener("click", () => {
    applySize(sizes[Math.min(sizes.length - 1, currentSizeIndex() + 1)]);
  });
  document.querySelector("[data-font-reset]")?.addEventListener("click", () => applySize("default"));
  applySize(storageGet(sizeKey) || "default");

  function updatePosition() {
    framePending = false;
    const maximum = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
    const ratio = Math.min(1, Math.max(0, window.scrollY / maximum));
    const percent = Math.round(ratio * 100);
    progress.style.setProperty("--reading-progress", `${percent}%`);
    progress.setAttribute("aria-valuenow", String(percent));
    storageSet(positionKey, JSON.stringify({ ratio }));
  }

  window.addEventListener("scroll", () => {
    if (!framePending) {
      framePending = true;
      window.requestAnimationFrame(updatePosition);
    }
  }, { passive: true });

  window.requestAnimationFrame(() => {
    if (!window.location.hash) {
      try {
        const saved = JSON.parse(storageGet(positionKey) || "null");
        if (saved && Number.isFinite(saved.ratio) && saved.ratio > .02 && saved.ratio < 1) {
          const maximum = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
          window.scrollTo({ top: maximum * saved.ratio, behavior: "instant" });
          resume.textContent = `Restored your reading position at ${Math.round(saved.ratio * 100)}%.`;
        }
      } catch (_) { /* Ignore malformed local state. */ }
    }
    updatePosition();
  });
})();
