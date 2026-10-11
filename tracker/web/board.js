"use strict";

const REFRESH_MS = 15000;

const state = {
  project: "",
  tag: "",
  statuses: [],
  projects: [],
  tasks: [],
  dragging: null,
  current: null,
  loads: 0,
  moving: 0,
  tab: "view",
  previews: 0,
};

const $ = (id) => document.getElementById(id);

// Элемент DOM из свойств и потомков; строки становятся текстовыми узлами, разметка из них не исполняется.
function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node[key] = value;
  }
  node.append(...children);
  return node;
}

function describe(data, response) {
  const detail = data && data.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg).join("; ");
  return `${response.status} ${response.statusText}`;
}

async function api(method, path, body) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(describe(data, response));
  return data;
}

function query(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value) search.set(key, value);
  const text = search.toString();
  return text ? `?${text}` : "";
}

function showError(message, target = $("error")) {
  target.textContent = message || "";
  target.hidden = !message;
}

function stamp() {
  $("status-line").textContent = `обновлено ${new Date().toLocaleTimeString("ru-RU")}`;
}

function parseTags(text) {
  return text.split(",").map((tag) => tag.trim()).filter(Boolean);
}

// Переводы строк тела к \n, как их отдаёт textarea.
function lf(text) {
  return text.replace(/\r\n/g, "\n");
}

function sameTags(a, b) {
  return a.length === b.length && a.every((tag, i) => tag === b[i]);
}

function fillSelect(select, first, items, current) {
  const values = items.map((item) => item.value);
  const options = items.map((item) => el("option", { value: item.value }, item.text));
  // Выбранное значение, которого нет в списке, остаётся видимым с нулём задач.
  if (current && !values.includes(current)) options.push(el("option", { value: current }, `${current} (0)`));
  select.replaceChildren(el("option", { value: "" }, first), ...options);
  select.value = current;
}

async function loadFilters() {
  const [projects, tags] = await Promise.all([
    api("GET", "/api/projects"),
    api("GET", `/api/tags${query({ project: state.project })}`),
  ]);
  state.projects = projects.map((p) => p.project);
  const total = projects.reduce((sum, p) => sum + p.tasks, 0);
  fillSelect(
    $("project-filter"),
    `Все проекты (${total})`,
    projects.map((p) => ({ value: p.project, text: `${p.project} (${p.tasks})` })),
    state.project,
  );
  fillSelect(
    $("tag-filter"),
    "Все метки",
    tags.map((t) => ({ value: t.tag, text: `${t.tag} (${t.tasks})` })),
    state.tag,
  );
  $("hint").hidden = total > 0;
}

async function loadTasks() {
  const ticket = ++state.loads;
  const filter = `${state.project}|${state.tag}`;
  const tasks = await api("GET", `/api/tasks${query({ project: state.project, tag: state.tag })}`);
  // Ответ чтения, начатого до переноса или смены фильтра, отбрасывается.
  if (ticket !== state.loads || filter !== `${state.project}|${state.tag}`) return;
  state.tasks = tasks;
  render();
  stamp();
}

async function reload() {
  await Promise.all([loadTasks(), loadFilters()]);
}

function pageUrl(params) {
  return `/${query(params)}`;
}

// Адрес страницы отражает фильтры и открытую задачу: его можно сохранить или переслать.
function syncUrl() {
  const task = $("card-dialog").open && state.current ? state.current.id : "";
  history.replaceState(null, "", pageUrl({ p: state.project, t: state.tag, task }));
}

async function setFilter(project, tag) {
  state.project = project;
  state.tag = tag;
  syncUrl();
  document.title = project ? `${project} - трекер задач` : "Трекер задач";
  try {
    await reload();
    showError("");
  } catch (error) {
    showError(error.message);
  }
}

