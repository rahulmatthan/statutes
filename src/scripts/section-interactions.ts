// Client-side behaviour for a section page:
// - Click an `.amend` indicator → its details fill the right amendment panel.
// - Click the panel's × (or press Esc) → panel returns to its empty hint.
// - Click a version pill → switch the body to that historical version.

interface AmendData {
  id: string;
  kind: string;
  date: string;
  by: string;
  byText?: string;
  byHref: string;
  target?: string;
  note?: string;
  before?: string;
  after?: string;
}

const KIND_LABEL: Record<string, string> = {
  inserted: "Inserted",
  substituted: "Substituted",
  omitted: "Omitted",
  renumbered: "Renumbered",
  amended: "Amended",
  enacted: "Enacted",
};

// Astro's deploy base ("/" in dev, e.g. "/statutes" on the production
// subpath). Vite inlines `import.meta.env.BASE_URL` at build time.
const BASE = (import.meta.env.BASE_URL ?? "/").replace(/\/$/, "");

const AMEND_LINKS: Record<string, string> = {
  "2019-amendment-act": `${BASE}/amendments/2019-amendment-act`,
  "2019-ordinance": `${BASE}/amendments/2019-ordinance`,
  "2019-jk-reorganisation":
    "https://www.indiacode.nic.in/handle/123456789/2030?view_type=browse",
  "2023-jan-vishwas":
    "https://www.indiacode.nic.in/handle/123456789/19972?view_type=browse",
  original: "#",
  unknown: "#",
};

// Regulation- and rule-amendment refs look like `<parent>/<date>` and resolve
// to per-instrument pages we generate at /regulations/<parent>/a/<date> (and
// /rules/<parent>/a/<date>). Pick the right prefix based on the URL we're on.
function resolveAmendLink(by: string): string {
  if (AMEND_LINKS[by]) return AMEND_LINKS[by];
  if (!by.includes("/")) return "#";
  const onRules = window.location.pathname.startsWith(`${BASE}/rules/`);
  const prefix = onRules ? `${BASE}/rules` : `${BASE}/regulations`;
  return `${prefix}/${by.replace("/", "/a/")}`;
}

function readAmend(el: HTMLElement): AmendData {
  const ds = el.dataset;
  return {
    id: ds.id ?? "",
    kind: ds.kind ?? "amended",
    date: ds.date ?? "",
    by: ds.by ?? "unknown",
    byText: ds.byText ?? "",
    byHref: resolveAmendLink(ds.by ?? "unknown"),
    target: ds.target ?? "",
    note: ds.note ?? "",
    before: ds.before ?? "",
    after: el.textContent ?? "",
  };
}

