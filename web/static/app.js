/* Sprout front-end: one smart input that auto-routes to six checks
 * (savings / trip / claim / shop / worth / lookup), each with a tailored renderer,
 * a savings-plan ledger, and Google/WhatsApp URL-spec dispatch. */
"use strict";

const $ = (id) => document.getElementById(id);

const MODES = {
  auto: {
    hint: "Paste anything — a bill, a trip, a product, an eco-claim, an order, or ask “is solar worth it?”. Sprout detects what you need.",
    sample: "My electricity bill is around ₹3,200 a month with two ACs running most of the day.",
  },
  savings: {
    hint: "Paste your bill, fuel, or monthly spend → specific actions that save real ₹ + carbon.",
    sample:
      "Monthly electricity bill ₹3,200 with two ACs ~6 hours a day, plus ₹4,000/month on petrol commuting.",
  },
  trip: {
    hint: "Describe a trip → options ranked by carbon, cost and time.",
    sample: "I need to travel from Mumbai to Pune, about 150 km. I usually drive — greener options?",
  },
  shop: {
    hint: "Paste an order, cart, or receipt → footprint + cheaper-greener swaps.",
    sample: "My grocery order: 2 kg beef, a packet of imported cheese, 6 plastic water bottles, 5 kg rice.",
  },
  worth: {
    hint: "Ask about a big purchase → personalised payback in ₹, kg and years.",
    sample: "Is rooftop solar worth it for a home with a ₹3,000/month electricity bill in Mumbai?",
  },
  claim: {
    hint: "Paste an “eco-friendly” marketing line → legit or greenwashing, and why.",
    sample:
      "This fast-fashion brand says its collection is “100% sustainable and carbon neutral, made from eco-conscious fabrics”.",
  },
  lookup: {
    hint: "Ask “what's the footprint of X?” → a number + a relatable comparison.",
    sample: "What's the carbon footprint of a one-way flight from Mumbai to Delhi?",
  },
};

const LABEL = {
  savings: "Find savings 💰",
  trip: "Greener trip 🚆",
  claim: "Eco-claim 🔍",
  shop: "Shopping 🛒",
  worth: "Worth it? ⚖️",
  lookup: "Footprint 📊",
};

let currentMode = "auto";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}

function toast(message, actions = [], sticky = false) {
  const el = document.createElement("div");
  el.className = "toast";
  el.setAttribute("role", "status");
  const span = document.createElement("span");
  span.textContent = message;
  el.appendChild(span);
  actions.forEach((a) => {
    const b = document.createElement("button");
    b.textContent = a.label;
    b.onclick = () => {
      a.onClick();
      el.remove();
    };
    el.appendChild(b);
  });
  $("toast-root").appendChild(el);
  if (!sticky) setTimeout(() => el.remove(), 6000);
}

const esc = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const EFFORT_TINT = { easy: "#2f9e44", medium: "#e8973c", hard: "#c94c3c" };
const VERDICT = {
  legit: { label: "Looks legit ✅", color: "#2f9e44" },
  mixed: { label: "Mixed — be careful ⚠️", color: "#e8973c" },
  greenwashing: { label: "Greenwashing 🚩", color: "#c94c3c" },
  "worth it": { label: "Worth it ✅", color: "#2f9e44" },
  borderline: { label: "Borderline ⚖️", color: "#e8973c" },
  "not yet": { label: "Not yet 🚩", color: "#c94c3c" },
};

// ---------------------------------------------------------------------------
// Mode switching
// ---------------------------------------------------------------------------
function setMode(mode) {
  currentMode = mode;
  document.querySelectorAll(".mode-tab").forEach((t) => {
    const on = t.dataset.mode === mode;
    t.setAttribute("aria-selected", on ? "true" : "false");
    t.classList.toggle("mode-tab-active", on);
  });
  $("mode-hint").textContent = MODES[mode].hint;
}