function cardOf(task) {
  const labels = [];
  if (!state.project && task.project) labels.push(el("span", { class: "project-chip" }, task.project));
  for (const tag of task.tags) {
    labels.push(
      el(
        "button",
        {
          type: "button",
          class: tag === state.tag ? "tag current" : "tag",
          title: `Только задачи с меткой «${tag}»`,
          onclick: (event) => {
            event.stopPropagation();
            setFilter(state.project, tag === state.tag ? "" : tag);
          },
        },
        tag,
      ),
    );
  }
  const meta = task.author === "human" ? `#${task.id}` : `#${task.id} - ${task.author}`;
  return el(
    "article",
    {
      class: "card",
      draggable: true,
      dataset: { id: task.id },
      title: "Открыть задачу",
      onclick: () => openTask(task.id),
      ondragstart: (event) => {
        state.dragging = task.id;
        event.dataTransfer.setData("text/plain", task.id);
        event.dataTransfer.effectAllowed = "move";
        event.currentTarget.classList.add("dragging");
      },
      ondragend: (event) => {
        state.dragging = null;
        event.currentTarget.classList.remove("dragging");
        document.querySelectorAll(".column.over").forEach((c) => c.classList.remove("over"));
      },
    },
    el("div", { class: "meta" }, meta),
    el("div", { class: "title" }, task.title),
    ...(labels.length ? [el("div", { class: "tags" }, ...labels)] : []),
  );
}

function columnOf(status, tasks) {
  const column = el(
    "section",
    {
      class: "column",
      dataset: { status: status.status },
      ondragover: (event) => {
        if (!state.dragging) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
        column.classList.add("over");
      },
      ondragleave: (event) => {
        if (!column.contains(event.relatedTarget)) column.classList.remove("over");
      },
      ondrop: (event) => {
        event.preventDefault();
        column.classList.remove("over");
        const id = state.dragging || event.dataTransfer.getData("text/plain");
        // Снять признак перетаскивания до перерисовки, которая удаляет карточку вместе с её dragend.
        state.dragging = null;
        if (id) moveTask(id, status.status);
      },
    },
    el(
      "div",
      { class: "column-head" },
      el("h2", {}, status.label),
      el("span", { class: "count" }, String(tasks.length)),
      el("button", {
        type: "button",
        class: "add",
        title: `Новая задача в «${status.label}»`,
        textContent: "+",
        onclick: () => openNew(status.status),
      }),
    ),
    el("div", { class: "cards" }, ...tasks.map(cardOf)),
  );
  return column;
}

function render() {
  const board = $("board");
  board.style.setProperty("--columns", state.statuses.length);
  board.replaceChildren(
    ...state.statuses.map((status) =>
      columnOf(status, state.tasks.filter((task) => task.status === status.status)),
    ),
  );
}

async function moveTask(id, status) {
  const task = state.tasks.find((t) => t.id === id);
  if (!task || task.status === status) return;
  const previous = task.status;
  task.status = status;
  state.loads++;
  state.moving++;
  render();
  try {
    const saved = await api("POST", `/api/tasks/${encodeURIComponent(id)}/move`, { status });
    Object.assign(task, { status: saved.status, updated: saved.updated });
    showError("");
    stamp();
  } catch (error) {
    task.status = previous;
    render();
    showError(`#${id} не перенесена: ${error.message}`);
  } finally {
    state.moving--;
  }
}

function fillStatuses(select) {
  select.replaceChildren(
    ...state.statuses.map((s) => el("option", { value: s.status }, s.label)),
  );
}

async function renderPreview() {
  const view = $("tab-view");
  const text = $("card-form").elements.body.value;
  const ticket = ++state.previews;
  if (!text.trim()) {
    view.classList.add("empty");
    view.textContent = "Текста нет: его пишут на вкладке «Правка».";
    return;
  }
  try {
    const { html } = await api("POST", "/api/markdown", { text });
    if (ticket !== state.previews) return;
    view.classList.remove("empty");
    // Html собран сервером с экранированием сырого html из текста (tracker/board.py).
    view.innerHTML = html;
    view.querySelectorAll("a[href]").forEach((a) => {
      a.target = "_blank";
      a.rel = "noopener";
    });
  } catch (error) {
    showError(error.message, $("card-error"));
  }
}