function setupAmendPanel() {
  const panel = document.querySelector(".amend-panel") as HTMLElement | null;
  if (!panel) return;

  const kindEl = panel.querySelector(".amend-panel-kind") as HTMLElement;
  const dateEl = panel.querySelector(".amend-panel-date") as HTMLElement;
  const byEl = panel.querySelector(".amend-panel-by") as HTMLElement;
  const targetEl = panel.querySelector(".amend-panel-target") as HTMLElement;
  const beforeWrap = panel.querySelector(
    ".amend-panel-before-block",
  ) as HTMLElement;
  const beforeText = panel.querySelector(
    ".amend-panel-before",
  ) as HTMLElement;
  const afterWrap = panel.querySelector(
    ".amend-panel-after-block",
  ) as HTMLElement;
  const afterText = panel.querySelector(".amend-panel-after") as HTMLElement;
  const noteEl = panel.querySelector(".amend-panel-note") as HTMLElement;
  const linkEl = panel.querySelector(
    ".amend-panel-link",
  ) as HTMLAnchorElement;
  const closeBtn = panel.querySelector(
    ".amend-panel-close",
  ) as HTMLButtonElement;

  function clear() {
    panel!.dataset.state = "empty";
    document
      .querySelectorAll(".amend.is-active")
      .forEach((n) => n.classList.remove("is-active"));
  }

  function showAmend(target: HTMLElement) {
    const d = readAmend(target);

    kindEl.textContent = KIND_LABEL[d.kind] ?? "Amended";
    kindEl.dataset.kind = d.kind;
    dateEl.textContent = d.date;
    dateEl.setAttribute("datetime", d.date);

    byEl.textContent = d.byText
      ? `By ${d.byText}`
      : d.by !== "unknown"
        ? `By ${d.by}`
        : "";

    if (d.target) {
      targetEl.hidden = false;
      targetEl.textContent = `Target: ${d.target}`;
    } else {
      targetEl.hidden = true;
    }

    if (d.kind === "substituted" && d.before) {
      beforeWrap.hidden = false;
      beforeText.textContent = d.before;
      afterWrap.hidden = false;
      afterText.textContent = d.after;
    } else if (d.kind === "inserted") {
      beforeWrap.hidden = false;
      beforeText.innerHTML =
        "<em>(this text did not exist before the amendment)</em>";
      afterWrap.hidden = false;
      afterText.textContent = d.after;
    } else if (d.kind === "omitted") {
      beforeWrap.hidden = false;
      beforeText.textContent = d.before || d.after;
      afterWrap.hidden = false;
      afterText.innerHTML = "<em>(omitted)</em>";
    } else {
      beforeWrap.hidden = !d.before;
      if (d.before) beforeText.textContent = d.before;
      afterWrap.hidden = false;
      afterText.textContent = d.after;
    }

    if (d.note) {
      noteEl.hidden = false;
      noteEl.textContent = d.note;
    } else {
      noteEl.hidden = true;
    }

    linkEl.href = d.byHref;

    panel!.dataset.state = "detail";
  }

  document.addEventListener("click", (ev) => {
    const target = ev.target as HTMLElement;
    if (target.closest(".amend-panel")) return;
    const amend = target.closest(".amend") as HTMLElement | null;
    if (amend) {
      ev.preventDefault();
      document
        .querySelectorAll(".amend.is-active")
        .forEach((n) => n.classList.remove("is-active"));
      amend.classList.add("is-active");
      showAmend(amend);
    }
  });

  closeBtn.addEventListener("click", clear);

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && panel.dataset.state === "detail") {
      clear();
    }
  });
}

function setupTimeline() {
  const picker = document.querySelector(".version-picker") as HTMLElement | null;
  const wrap = document.querySelector(".section-body-wrap") as HTMLElement | null;
  if (!picker || !wrap) return;

  const currentBody = wrap.querySelector(
    ".statute-body-current",
  ) as HTMLElement | null;
  const historicalBodies = wrap.querySelectorAll<HTMLElement>(
    ".statute-body-historical",
  );

  if (!currentBody) return;

  const innerSnapshot = currentBody.innerHTML;

  const buttons = picker.querySelectorAll<HTMLButtonElement>(".version-pill");
  const dates = Array.from(buttons).map((b) => b.dataset.version!);
  const currentDate = dates[dates.length - 1];

  function applyVersion(date: string) {
    const target = new Date(date).getTime();

    let historicalShown = false;
    historicalBodies.forEach((hb) => {
      const hbDate = new Date(hb.dataset.version ?? "").getTime();
      const showHistorical = target <= hbDate;
      hb.hidden = !showHistorical;
      if (showHistorical) historicalShown = true;
    });
    currentBody!.hidden = historicalShown;

    currentBody!.innerHTML = innerSnapshot;

    if (!historicalShown) {
      currentBody!
        .querySelectorAll<HTMLElement>(".amend")
        .forEach((amend) => {
          const eff = new Date(amend.dataset.date ?? "").getTime();
          const kind = amend.dataset.kind;
          if (eff > target) {
            if (kind === "inserted") {
              const para = amend.closest("p");
              if (
                para &&
                para.querySelectorAll(".amend").length === 1 &&
                (amend.textContent ?? "").trim().length > 20 &&
                (para.textContent ?? "").trim() ===
                  (amend.textContent ?? "").trim()
              ) {
                para.classList.add("hidden-by-version");
              } else {
                amend.outerHTML = "";
              }
            } else if (kind === "substituted") {
              if (amend.dataset.before) {
                amend.textContent = amend.dataset.before;
                amend.classList.add("rolled-back");
              }
            }
          }
        });
    }

    wrap!.classList.toggle("is-historical", date !== currentDate);
  }

  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const date = btn.dataset.version!;
      buttons.forEach((b) => {
        b.dataset.active = "false";
        b.setAttribute("aria-selected", "false");
      });
      btn.dataset.active = "true";
      btn.setAttribute("aria-selected", "true");
      applyVersion(date);
    });
  });
}

setupAmendPanel();
setupTimeline();