// ---------------------------------------------------------------------------
// Ask
// ---------------------------------------------------------------------------
async function ask() {
  const input = $("ask-input").value.trim();
  if (!input) {
    toast("Type or paste your question first 🙂");
    return;
  }
  $("ask").disabled = true;
  const label = $("ask").innerHTML;
  $("ask").textContent = "Thinking…";
  try {
    const env = await postJSON("/api/analyze", { mode: currentMode, input });
    const badge = $("detected");
    if (currentMode === "auto") {
      badge.textContent = "Detected: " + (LABEL[env.mode] || env.mode);
      badge.classList.remove("hidden");
    } else {
      badge.classList.add("hidden");
    }
    (RENDER[env.mode] || RENDER.lookup)(env.result);
    $("result").classList.remove("hidden");
    $("result").scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (e) {
    toast(e.message);
  } finally {
    $("ask").disabled = false;
    $("ask").innerHTML = label;
  }
}

// ---------------------------------------------------------------------------
// Renderers (one per check)
// ---------------------------------------------------------------------------
function commitButton(label, kgYear, inrYear, text = "Commit ✅") {
  return `<button class="commit-btn shrink-0 bg-leafdark hover:bg-leafdarker text-white font-semibold px-3 py-2 rounded-lg focus:ring-2 focus:ring-leaf"
    data-label="${esc(label)}" data-kg="${kgYear}" data-inr="${inrYear}">${text}</button>`;
}

function wireCommits() {
  document.querySelectorAll(".commit-btn").forEach((b) => {
    b.onclick = () => {
      commit(b.dataset.label, +b.dataset.kg, +b.dataset.inr);
      b.textContent = "Banked 🌿";
      b.disabled = true;
    };
  });
}

const RENDER = {
  savings(d) {
    const actions = [...d.actions].sort((a, b) => b.saves_inr_year - a.saves_inr_year);
    const total = actions.reduce((s, a) => s + a.saves_inr_year, 0);
    const cards = actions
      .map(
        (a) => `
      <li class="bg-white rounded-xl border border-black/5 p-4 flex flex-wrap items-center justify-between gap-3">
        <div class="min-w-0"><p class="font-semibold">${esc(a.action)}</p>
          <p class="text-sm text-bark">₹${a.saves_inr_year}/yr · ${a.saves_kg_year} kg/yr ·
            <span style="color:${EFFORT_TINT[a.effort] || "#4a3f35"}">${esc(a.effort)}</span> · payback ${esc(a.payback)}</p></div>
        ${commitButton(a.action, a.saves_kg_year, a.saves_inr_year)}
      </li>`,
      )
      .join("");
    $("result-body").innerHTML = `
      <div class="bg-leaf/10 border border-leaf/30 rounded-2xl p-5">
        <p class="text-xl font-bold text-leafdark">₹${total}/year in savings found</p>
        <p class="text-bark">${esc(d.summary || "")}</p></div>
      <ul class="grid gap-2">${cards}</ul>`;
    wireCommits();
  },

  trip(d) {
    const opts = [...d.options].sort((a, b) => a.kg - b.kg);
    const rows = opts
      .map((o) => {
        const best = o.mode === d.best;
        return `<li class="bg-white rounded-xl border ${best ? "border-leaf" : "border-black/5"} p-4 flex flex-wrap justify-between gap-2">
        <div><p class="font-semibold">${esc(o.mode)} ${best ? '<span class="text-leafdark text-xs">★ best</span>' : ""}</p>
          <p class="text-sm text-bark">${esc(o.note || "")}</p></div>
        <div class="text-sm text-right text-bark"><p><strong>${o.kg} kg</strong> CO₂</p><p>₹${o.cost_inr} · ${esc(o.time)}</p></div></li>`;
      })
      .join("");
    $("result-body").innerHTML = `
      <div class="bg-white rounded-2xl p-5 shadow-sm">
        <p class="text-lg font-bold">${esc(d.from)} → ${esc(d.to)} · ~${d.distance_km} km</p>
        <p class="text-bark">Greenest practical option: <strong>${esc(d.best)}</strong></p></div>
      <ul class="grid gap-2">${rows}</ul>`;
  },

  claim(d) {
    const v = VERDICT[d.verdict] || VERDICT.mixed;
    const reasons = (d.reasons || []).map((r) => `<li class="text-bark">• ${esc(r)}</li>`).join("");
    $("result-body").innerHTML = `
      <div class="bg-white rounded-2xl p-5 shadow-sm grid gap-2">
        <span class="inline-block w-max px-3 py-1 rounded-full font-semibold" style="background:${v.color}22;color:${v.color}">${v.label}</span>
        <p class="italic text-bark">"${esc(d.claim)}"</p>
        <ul class="grid gap-1">${reasons}</ul>
        ${d.tip ? `<p class="text-sm bg-cream rounded-lg p-3"><strong>What to look for:</strong> ${esc(d.tip)}</p>` : ""}</div>`;
  },

  shop(d) {
    const items = (d.items || [])
      .map(
        (it) => `
      <li class="bg-white rounded-xl border border-black/5 p-4 flex flex-wrap items-center justify-between gap-3">
        <div class="min-w-0"><p class="font-semibold">${esc(it.item)} · ${it.kg} kg</p>
          <p class="text-sm text-bark">Swap: ${esc(it.swap)} (saves ${it.saves_kg} kg)</p></div>
        ${commitButton("Shop swap: " + it.swap, (it.saves_kg || 0) * 52, 0)}
      </li>`,
      )
      .join("");
    $("result-body").innerHTML = `
      <div class="bg-white rounded-2xl p-5 shadow-sm">
        <p class="text-xl font-bold">${d.total_kg} kg CO₂e in this order</p>
        <p class="text-bark">${esc(d.summary || "")} You could cut <strong>${d.total_saves_kg} kg</strong> with the swaps below.</p></div>
      <ul class="grid gap-2">${items}</ul>`;
    wireCommits();
  },

  worth(d) {
    const v = VERDICT[d.verdict] || VERDICT.borderline;
    $("result-body").innerHTML = `
      <div class="bg-white rounded-2xl p-5 shadow-sm grid gap-2">
        <span class="inline-block w-max px-3 py-1 rounded-full font-semibold" style="background:${v.color}22;color:${v.color}">${v.label}</span>
        <p class="text-lg font-bold">${esc(d.item)}</p>
        <div class="grid grid-cols-3 gap-3 text-center my-1">
          <div class="bg-cream rounded-xl p-3"><p class="text-xl font-bold text-leafdark">₹${d.upfront_inr}</p><p class="text-xs text-bark">upfront</p></div>
          <div class="bg-cream rounded-xl p-3"><p class="text-xl font-bold text-leafdark">₹${d.saves_inr_year}</p><p class="text-xs text-bark">saved / year</p></div>
          <div class="bg-cream rounded-xl p-3"><p class="text-xl font-bold text-leafdark">${d.payback_years} yr</p><p class="text-xs text-bark">payback</p></div></div>
        <p class="text-bark">${esc(d.note || "")}</p>
        <div>${commitButton(d.item, d.saves_kg_year, d.saves_inr_year, "Add to my plan ✅")}</div></div>`;
    wireCommits();
  },

  lookup(d) {
    $("result-body").innerHTML = `
      <div class="bg-white rounded-2xl p-6 shadow-sm text-center grid gap-1">
        <p class="text-bark">${esc(d.thing)}</p>
        <p class="text-4xl font-bold text-leafdark">${d.kg} kg CO₂e <span class="text-base text-bark">${esc(d.unit || "")}</span></p>
        <p class="text-lg">${esc(d.equivalent || "")}</p>
        ${d.context ? `<p class="text-sm text-bark">${esc(d.context)}</p>` : ""}</div>`;
  },
};

// ---------------------------------------------------------------------------
// Savings plan ledger
// ---------------------------------------------------------------------------
function planCode() {
  return $("plan-code").value.trim();
}

function commit(label, kgYear, inrYear) {
  const plan = planCode();
  if (!plan) {
    toast("Open a plan first to bank your savings 🌳", [
      { label: "OK", onClick: () => $("plan-code").focus() },
    ]);
    return;
  }
  postJSON("/api/plan", { plan, action: "commit", label, kg_year: kgYear, inr_year: inrYear })
    .then(renderPlan)
    .then(() => toast("Banked! Your plan just grew 🌿"))
    .catch((e) => toast(e.message));
}

async function openPlan() {
  const plan = planCode();
  if (!plan) {
    toast("Enter a plan code");
    return;
  }
  try {
    renderPlan(await postJSON("/api/plan", { plan }));
    localStorage.setItem("sprout:plan", plan);
  } catch (e) {
    toast(e.message);
  }
}

function renderPlan(s) {
  $("plan-view").classList.remove("hidden");
  $("plan-inr").textContent = "₹" + s.total_inr_year;
  $("plan-kg").textContent = s.total_kg_year;
  $("plan-trees").textContent = s.trees;
  $("plan-actions").innerHTML =
    s.actions.map((a) => `<li class="bg-cream rounded-lg px-3 py-2">✅ ${esc(a)}</li>`).join("") ||
    '<li class="text-bark">No actions yet — commit one above.</li>';
}

function planReminder() {
  const text = encodeURIComponent("Sprout: start my savings actions");
  const details = encodeURIComponent(
    `On track to save ${$("plan-inr").textContent}/yr and ${$("plan-kg").textContent} kg CO₂. — Sprout`,
  );
  window.open(
    `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${text}&details=${details}`,
    "_blank",
    "noopener",
  );
}

function planEmail() {
  const su = encodeURIComponent(`My Sprout plan: ${$("plan-inr").textContent}/yr in savings`);
  const items = [...document.querySelectorAll("#plan-actions li")].map((li) => li.textContent).join("\n");
  const body = encodeURIComponent(
    `My savings plan (${planCode() || "plan"}):\n\n${items}\n\nOn track: ${$("plan-inr").textContent}/yr, ${$("plan-kg").textContent} kg CO₂/yr.`,
  );
  window.open(`https://mail.google.com/mail/?view=cm&fs=1&su=${su}&body=${body}`, "_blank", "noopener");
}

function planShare() {
  const plan = planCode() || "sprout-plan";
  const link = `${location.origin}/?plan=${encodeURIComponent(plan)}`;
  const text = encodeURIComponent(
    `Join my Sprout savings plan — let's cut bills + carbon together 🌳 ${link}`,
  );
  window.open(`https://wa.me/?text=${text}`, "_blank", "noopener");
}

// ---------------------------------------------------------------------------
// Wire up
// ---------------------------------------------------------------------------
function init() {
  document.querySelectorAll(".mode-tab").forEach((t) => {
    t.onclick = () => setMode(t.dataset.mode);
  });
  $("ask").onclick = ask;
  $("load-sample").onclick = () => {
    $("ask-input").value = MODES[currentMode].sample;
    $("ask-input").focus();
  };
  $("plan-open").onclick = openPlan;
  $("plan-remind").onclick = planReminder;
  $("plan-email").onclick = planEmail;
  $("plan-share").onclick = planShare;

  $("ask-input").addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") ask();
  });

  const params = new URLSearchParams(location.search);
  const p = params.get("plan") || localStorage.getItem("sprout:plan");
  if (p) {
    $("plan-code").value = p;
    openPlan();
  }

  setMode("auto");
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", init);
}
