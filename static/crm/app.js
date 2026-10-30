let lastDrawerOpener = null;
let focusAfterCardSwap = null;

function closeNavigation() {
  const wasOpen = document.body.classList.contains("nav-open");
  document.body.classList.remove("nav-open");
  document.querySelector("[data-nav-toggle]")?.setAttribute("aria-expanded", "false");
  if (wasOpen) document.querySelector("[data-nav-toggle]")?.focus({preventScroll: true});
}

function focusables(container) {
  return [...container.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex="0"]')]
    .filter((item) => item.getClientRects().length > 0);
}

function restoreCardFocus(target) {
  if (!focusAfterCardSwap || !target) return;
  const saved = focusAfterCardSwap;
  focusAfterCardSwap = null;
  const selector = saved.id ? `#${CSS.escape(saved.id)}` : `[name="${CSS.escape(saved.name || "")}"]`;
  const next = target.querySelector(selector);
  if (next) {
    if (saved.value && next instanceof HTMLSelectElement) next.value = saved.value;
    next.focus({preventScroll: true});
  }
}

function listUrlWithoutCard() {
  const url = new URL(window.location.href);
  url.searchParams.delete("selected");
  return `${url.pathname}${url.search}`;
}

document.addEventListener("click", async (event) => {
  const copyButton = event.target.closest("[data-copy]");
  if (copyButton) {
    try {
      await navigator.clipboard.writeText(copyButton.dataset.copy);
      const label = copyButton.textContent;
      copyButton.textContent = "Скопировано";
      window.setTimeout(() => { copyButton.textContent = label; }, 1300);
    } catch {
      copyButton.textContent = "Не удалось скопировать";
    }
    return;
  }

  const navToggle = event.target.closest("[data-nav-toggle]");
  if (navToggle) {
    const open = document.body.classList.toggle("nav-open");
    navToggle.setAttribute("aria-expanded", String(open));
    if (open) document.querySelector("#sidebar .nav-item")?.focus({preventScroll: true});
    return;
  }
  if (document.body.classList.contains("nav-open") && event.target === document.body) {
    closeNavigation();
    return;
  }

  if (event.target.matches("[data-drawer-backdrop]")) {
    document.querySelector("[data-close-drawer]")?.click();
  }
});

document.addEventListener("keydown", (event) => {
  const panel = document.querySelector("#drawer-panel");
  if (!panel) {
    if (event.key === "Escape") closeNavigation();
    return;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    document.querySelector("[data-close-drawer]")?.click();
    return;
  }
  if (event.key !== "Tab") return;
  const items = focusables(panel);
  if (!items.length) {
    event.preventDefault();
    panel.focus();
    return;
  }
  const first = items[0];
  const last = items[items.length - 1];
  if (event.shiftKey && (document.activeElement === first || !panel.contains(document.activeElement))) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && (document.activeElement === last || !panel.contains(document.activeElement))) {
    event.preventDefault();
    first.focus();
  }
});

document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;
  const submit = form.querySelector("button[type=submit]");
  if (submit) {
    submit.dataset.label ||= submit.textContent;
    submit.disabled = true;
    submit.textContent = "Сохраняем…";
  }
  if (form.matches(".form-stack")) form.dataset.dirty = "false";
}, true);

document.addEventListener("input", (event) => {
  const form = event.target.closest(".form-stack");
  if (form) form.dataset.dirty = "true";
});
document.addEventListener("change", (event) => {
  const form = event.target.closest(".form-stack");
  if (form) form.dataset.dirty = "true";
});
window.addEventListener("beforeunload", (event) => {
  if (document.querySelector('.form-stack[data-dirty="true"]')) {
    event.preventDefault();
    event.returnValue = "";
  }
});

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("details[data-persist-disclosure]").forEach((disclosure) => {
    const key = `potok:sidebar:${disclosure.dataset.persistDisclosure}`;
    try {
      const saved = window.localStorage.getItem(key);
      if (saved !== null) disclosure.open = saved === "open";
      disclosure.addEventListener("toggle", () => {
        try { window.localStorage.setItem(key, disclosure.open ? "open" : "closed"); } catch { /* Storage may be disabled; native disclosure still works. */ }
      });
    } catch { /* Native details controls work even when storage is disabled. */ }
  });
  const drawer = document.querySelector("#drawer-panel");
  if (drawer) {
    document.body.classList.add("drawer-open");
    window.setTimeout(() => document.querySelector("[data-close-drawer]")?.focus({preventScroll: true}), 0);
  }
  const filterForm = document.querySelector("#filters-form");
  const inbox = document.querySelector("#inbox-content");
  if (!window.htmx && filterForm) {
    const search = filterForm.querySelector("input[name=q]");
    let timer;
    search?.addEventListener("input", () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => filterForm.requestSubmit(), 350);
    });
    filterForm.querySelectorAll("select").forEach((select) => select.addEventListener("change", () => filterForm.requestSubmit()));
  }
  if (!window.htmx && inbox) {
    window.setInterval(async () => {
      if (document.visibilityState !== "visible" || document.querySelector(".drawer-backdrop") || document.querySelector(".tag-more[open]")) return;
      if (inbox.contains(document.activeElement) || document.querySelector(".form-stack[data-dirty='true']")) return;
      try {
        const response = await fetch(listUrlWithoutCard(), {headers: {"HX-Request": "true", "HX-Target": "inbox-content"}, credentials: "same-origin"});
        if (!response.ok) return;
        inbox.innerHTML = await response.text();
      } catch { /* Keep the last confirmed list visible if the connection is unavailable. */ }
    }, 3000);
  }
});

