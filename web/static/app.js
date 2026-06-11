/* Sprout front-end: one analyse call, the swap loop, what-if, and the Grove.
 * Distribution (reminders, digest, share) uses Google/WhatsApp URL-specs — no OAuth. */
"use strict";

const $ = (id) => document.getElementById(id);
const STORAGE_KEY = "sprout:v1";
const SAMPLE = "Drove 20 km to work, had a beef burger for lunch, ran the AC for 3 hours, took a 15 minute hot shower";

let lastSwap = null; // remembered for the Calendar reminder + Grove "Did it"

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
    b.onclick = () => { a.onClick(); el.remove(); };
    el.appendChild(b);
  });
  $("toast-root").appendChild(el);
  if (!sticky) setTimeout(() => el.remove(), 6000);
}

const CATEGORY_ICON = { transport: "🚗", food: "🍔", energy: "⚡", other: "📦", general: "📦" };

// ---------------------------------------------------------------------------
// Analyse a day
// ---------------------------------------------------------------------------
async function analyze() {
  const activity = $("activity").value.trim();
  if (!activity) { toast("Tell me about your day first 🙂"); return; }
  $("analyze").disabled = true;
  $("analyze").textContent = "Analysing…";
  try {
    const data = await postJSON("/api/log", { activity });
    renderResult(data);
    persist({ activity, result: data });
  } catch (e) {
    toast(e.message);
  } finally {
    $("analyze").disabled = false;
    $("analyze").innerHTML = 'Analyse my day <span class="text-white/70 text-xs ml-1">⌘↵</span>';
  }
}