function showTab(name) {
  state.tab = name;
  document.querySelectorAll(".tabs [data-tab]").forEach((button) => {
    const on = button.dataset.tab === name;
    button.classList.toggle("current", on);
    button.setAttribute("aria-selected", String(on));
  });
  $("tab-view").hidden = name !== "view";
  $("tab-edit").hidden = name !== "edit";
  if (name === "view") renderPreview();
}

// Значение пункта «Новый проект»: подчёркивания в имени проекта не бывает.
const NEW_PROJECT = "__new__";

function fillProjectField(current) {
  const select = $("card-form").elements.project;
  const names = [...state.projects];
  if (current && !names.includes(current)) names.push(current);
  select.replaceChildren(
    el("option", { value: "", disabled: true }, "выберите проект"),
    ...names.map((name) => el("option", { value: name }, name)),
    el("option", { value: NEW_PROJECT }, "Новый проект…"),
  );
  select.value = current || (names.length ? "" : NEW_PROJECT);
  showNewProject();
}

function showNewProject() {
  const form = $("card-form");
  const fresh = form.elements.project.value === NEW_PROJECT;
  form.elements.new_project.hidden = !fresh;
  form.elements.new_project.required = fresh;
  if (!fresh) form.elements.new_project.value = "";
}

function readProject() {
  const form = $("card-form");
  const value = form.elements.project.value;
  return value === NEW_PROJECT ? form.elements.new_project.value.trim() : value;
}

// Запись в буфер: clipboard API есть только на https и localhost, иначе - через выделенный текст.
async function toClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const area = el("textarea", { value: text, readOnly: true });
  area.style.position = "fixed";
  area.style.opacity = "0";
  $("card-dialog").append(area);
  area.select();
  const copied = document.execCommand("copy");
  area.remove();
  if (!copied) throw new Error("браузер не дал записать в буфер");
}

async function copyLink() {
  const button = $("copy-link");
  if (!state.current) return;
  const url = `${location.origin}${pageUrl({ task: state.current.id })}`;
  try {
    await toClipboard(url);
    button.textContent = "Скопировано";
    button.classList.add("done");
    showError("", $("card-error"));
  } catch (error) {
    showError(`${error.message}: ${url}`, $("card-error"));
  }
  setTimeout(() => {
    button.textContent = "Ссылка";
    button.classList.remove("done");
  }, 1500);
}

function openNew(status) {
  state.current = null;
  const form = $("card-form");
  form.reset();
  form.elements.status.value = status;
  fillProjectField(state.project);
  form.elements.tags.value = state.tag;
  $("copy-link").hidden = true;
  $("card-dialog").dataset.status = status;
  $("card-id").textContent = "Новая задача";
  $("card-meta").textContent = "";
  $("comment-form").hidden = true;
  showError("", $("card-error"));
  showTab("edit");
  $("card-dialog").showModal();
  syncUrl();
  form.elements.title.focus();
}

function fillTask(task) {
  state.current = task;
  const form = $("card-form");
  form.elements.title.value = task.title;
  form.elements.id.value = task.id;
  fillProjectField(task.project);
  $("copy-link").hidden = false;
  form.elements.status.value = task.status;
  $("card-dialog").dataset.status = task.status;
  form.elements.tags.value = task.tags.join(", ");
  form.elements.body.value = task.body;
  $("card-id").textContent = `#${task.id}`;
  const author = `автор ${task.author}`;
  $("card-meta").textContent = `${author} · создана ${task.created} · изменена ${task.updated}`;
}

async function openTask(id) {
  let task;
  try {
    task = await api("GET", `/api/tasks/${encodeURIComponent(id)}`);
  } catch (error) {
    showError(error.message);
    return;
  }
  $("comment-form").reset();
  $("comment-form").hidden = false;
  showError("", $("card-error"));
  fillTask(task);
  showTab("view");
  $("card-dialog").showModal();
  // Фокус на само окно, а не на первую кнопку в нём: иначе после загрузки страницы у неё рамка фокуса.
  $("card-dialog").focus();
  syncUrl();
}

