// کد مشترک دو صفحه‌ی «بازار ایران» و «آمار واردات ایران»
const MONTHS_FA = ["ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن", "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر"];
const MONTHS_IR = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
const DAY = 86400000;

const esc = (s) => String(s).replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]));
const num = (s) => `<span class="num">${s}</span>`;
const fmt = (v, d = 0) => v.toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d });
const monthLabel = (p) => `${MONTHS_FA[+p.slice(5, 7) - 1]} ${p.slice(0, 4)}`;
const dayLabel = (d, withYear = true) => `${+d.slice(8, 10)} ${MONTHS_FA[+d.slice(5, 7) - 1]}${withYear ? " " + d.slice(0, 4) : ""}`;
const rangeLabel = (a, b) => `${dayLabel(a, a.slice(0, 4) !== b.slice(0, 4))} تا ${dayLabel(b)}`;

function shiftMonth(p, n) {
  const d = new Date(Date.UTC(+p.slice(0, 4), +p.slice(5, 7) - 1 + n, 1));
  return d.toISOString().slice(0, 7);
}
function monthRange(from, to) {
  const out = [];
  for (let p = from; p <= to; p = shiftMonth(p, 1)) out.push(p);
  return out;
}

const crosshair = {
  id: "crosshair",
  afterDatasetsDraw(chart) {
    const a = chart.tooltip?.getActiveElements?.();
    if (!a || !a.length) return;
    const { ctx, chartArea } = chart;
    ctx.save(); ctx.strokeStyle = "#c3c2b7"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(a[0].element.x, chartArea.top); ctx.lineTo(a[0].element.x, chartArea.bottom); ctx.stroke();
    ctx.restore();
  },
};

function baseOptions(yFmt, tooltipLabel) {
  return {
    maintainAspectRatio: false, animation: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        rtl: true, textDirection: "rtl",
        backgroundColor: "#ffffff", titleColor: "#0b0b0b", bodyColor: "#52514e",
        borderColor: "rgba(11,11,11,0.15)", borderWidth: 1, padding: 10, boxPadding: 4,
        filter: (it) => it.parsed.y != null,
        callbacks: { title: (it) => monthLabel(it[0].label), label: tooltipLabel },
      },
    },
    scales: {
      x: { grid: { display: false }, border: { color: "#c3c2b7" },
           ticks: { color: "#898781", maxRotation: 0, autoSkipPadding: 16, callback(v) { return this.getLabelForValue(v).replace("-", "/"); } } },
      y: { position: "right", grid: { color: "#e1e0d9" }, border: { display: false },
           ticks: { color: "#898781", callback: yFmt } },
    },
  };
}

async function getJson(path) {
  const res = await fetch(path, { cache: "no-cache" });
  if (!res.ok) throw new Error("HTTP " + res.status);
  return res.json();
}

// دکمه‌های انتخاب کالا بالای صفحه؛ انتخاب بین دو صفحه یادش می‌ماند
const PICK_KEY = "iran-commodity";
function setupPicker(commodities, onChange) {
  let saved = null;
  try { saved = localStorage.getItem(PICK_KEY); } catch (e) { /* مرورگر اجازه نمی‌دهد؛ مهم نیست */ }
  let current = commodities.find((c) => c.key === saved) || commodities[0];
  const el = document.getElementById("pick");
  el.innerHTML = commodities.map((c) => `<button data-key="${esc(c.key)}">${esc(c.name_fa)}</button>`).join("");
  const select = (c) => {
    current = c;
    el.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.key === c.key)));
    try { localStorage.setItem(PICK_KEY, c.key); } catch (e) { /* مهم نیست */ }
    onChange(c);
  };
  el.addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    select(commodities.find((c) => c.key === b.dataset.key));
  });
  select(current);
}