function renderResult(data) {
  $("summary").textContent = data.summary;
  $("equivalence").textContent = data.equivalence;

  const g = data.gauge;
  const pct = Math.min(100, Math.round(g.ratio * 100));
  const bar = $("gauge-bar");
  bar.style.width = pct + "%";
  const colors = { green: "#2f9e44", amber: "#e8973c", red: "#c94c3c" };
  bar.style.background = colors[g.level];
  $("gauge-label").textContent = g.label + ` (target ${g.target_kg} kg/day)`;
  const pill = $("gauge-pill");
  pill.textContent = g.level === "green" ? "On track" : g.level === "amber" ? "Close" : "Over";
  pill.style.background = colors[g.level] + "22";
  pill.style.color = colors[g.level];

  const sprout = $("sprout");
  sprout.textContent = g.level === "green" ? "🌳" : g.level === "amber" ? "🌿" : "🌱";
  sprout.classList.toggle("sprout-grow", g.level === "green");

  const items = $("items");
  items.innerHTML = "";
  data.items.forEach((it) => {
    const li = document.createElement("li");
    li.className = "bg-white rounded-lg border border-black/5 p-3 flex justify-between";
    li.innerHTML =
      `<span>${CATEGORY_ICON[it.category] || "📦"} ${it.label}</span>` +
      `<span class="font-semibold">${it.kg} kg</span>`;
    items.appendChild(li);
  });

  lastSwap = data.swap;
  $("swap-tip").textContent = data.swap.tip;
  $("swap-savings").textContent =
    `Saves ≈ ${data.swap.kg_saved} kg CO₂ and ₹${data.swap.money_inr}.`;
  $("result").classList.remove("hidden");
  $("result").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// ---------------------------------------------------------------------------
// Swap loop: commit to a Grove + Calendar reminder
// ---------------------------------------------------------------------------
function didIt() {
  const grove = $("grove-code").value.trim();
  if (!lastSwap) return;
  if (!grove) { toast("Join a Grove first to bank your savings 🌳"); return; }
  postJSON("/api/grove", {
    grove, action: "log", member: localStorage.getItem("sprout:name") || "you",
    kg_saved: lastSwap.kg_saved, money_inr: lastSwap.money_inr,
  }).then(renderGrove).then(() => toast("Banked! Your Grove just grew 🌿")).catch((e) => toast(e.message));
}

function addReminder() {
  if (!lastSwap) return;
  // Google Calendar URL-spec — opens in the user's logged-in tab, no OAuth.
  const text = encodeURIComponent("Sprout swap: " + lastSwap.tip);
  const details = encodeURIComponent(`Saves ~${lastSwap.kg_saved} kg CO2 and ₹${lastSwap.money_inr}. — Sprout`);
  const url =
    "https://calendar.google.com/calendar/render?action=TEMPLATE" +
    `&text=${text}&details=${details}`;
  window.open(url, "_blank", "noopener");
}

// ---------------------------------------------------------------------------
// What-if simulator
// ---------------------------------------------------------------------------
async function runWhatif() {
  const change = $("whatif-input").value.trim();
  if (!change) { toast("Type a change to simulate"); return; }
  $("whatif-go").disabled = true;
  try {
    const data = await postJSON("/api/whatif", { change });
    const box = $("whatif-result");
    box.classList.remove("hidden");
    box.innerHTML =
      `<p class="font-semibold">${change}</p>` +
      `<p class="text-bark">Saves about <strong>${Math.round(data.annual_kg)} kg CO₂</strong>, ` +
      `<strong>₹${Math.round(data.annual_money_inr)}</strong> and ${data.trees} trees' worth per year.</p>` +
      (data.note ? `<p class="text-sm text-bark mt-1">${data.note}</p>` : "");
  } catch (e) {
    toast(e.message);
  } finally {
    $("whatif-go").disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Grove
// ---------------------------------------------------------------------------
async function joinGrove() {
  const grove = $("grove-code").value.trim();
  if (!grove) { toast("Enter a Grove code"); return; }
  try {
    renderGrove(await postJSON("/api/grove", { grove, action: "state" }));
    localStorage.setItem("sprout:grove", grove);
  } catch (e) { toast(e.message); }
}

function renderGrove(state) {
  $("grove-view").classList.remove("hidden");
  $("grove-trees").textContent = state.trees;
  $("grove-money").textContent = "₹" + Math.round(state.total_money_inr);
  $("grove-swaps").textContent = state.swaps;
  const trees = Math.max(state.members.length, Math.min(20, Math.round(state.trees)));
  $("grove-forest").textContent = "🌳".repeat(Math.max(1, trees));
  $("grove-goalbar").style.width = state.goal_pct + "%";
  $("grove-goal").textContent =
    `${state.total_kg} of ${state.goal_kg} kg saved · ${state.members.length} member(s) · ${state.goal_pct}% to weekly goal`;
}

function shareGrove() {
  const grove = $("grove-code").value.trim() || "sprout-grove";
  const link = `${location.origin}/?grove=${encodeURIComponent(grove)}`;
  const text = encodeURIComponent(`Join my Sprout Grove and let's cut our carbon together 🌳 ${link}`);
  // WhatsApp URL-spec — no auth.
  window.open(`https://wa.me/?text=${text}`, "_blank", "noopener");
}

function emailDigest() {
  const grove = $("grove-code").value.trim() || "your Grove";
  const trees = $("grove-trees").textContent;
  const money = $("grove-money").textContent;
  // Gmail compose URL-spec — opens prefilled in the user's logged-in tab, no OAuth.
  const su = encodeURIComponent(`🌳 ${grove} saved ${money} this week`);
  const body = encodeURIComponent(
    `This week your Sprout Grove "${grove}" grew to ${trees} trees' worth and saved ${money}.\n\n` +
    `Keep the streak going — your next swap is waiting in Sprout.`);
  window.open(`https://mail.google.com/mail/?view=cm&fs=1&su=${su}&body=${body}`, "_blank", "noopener");
}

// ---------------------------------------------------------------------------
// Persistence (restore last session)
// ---------------------------------------------------------------------------
function persist(state) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ data: state, savedAt: Date.now() }));
}

function maybeRestore() {
  const blob = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
  if (!blob) return;
  if (Date.now() - blob.savedAt > 7 * 864e5) return;
  toast("Restore your last session?", [
    { label: "Restore", onClick: () => { $("activity").value = blob.data.activity; renderResult(blob.data.result); } },
    { label: "Dismiss", onClick: () => localStorage.removeItem(STORAGE_KEY) },
  ], true);
}

// ---------------------------------------------------------------------------
// Wire up
// ---------------------------------------------------------------------------
function init() {
  $("analyze").onclick = analyze;
  $("load-sample").onclick = () => { $("activity").value = SAMPLE; $("activity").focus(); };
  $("did-it").onclick = didIt;
  $("remind").onclick = addReminder;
  $("whatif-go").onclick = runWhatif;
  $("grove-join").onclick = joinGrove;
  $("grove-share").onclick = shareGrove;
  $("grove-email").onclick = emailDigest;

  document.querySelectorAll(".whatif-preset").forEach((b) => {
    b.onclick = () => { $("whatif-input").value = b.textContent.trim(); runWhatif(); };
  });

  // ⌘/Ctrl+Enter analyses from the textarea.
  $("activity").addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") analyze();
  });

  // Deep link: /?grove=code prefills + joins.
  const params = new URLSearchParams(location.search);
  const g = params.get("grove") || localStorage.getItem("sprout:grove");
  if (g) { $("grove-code").value = g; joinGrove(); }

  maybeRestore();
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", init);
}