document.addEventListener("htmx:beforeRequest", (event) => {
  const target = event.detail.target;
  if (target?.id === "drawer-host") {
    const opener = event.detail.elt?.closest?.("a.client-link");
    if (opener) lastDrawerOpener = opener;
  }
  if (target?.id === "drawer-panel-content") {
    const active = document.activeElement;
    focusAfterCardSwap = active && target.contains(active) ? {id: active.id, name: active.getAttribute("name"), value: active.value || ""} : null;
  }
  const statusForm = event.detail.elt?.closest?.("[data-status-form]");
  if (statusForm) {
    const select = statusForm.querySelector("select");
    const feedback = statusForm.querySelector(".status-feedback");
    if (select) select.disabled = true;
    if (feedback) feedback.textContent = "Сохраняем…";
  }
  const boardForm = event.detail.elt?.closest?.(".kanban-stage-form");
  if (boardForm) {
    const select = boardForm.querySelector("select");
    if (select) select.disabled = true;
  }
});

document.addEventListener("htmx:afterRequest", (event) => {
  const form = event.detail.elt?.closest?.("form") || (event.detail.elt instanceof HTMLFormElement ? event.detail.elt : null);
  const submit = form?.querySelector("button[type=submit]");
  if (submit) {
    submit.disabled = false;
    submit.textContent = submit.dataset.label || submit.textContent;
  }
  const statusForm = form?.matches("[data-status-form]") ? form : null;
  if (statusForm) {
    const select = statusForm.querySelector("select");
    const feedback = statusForm.querySelector(".status-feedback");
    if (select) {
      select.disabled = false;
      if (!event.detail.successful) select.value = select.dataset.savedStatus;
    }
    if (feedback && !event.detail.successful) feedback.textContent = "Не удалось сохранить. Повторите попытку.";
  }
  const boardForm = form?.matches(".kanban-stage-form") ? form : null;
  if (boardForm) {
    const select = boardForm.querySelector("select");
    if (select) {
      select.disabled = false;
      if (!event.detail.successful) select.value = select.dataset.savedStatus;
    }
  }
});

document.addEventListener("htmx:afterSwap", (event) => {
  const target = event.detail.target;
  if (target?.id === "drawer-host") {
    const panel = target.querySelector("#drawer-panel");
    if (panel) {
      document.body.classList.add("drawer-open");
      window.setTimeout(() => document.querySelector("[data-close-drawer]")?.focus({preventScroll: true}), 0);
    } else {
      document.body.classList.remove("drawer-open");
      if (lastDrawerOpener?.isConnected) lastDrawerOpener.focus({preventScroll: true});
      else document.querySelector("#inbox-heading")?.focus({preventScroll: true});
      lastDrawerOpener = null;
    }
  }
  if (target?.id === "drawer-panel-content") restoreCardFocus(target);
  if (target?.id === "inbox-content") {
    const inbox = document.querySelector("#inbox-content");
    if (inbox) inbox.setAttribute("hx-get", listUrlWithoutCard());
  }
});

document.addEventListener("htmx:afterSettle", () => {
  const inbox = document.querySelector("#inbox-content");
  if (inbox && !document.querySelector(".drawer-backdrop")) inbox.setAttribute("hx-get", listUrlWithoutCard());
});

document.addEventListener("htmx:responseError", (event) => {
  const form = event.detail.elt?.closest?.("form");
  const statusForm = form?.matches("[data-status-form]") ? form : null;
  const select = statusForm?.querySelector("select");
  const feedback = statusForm?.querySelector(".status-feedback");
  if (select) {
    select.disabled = false;
    select.value = select.dataset.savedStatus;
  }
  if (feedback) feedback.textContent = "Не удалось сохранить. Повторите попытку.";
});

document.addEventListener("dragstart", (event) => {
  const card = event.target.closest?.("[data-kanban-card]");
  if (!card) return;
  card.classList.add("dragging");
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", "lead-card");
  }
});

document.addEventListener("dragend", (event) => {
  event.target.closest?.("[data-kanban-card]")?.classList.remove("dragging");
  document.querySelectorAll(".kanban-column.drag-over").forEach((column) => column.classList.remove("drag-over"));
});

document.addEventListener("dragover", (event) => {
  const column = event.target.closest?.("[data-kanban-column]");
  if (!column) return;
  event.preventDefault();
  event.dataTransfer && (event.dataTransfer.dropEffect = "move");
  column.classList.add("drag-over");
});

document.addEventListener("dragleave", (event) => {
  const column = event.target.closest?.("[data-kanban-column]");
  if (column && !column.contains(event.relatedTarget)) column.classList.remove("drag-over");
});

document.addEventListener("drop", (event) => {
  const column = event.target.closest?.("[data-kanban-column]");
  const card = document.querySelector("[data-kanban-card].dragging");
  if (!column || !card) return;
  event.preventDefault();
  const status = card.querySelector("select[name=status]");
  if (!status || status.value === column.dataset.status) return;
  status.value = column.dataset.status;
  status.dispatchEvent(new Event("change", {bubbles: true}));
});