async function saveTask(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const title = form.elements.title.value.trim();
  const taskId = form.elements.id.value.trim().replace(/^#/, "");
  const project = readProject();
  const status = form.elements.status.value;
  const tags = parseTags(form.elements.tags.value);
  const body = form.elements.body.value;
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  try {
    if (!state.current) {
      await api("POST", "/api/tasks", { id: taskId || null, project, title, body, status, tags });
    } else {
      const task = state.current;
      const patch = {};
      if (taskId && taskId !== task.id) patch.id = taskId;
      if (title !== task.title) patch.title = title;
      if (project !== task.project) patch.project = project;
      if (body !== lf(task.body)) patch.body = body;
      if (!sameTags(tags, task.tags)) patch.tags = tags;
      let id = encodeURIComponent(task.id);
      if (Object.keys(patch).length) {
        const saved = await api("PATCH", `/api/tasks/${id}`, patch);
        state.current = saved;
        id = encodeURIComponent(saved.id);
      }
      if (status !== task.status) await api("POST", `/api/tasks/${id}/move`, { status });
    }
    $("card-dialog").close();
    await reload();
  } catch (error) {
    showError(error.message, $("card-error"));
  } finally {
    button.disabled = false;
  }
}

async function addComment(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const text = form.elements.text.value.trim();
  const task = state.current;
  if (!text || !task) return;
  if ($("card-form").elements.body.value !== lf(task.body)) {
    showError("Текст задачи изменён и не сохранён: сохраните его до комментария.", $("card-error"));
    return;
  }
  try {
    const saved = await api("POST", `/api/tasks/${encodeURIComponent(task.id)}/comments`, { text });
    form.reset();
    showError("", $("card-error"));
    fillTask(saved);
    if (state.tab === "view") renderPreview();
    await loadTasks();
  } catch (error) {
    showError(error.message, $("card-error"));
  }
}

async function refresh() {
  if (document.hidden || state.dragging || state.moving) return;
  if ($("card-dialog").open) return;
  try {
    await reload();
  } catch (error) {
    showError(error.message);
  }
}

async function projectOf(id) {
  try {
    return (await api("GET", `/api/tasks/${encodeURIComponent(id)}`)).project;
  } catch {
    return "";
  }
}

async function start() {
  $("project-filter").addEventListener("change", (event) => setFilter(event.target.value, ""));
  $("tag-filter").addEventListener("change", (event) => setFilter(state.project, event.target.value));
  $("card-form").addEventListener("submit", saveTask);
  $("card-form").elements.status.addEventListener("change", (event) => {
    $("card-dialog").dataset.status = event.target.value;
  });
  $("card-form").elements.project.addEventListener("change", () => {
    showNewProject();
    if (!$("card-form").elements.new_project.hidden) $("card-form").elements.new_project.focus();
  });
  $("copy-link").addEventListener("click", copyLink);
  $("card-dialog").addEventListener("close", syncUrl);
  $("comment-form").addEventListener("submit", addComment);
  document.querySelectorAll(".tabs [data-tab]").forEach((button) =>
    button.addEventListener("click", () => showTab(button.dataset.tab)),
  );
  document.querySelectorAll("[data-close]").forEach((button) =>
    button.addEventListener("click", () => $("card-dialog").close()),
  );
  document.addEventListener("visibilitychange", refresh);
  setInterval(refresh, REFRESH_MS);

  try {
    state.statuses = await api("GET", "/api/statuses");
    fillStatuses($("card-form").elements.status);
    const params = new URLSearchParams(location.search);
    const linked = params.get("task");
    // Ссылка на задачу открывает доску её проекта: проект берётся из задачи, а не из ссылки.
    const project = params.get("p") || (linked ? await projectOf(linked) : "");
    await setFilter(project, params.get("t") || "");
    if (linked) await openTask(linked);
  } catch (error) {
    showError(error.message);
  }
}

start();
