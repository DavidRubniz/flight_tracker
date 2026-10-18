// Alpine.js component driving the whole UI. Talks to the FastAPI backend under /api.
"use strict";

const api = {
  async request(method, path, body) {
    const response = await fetch(`/api${path}`, {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const detail = Array.isArray(payload.detail)
        ? payload.detail.map((d) => d.msg).join(", ")
        : payload.detail;
      throw new Error(detail || `HTTP ${response.status}`);
    }
    return response.status === 204 ? null : response.json();
  },
  get: (path) => api.request("GET", path),
  post: (path, body) => api.request("POST", path, body ?? {}),
  put: (path, body) => api.request("PUT", path, body),
  patch: (path, body) => api.request("PATCH", path, body),
  del: (path) => api.request("DELETE", path),
};

const STATUS_POLL_IDLE_MS = 15000;
const STATUS_POLL_BUSY_MS = 2000;
const charts = new Map(); // canvas id -> Chart instance (kept outside Alpine's reactivity)

function drawChart(canvasId, points, { sparkline = false } = {}) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  charts.get(canvasId)?.destroy();
  if (!points.length) return;

  const ctx = canvas.getContext("2d");
  const gradient = ctx.createLinearGradient(0, 0, 0, canvas.clientHeight || 120);
  gradient.addColorStop(0, "rgba(56, 189, 248, 0.35)");
  gradient.addColorStop(1, "rgba(56, 189, 248, 0)");

  charts.set(canvasId, new Chart(ctx, {
    type: "line",
    data: {
      labels: points.map((p) => new Date(p.at).toLocaleString("he-IL", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })),
      datasets: [{
        data: points.map((p) => p.price),
        borderColor: "#38bdf8",
        backgroundColor: gradient,
        fill: true,
        tension: 0.35,
        borderWidth: 2,
        pointRadius: sparkline ? 0 : 3,
        pointHoverRadius: 4,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: { legend: { display: false }, tooltip: { enabled: !sparkline, rtl: true } },
      scales: sparkline
        ? { x: { display: false }, y: { display: false } }
        : {
            x: { ticks: { color: "#64748b", maxTicksLimit: 8 }, grid: { color: "rgba(255,255,255,.04)" } },
            y: { ticks: { color: "#64748b" }, grid: { color: "rgba(255,255,255,.04)" } },
          },
    },
  }));
}

// eslint-disable-next-line no-unused-vars
function tracker() {
  return {
    tabs: [
      { id: "dashboard", label: "לוח בקרה", icon: "📊" },
      { id: "flights", label: "טיסות זולות", icon: "🎫" },
      { id: "alerts", label: "התראות", icon: "🔔" },
      { id: "settings", label: "הגדרות", icon: "⚙️" },
    ],
    channels: [
      { id: "desktop", key: "notify_desktop", label: "התראות שולחן עבודה" },
      { id: "telegram", key: "notify_telegram", label: "Telegram" },
      { id: "email", key: "notify_email", label: "אימייל" },
    ],
    tab: "dashboard",
    meta: { origin: "TLV", currency: "USD", provider: "", regions: {}, airport_names: {}, channels: {} },
    status: { running: false, errors: [], progress: "", next_run: null },
    rows: [],
    destinations: [],
    offers: [],
    alerts: [],
    settings: {},
    offsetsText: "",
    offerFilter: { destination: 0, maxStops: 9 },
    newDest: { code: "", target_price: null, max_stops: 1, trip_nights: 7 },
    details: null,
    detailOffers: [],
    toast: "",
    _pollTimer: null,
    _seenFinish: undefined, // last scan finish time the UI has rendered
    _awaitingScan: false, // a scan was requested; poll quickly until it finishes

    // ------------------------------------------------------------ lifecycle
    async init() {
      try {
        this.meta = await api.get("/meta");
        await Promise.all([this.refresh(), this.loadSettings()]);
      } catch (err) {
        this.notify(`שגיאה בטעינה: ${err.message}`);
      }
      this.pollStatus();
    },

    async refresh() {
      const [rows, destinations, offers, alerts] = await Promise.all([
        api.get("/dashboard"), api.get("/destinations"), api.get("/offers?limit=200"), api.get("/alerts"),
      ]);
      Object.assign(this, { rows, destinations, offers, alerts });
      this.$nextTick(() => rows.forEach((r) => drawChart(`spark-${r.destination.id}`, r.history, { sparkline: true })));
    },

    // Detect finished scans by comparing finish times (not the "running" flag): a fast background
    // scan can start and finish entirely between two polls.
    async pollStatus() {
      try {
        this.status = await api.get("/status");
        const finished = this.status.last_finished ?? null;
        if (this._seenFinish === undefined) {
          this._seenFinish = finished; // first poll after page load - data is already fresh
        } else if (finished !== this._seenFinish) {
          this._seenFinish = finished;
          this._awaitingScan = false;
          await this.refresh();
          this.notify("הסריקה הסתיימה ✓");
        }
      } catch { /* server restarting - try again on next tick */ }
      clearTimeout(this._pollTimer);
      const busy = this.status.running || this._awaitingScan;
      this._pollTimer = setTimeout(() => this.pollStatus(), busy ? STATUS_POLL_BUSY_MS : STATUS_POLL_IDLE_MS);
    },
    watchScan(accepted) {
      this._awaitingScan = accepted;
      this.pollStatus();
    },

    // ------------------------------------------------------------ computed
    get cheapestRow() {
      return this.rows.filter((r) => r.current_price).sort((a, b) => a.current_price - b.current_price)[0] ?? null;
    },
    get recentAlerts() {
      const dayAgo = Date.now() - 24 * 3600 * 1000;
      return this.alerts.filter((a) => new Date(a.created_at).getTime() > dayAgo).length;
    },
    get filteredOffers() {
      return this.offers.filter((o) =>
        (!this.offerFilter.destination || o.destination_id === this.offerFilter.destination) &&
        o.stops <= this.offerFilter.maxStops);
    },

    // ------------------------------------------------------------ actions
    async scanAll() {
      await this.run(async () => {
        const res = await api.post("/scan");
        this.notify(res.message);
        this.watchScan(res.accepted);
      });
    },
    async scanOne(destination) {
      await this.run(async () => {
        const res = await api.post(`/scan/${destination.id}`);
        this.notify(`${destination.name}: ${res.message}`);
        this.watchScan(res.accepted);
      });
    },
    async openDetails(row) {
      this.details = row;
      this.detailOffers = this.offers.filter((o) => o.destination_id === row.destination.id).slice(0, 10);
      const history = await api.get(`/destinations/${row.destination.id}/history?days=90`);
      this.$nextTick(() => drawChart("detail-chart", history));
    },
    async addDestination() {
      await this.run(async () => {
        const body = {
          code: this.newDest.code.trim().toUpperCase(),
          target_price: this.newDest.target_price || null,
          max_stops: this.newDest.max_stops,
          trip_nights: this.newDest.trip_nights || null,
        };
        await api.post("/destinations", body);
        this.newDest = { code: "", target_price: null, max_stops: 1, trip_nights: 7 };
        await this.refresh();
        this.notify("היעד נוסף ✓");
      });
    },
    async updateDestination(destination, patch) {
      await this.run(async () => {
        await api.patch(`/destinations/${destination.id}`, patch);
        await this.refresh();
      });
    },
    async removeDestination(destination) {
      if (!confirm(`למחוק את ${destination.name} וכל ההיסטוריה שלו?`)) return;
      await this.run(async () => {
        await api.del(`/destinations/${destination.id}`);
        await this.refresh();
      });
    },
    async loadSettings() {
      this.settings = await api.get("/settings");
      this.offsetsText = this.settings.date_offsets_days.join(", ");
    },
    async saveSettings() {
      await this.run(async () => {
        const offsets = this.offsetsText.split(",").map((s) => parseInt(s, 10)).filter(Number.isFinite);
        this.settings = await api.put("/settings", { ...this.settings, date_offsets_days: offsets });
        this.offsetsText = this.settings.date_offsets_days.join(", ");
        this.pollStatus(); // picks up the rescheduled next run
        this.notify("ההגדרות נשמרו ✓");
      });
    },
    async testNotifications() {
      await this.run(async () => {
        const report = await api.post("/notifications/test");
        const parts = Object.entries(report).map(([k, v]) => `${k}: ${v === "ok" ? "✓" : v}`);
        this.notify(parts.length ? parts.join(" · ") : "אין ערוצי התראה פעילים");
      });
    },

    async run(action) {
      try { await action(); } catch (err) { this.notify(`שגיאה: ${err.message}`); }
    },
    notify(message) {
      this.toast = message;
      clearTimeout(this._toastTimer);
      this._toastTimer = setTimeout(() => (this.toast = ""), 3500);
    },

    // ------------------------------------------------------------ formatting
    money(value, currency) {
      if (value == null) return "—";
      return new Intl.NumberFormat("he-IL", { style: "currency", currency: currency || this.meta.currency, maximumFractionDigits: 0 }).format(value);
    },
    fmtDate: (iso) => new Date(iso).toLocaleDateString("he-IL", { day: "2-digit", month: "2-digit", year: "2-digit" }),
    fmtTime: (iso) => new Date(iso).toLocaleString("he-IL", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }),
    hhmm: (iso) => new Date(iso).toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" }),
    duration: (minutes) => `${Math.floor(minutes / 60)}ש' ${minutes % 60}ד'`,
    stopsLabel(stops, isMax = false) {
      const label = stops === 0 ? "ישירה" : stops === 1 ? "עצירה אחת" : `${stops} עצירות`;
      return isMax && stops > 0 ? `עד ${label}` : label;
    },
    routeText(offer) {
      const hubs = offer.outbound.slice(0, -1).map((s) => s.destination);
      const last = offer.outbound.at(-1)?.destination ?? offer.destination_code;
      return [this.meta.origin, ...hubs, last].join(" → ");
    },
    trendLabel(row) {
      if (row.change_percent == null) return "—";
      const arrow = { up: "▲", down: "▼", flat: "■" }[row.trend] ?? "";
      return `${arrow} ${Math.abs(row.change_percent).toFixed(1)}%`;
    },
  };
}
