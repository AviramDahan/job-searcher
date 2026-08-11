const els = {
  candidateName: document.querySelector("#candidateName"),
  generatedAt: document.querySelector("#generatedAt"),
  telegramState: document.querySelector("#telegramState"),
  metrics: document.querySelector("#metrics"),
  locationPolicy: document.querySelector("#locationPolicy"),
  searchInput: document.querySelector("#searchInput"),
  scoreFilter: document.querySelector("#scoreFilter"),
  sortBy: document.querySelector("#sortBy"),
  segments: [...document.querySelectorAll(".segment")],
  visibleCount: document.querySelector("#visibleCount"),
  jobList: document.querySelector("#jobList"),
  jobDetails: document.querySelector("#jobDetails"),
  toast: document.querySelector("#toast"),
};

const MANUAL_REQUIRED_STATUS = "נדרשת הגשה ידנית";
const PENDING_STATUS = "נדרש אישור";

const statusClass = new Map([
  ["הוגש", "status-submitted"],
  [MANUAL_REQUIRED_STATUS, "status-manual-required"],
  [PENDING_STATUS, "status-pending"],
  ["נפסל", "status-rejected"],
]);

const state = {
  data: null,
  selectedKey: null,
  status: "all",
  busy: false,
  enginePlans: new Map(),
  locationPreferences: { approvedLocations: {}, radiusKm: 0 },
};

const escapeHtml = (value = "") =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

function showToast(message) {
  els.toast.textContent = message;
  els.toast.hidden = false;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    els.toast.hidden = true;
  }, 3500);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok || !payload.ok) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

async function loadState() {
  const payload = await api("/api/state");
  state.data = payload.state;
  state.locationPreferences = {
    approvedLocations: payload.state.location_preferences?.approved_locations || {},
    radiusKm: Number(payload.state.location_preferences?.radius_km || 0),
  };
  if (!state.selectedKey && state.data.jobs.length > 0) {
    state.selectedKey = state.data.jobs[0].key;
  }
  render();
}

function slugifyCity(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^\p{L}\p{N}_-]+/gu, "")
    .slice(0, 80);
}

function optionTerms(option = {}) {
  const terms = Array.isArray(option.terms) ? option.terms : [];
  return [...new Set([option.label, option.key, ...terms].map((term) => String(term || "").trim()).filter(Boolean))];
}

function locationOptionByKey(key) {
  const policy = state.data?.location_policy || {};
  const options = [
    ...(policy.default_approved || []),
    ...(policy.user_approvable || []),
    ...(policy.nearby_options || []),
    ...(policy.region_options || []),
    ...(policy.map_points || []),
  ];
  const remote = state.locationPreferences.approvedLocations[key];
  return (
    options.find((option) => option.key === key) ||
    (remote
      ? {
          key: remote.key,
          label: remote.label,
          terms: remote.terms || [remote.label],
        }
      : null)
  );
}

function approvedLocationEntries() {
  return Object.values(state.locationPreferences.approvedLocations).filter((entry) => entry && entry.approved);
}

function isLocationApproved(key) {
  return Boolean(state.locationPreferences.approvedLocations[key]?.approved);
}

function isDefaultLocation(key) {
  const policy = state.data?.location_policy || {};
  return (policy.default_approved || []).some((option) => option.key === key);
}

function selectedRadiusKm() {
  return Math.max(0, Math.min(Number.parseInt(String(state.locationPreferences.radiusKm || "0"), 10) || 0, 250));
}

function homeLocation(policy = state.data?.location_policy || {}) {
  return policy.home || {};
}

function distanceKm(lat1, lng1, lat2, lng2) {
  const earthRadiusKm = 6371;
  const toRadians = (value) => (Number(value) * Math.PI) / 180;
  const dLat = toRadians(lat2 - lat1);
  const dLng = toRadians(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRadians(lat1)) * Math.cos(toRadians(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * earthRadiusKm * Math.asin(Math.sqrt(a));
}

function isPointWithinRadius(point = {}, policy = state.data?.location_policy || {}) {
  const radius = selectedRadiusKm();
  const home = homeLocation(policy);
  if (!radius || point.key === home.key) {
    return false;
  }
  const lat = Number(point.lat);
  const lng = Number(point.lng);
  const homeLat = Number(home.lat);
  const homeLng = Number(home.lng);
  if (![lat, lng, homeLat, homeLng].every(Number.isFinite)) {
    return false;
  }
  return distanceKm(homeLat, homeLng, lat, lng) <= radius + 0.001;
}

function isScannedLocation(key, point = null) {
  return isDefaultLocation(key) || isLocationApproved(key) || (point ? isPointWithinRadius(point) : false);
}

function mapPointClass(point = {}) {
  if (point.key === state.data?.location_policy?.home?.key) {
    return "home";
  }
  if (isDefaultLocation(point.key) || isLocationApproved(point.key)) {
    return "scanned";
  }
  return isPointWithinRadius(point) ? "radius" : "not-scanned";
}

async function saveLocationPreference(option, approved) {
  state.busy = true;
  render();
  try {
    const cityKey = String(option.key || slugifyCity(option.label)).trim();
    const cityLabel = String(option.label || cityKey).trim();
    const payload = await api("/api/location-preferences", {
      method: "POST",
      body: JSON.stringify({
        city_key: cityKey,
        city_label: cityLabel,
        city_terms: optionTerms({ ...option, key: cityKey, label: cityLabel }).join("|"),
        approved: approved ? "true" : "false",
      }),
    });
    state.data = payload.state;
    state.locationPreferences = {
      approvedLocations: payload.location_preferences?.approved_locations || {},
      radiusKm: Number(payload.location_preferences?.radius_km || 0),
    };
    showToast(approved ? "העיר נוספה למדיניות החיפוש" : "העיר הוסרה ממדיניות החיפוש");
    render();
  } catch (error) {
    showToast(error.message);
  } finally {
    state.busy = false;
    render();
  }
}

async function saveLocationRadius(radiusKm) {
  state.busy = true;
  render();
  try {
    const radius = Math.max(0, Math.min(Number.parseInt(String(radiusKm || "0"), 10) || 0, 250));
    const payload = await api("/api/location-radius", {
      method: "POST",
      body: JSON.stringify({ radius_km: radius }),
    });
    state.data = payload.state;
    state.locationPreferences = {
      approvedLocations: payload.location_preferences?.approved_locations || {},
      radiusKm: Number(payload.location_preferences?.radius_km || 0),
    };
    showToast(radius ? `רדיוס החיפוש עודכן ל-${radius} ק״מ` : "רדיוס החיפוש בוטל");
    render();
  } catch (error) {
    showToast(error.message);
  } finally {
    state.busy = false;
    render();
  }
}

function renderMetrics() {
  const counts = state.data.counts;
  const manualAlerts = state.data.telegram.manual_alerts;
  const retry = state.data.retry_queue;
  const items = [
    ["נסרקו", counts.scanned],
    ["תועדו", counts.documented],
    ["מתאימות", counts.suitable],
    ["הוגשו", counts.submitted],
    ["הגשה ידנית", counts.manual_required || 0],
    ["ממתינות", counts.pending],
    ["נפסלו", counts.rejected],
    ["Telegram", manualAlerts.sent || 0],
  ];

  els.metrics.innerHTML = items
    .map(([label, value]) => {
      const suffix = label === "Telegram" && retry.total ? ` · retry ${retry.total}` : "";
      return `<article class="metric"><span class="metric-value">${escapeHtml(value)}</span><span class="metric-label">${escapeHtml(label + suffix)}</span></article>`;
    })
    .join("");
}

let locationMapInitHandle = 0;
let activeLocationMap = null;

function locationMapPoints(policy = {}) {
  return (Array.isArray(policy.map_points) ? policy.map_points : []).filter(
    (point) => Number.isFinite(Number(point.lat)) && Number.isFinite(Number(point.lng))
  );
}

function locationStatusText(point = {}) {
  const pointClass = mapPointClass(point);
  if (pointClass === "not-scanned") {
    return "לא בסריקה";
  }
  if (pointClass === "radius") {
    return `בתוך רדיוס ${selectedRadiusKm()} ק״מ`;
  }
  return "בסריקה";
}

function locationMapBounds(bounds = {}) {
  return [
    [Number(bounds.min_lat ?? 29.45), Number(bounds.min_lng ?? 34.25)],
    [Number(bounds.max_lat ?? 33.35), Number(bounds.max_lng ?? 35.95)],
  ];
}

function locationMapFocusBounds(bounds = {}) {
  return [
    [Number(bounds.min_lat ?? 31.25), Number(bounds.min_lng ?? 34.42)],
    [Number(bounds.max_lat ?? 31.95), Number(bounds.max_lng ?? 34.9)],
  ];
}

function regionPolygonLatLngs(region = {}) {
  const polygon = Array.isArray(region.map_area?.polygon) ? region.map_area.polygon : [];
  return polygon
    .map((point) => [Number(point.lat), Number(point.lng)])
    .filter(([lat, lng]) => Number.isFinite(lat) && Number.isFinite(lng));
}

function activeRegionOptions(policy = state.data?.location_policy || {}) {
  return (Array.isArray(policy.region_options) ? policy.region_options : []).filter(
    (option) => isLocationApproved(option.key) && regionPolygonLatLngs(option).length >= 3
  );
}

function extendBoundsWithLatLngs(bounds, latLngs = []) {
  latLngs.forEach(([lat, lng]) => bounds.extend([lat, lng]));
  return bounds;
}

function addLocationAreaOverlays(map, policy = {}) {
  const bounds = window.L.latLngBounds(locationMapFocusBounds(policy.map?.focus_bounds || {}));
  activeRegionOptions(policy).forEach((region) => {
    const polygon = regionPolygonLatLngs(region);
    extendBoundsWithLatLngs(bounds, polygon);
    window.L.polygon(polygon, {
      className: "location-region-overlay",
      color: "#0f766e",
      fillColor: "#0f766e",
      fillOpacity: 0.14,
      opacity: 0.82,
      weight: 2,
      dashArray: "7 6",
    })
      .addTo(map)
      .bindTooltip(`אזור ${region.label}`, {
        className: "location-map-tooltip",
        direction: "center",
        opacity: 0.92,
        sticky: true,
      });
  });

  const radius = selectedRadiusKm();
  const home = homeLocation(policy);
  const homeLat = Number(home.lat);
  const homeLng = Number(home.lng);
  if (radius > 0 && Number.isFinite(homeLat) && Number.isFinite(homeLng)) {
    const circle = window.L.circle([homeLat, homeLng], {
      className: "location-radius-overlay",
      color: "#1b5d92",
      fillColor: "#1b5d92",
      fillOpacity: 0.08,
      opacity: 0.88,
      radius: radius * 1000,
      weight: 2,
      dashArray: "8 6",
    })
      .addTo(map)
      .bindTooltip(`רדיוס ${radius} ק״מ משדרות`, {
        className: "location-map-tooltip",
        direction: "center",
        opacity: 0.92,
        sticky: true,
      });
    bounds.extend(circle.getBounds().getSouthWest());
    bounds.extend(circle.getBounds().getNorthEast());
  }

  return bounds;
}

function markerIconForPoint(point = {}) {
  const pointClass = mapPointClass(point);
  const size = pointClass === "home" ? 26 : 18;
  const radiusClass = isPointWithinRadius(point) ? " in-radius" : "";
  return window.L.divIcon({
    className: `location-map-pin ${pointClass}${radiusClass}`,
    html: `<span>${pointClass === "home" ? "קורן" : ""}</span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function markerTooltip(point = {}) {
  return `
    <strong>${escapeHtml(point.label || "")}</strong>
    <span>${escapeHtml(locationStatusText(point))}</span>
  `;
}

function markerPopup(point = {}) {
  const pointClass = mapPointClass(point);
  const toggleable = pointClass !== "home" && !point.locked && !state.busy;
  const approved = isLocationApproved(point.key);
  return `
    <div class="location-map-popup" dir="rtl">
      <strong>${escapeHtml(point.label || "")}</strong>
      <span>${escapeHtml(locationStatusText(point))}</span>
      ${
        toggleable
          ? `<button type="button" class="map-popup-button" data-location-action="toggle" data-location-key="${escapeHtml(point.key)}">${
              approved ? "הסר מהסריקה" : "הוסף לסריקה"
            }</button>`
          : ""
      }
    </div>
  `;
}

function bindMapViewButtons(panel, map, policy = {}) {
  const israelBounds = locationMapBounds(policy.map?.bounds || {});
  const focusBounds = locationMapFocusBounds(policy.map?.focus_bounds || {});
  panel.querySelectorAll("[data-map-view]").forEach((button) => {
    button.addEventListener("click", () => {
      const view = button.dataset.mapView;
      panel.querySelectorAll("[data-map-view]").forEach((item) => item.classList.toggle("active", item === button));
      map.fitBounds(view === "israel" ? israelBounds : focusBounds, {
        padding: [28, 28],
        maxZoom: view === "israel" ? 8 : 11,
      });
    });
  });
}

function initializeLocationMap() {
  const panel = els.locationPolicy?.querySelector(".location-map-panel");
  const canvas = panel?.querySelector("[data-location-map-canvas]");
  if (!panel || !canvas || !state.data?.location_policy) {
    return;
  }

  const policy = state.data.location_policy;
  const points = locationMapPoints(policy);
  if (!window.L || points.length === 0) {
    panel.classList.add("map-unavailable");
    return;
  }

  if (activeLocationMap) {
    activeLocationMap.remove();
    activeLocationMap = null;
  }

  canvas.replaceChildren();
  const map = window.L.map(canvas, {
    attributionControl: true,
    scrollWheelZoom: false,
    zoomControl: true,
  });
  map.setView([31.52, 34.63], 9);

  window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  const overlayBounds = addLocationAreaOverlays(map, policy);
  const hasActiveRegionOverlay = activeRegionOptions(policy).length > 0;
  const hasRadiusOverlay = selectedRadiusKm() > 0;
  const markerLayer = window.L.markerClusterGroup
    ? window.L.markerClusterGroup({
        showCoverageOnHover: false,
        spiderfyOnMaxZoom: true,
        disableClusteringAtZoom: hasRadiusOverlay ? 9 : 12,
        maxClusterRadius: hasRadiusOverlay ? 22 : 34,
        iconCreateFunction(cluster) {
          const childMarkers = cluster.getAllChildMarkers();
          const states = childMarkers.map((marker) => marker.options.scanState);
          const activeStates = new Set(["scanned", "radius"]);
          const clusterState = states.every((stateName) => stateName === "scanned")
            ? "scanned"
            : states.every((stateName) => stateName === "radius")
              ? "radius"
              : states.every((stateName) => activeStates.has(stateName))
                ? "scanned"
            : states.every((stateName) => stateName === "not-scanned")
              ? "not-scanned"
              : "mixed";
          const radiusClass = childMarkers.some((marker) => marker.options.withinRadius) ? " in-radius" : "";
          return window.L.divIcon({
            html: `<span>${cluster.getChildCount()}</span>`,
            className: `location-marker-cluster ${clusterState}${radiusClass}`,
            iconSize: window.L.point(38, 38),
          });
        },
      })
    : window.L.layerGroup();

  points.forEach((point) => {
    const pointClass = mapPointClass(point);
    const marker = window.L.marker([Number(point.lat), Number(point.lng)], {
      icon: markerIconForPoint(point),
      keyboard: false,
      scanState: pointClass,
      withinRadius: isPointWithinRadius(point, policy),
      title: `${point.label} - ${locationStatusText(point)}`,
    })
      .bindTooltip(markerTooltip(point), {
        className: "location-map-tooltip",
        direction: "top",
        offset: [0, -12],
        opacity: 0.96,
      })
      .bindPopup(markerPopup(point), {
        className: "location-map-popup-shell",
        closeButton: true,
        minWidth: 170,
      });
    markerLayer.addLayer(marker);
  });

  markerLayer.addTo(map);
  map.fitBounds(overlayBounds, { padding: [28, 28], maxZoom: hasActiveRegionOverlay ? 8 : hasRadiusOverlay ? 10 : 11 });
  bindMapViewButtons(panel, map, policy);
  activeLocationMap = map;
  requestAnimationFrame(() => map.invalidateSize());
}

function scheduleLocationMapInit() {
  if (locationMapInitHandle) {
    cancelAnimationFrame(locationMapInitHandle);
  }
  locationMapInitHandle = requestAnimationFrame(() => {
    initializeLocationMap();
  });
}

function renderLocationMap(policy = {}) {
  const points = locationMapPoints(policy);
  const scannedCount = points.filter((point) => isScannedLocation(point.key, point)).length;
  const radius = selectedRadiusKm();
  const radiusCount = radius ? points.filter((point) => isPointWithinRadius(point, policy)).length : 0;
  const nearbyCount = (policy.nearby_options || []).length;
  const regionOptions = Array.isArray(policy.region_options) ? policy.region_options : [];
  const radiusOptions = Array.isArray(policy.radius_options_km) ? policy.radius_options_km : [25, 40, 60, 80, 100, 150];
  const disabled = state.busy ? " disabled" : "";
  const regionChips = regionOptions
    .map((option) => {
      const approved = isLocationApproved(option.key);
      return `
        <button type="button" class="region-chip${approved ? " approved" : ""}" data-location-action="toggle" data-location-key="${escapeHtml(
          option.key
        )}" aria-pressed="${approved ? "true" : "false"}"${disabled}>${escapeHtml(option.label)}</button>
      `;
    })
    .join("");
  const radiusOptionsHtml = [
    `<option value="0"${radius === 0 ? " selected" : ""}>ללא רדיוס</option>`,
    ...radiusOptions.map((value) => `<option value="${escapeHtml(value)}"${radius === Number(value) ? " selected" : ""}>${escapeHtml(value)} ק״מ</option>`),
  ].join("");

  return `
    <section class="location-map-panel" aria-label="מפת מיקומים">
      <div class="location-map-stage">
        <div class="map-canvas leaflet-map" data-location-map-canvas></div>
        <div class="map-fallback">
          <strong>המפה לא נטענה</strong>
          <span>רשימת המיקומים זמינה למטה.</span>
        </div>
      </div>
      <aside class="map-side" aria-label="מקרא מפה">
        <div class="map-toolbar" aria-label="תצוגת מפה">
          <button type="button" class="map-view-button active" data-map-view="sderot">אזור שדרות</button>
          <button type="button" class="map-view-button" data-map-view="israel">ישראל</button>
        </div>
        <div class="map-legend">
          <span><i class="legend-dot home"></i>קורן - שדרות</span>
          <span><i class="legend-dot scanned"></i>בסריקה</span>
          <span><i class="legend-dot radius"></i>בתוך רדיוס</span>
          <span><i class="legend-dot not-scanned"></i>לא בסריקה</span>
        </div>
        <div class="map-region-panel" aria-label="אזורי סריקה">
          ${regionChips}
        </div>
        <label class="map-radius-control">
          <span>רדיוס משדרות</span>
          <select data-location-action="radius"${disabled}>
            ${radiusOptionsHtml}
          </select>
        </label>
        <div class="map-summary-grid" aria-label="סיכום מיקומים במפה">
          <span><strong>${escapeHtml(scannedCount)}</strong><small>במדיניות הסריקה</small></span>
          <span><strong>${escapeHtml(points.length - scannedCount)}</strong><small>לא מסומנים</small></span>
          ${
            radius
              ? `<span><strong>${escapeHtml(radiusCount)}</strong><small>בתוך ${escapeHtml(radius)} ק״מ משדרות</small></span>`
              : ""
          }
          <span><strong>${escapeHtml(nearbyCount)}</strong><small>יישובים סביב שדרות</small></span>
        </div>
      </aside>
    </section>
  `;
}

function renderLocationPolicy() {
  if (!els.locationPolicy || !state.data) {
    return;
  }

  const policy = state.data.location_policy || {};
  const defaultApproved = Array.isArray(policy.default_approved) ? policy.default_approved : [];
  const userApprovable = Array.isArray(policy.user_approvable) ? policy.user_approvable : [];
  const nearbyOptions = Array.isArray(policy.nearby_options) ? policy.nearby_options : [];
  const regionOptions = Array.isArray(policy.region_options) ? policy.region_options : [];
  const knownKeys = new Set([...defaultApproved, ...userApprovable, ...nearbyOptions, ...regionOptions].map((option) => option.key));
  const customApproved = approvedLocationEntries().filter((entry) => !knownKeys.has(entry.key));
  const disabled = state.busy ? " disabled" : "";

  const defaultChips = defaultApproved
    .map((option) => `<span class="city-chip locked">${escapeHtml(option.label)}</span>`)
    .join("");
  const optionalChips = userApprovable
    .map((option) => {
      const approved = isLocationApproved(option.key);
      return `
        <button type="button" class="city-chip toggle${approved ? " approved" : ""}" data-location-action="toggle" data-location-key="${escapeHtml(
        option.key
      )}" aria-pressed="${approved ? "true" : "false"}"${disabled}>${escapeHtml(option.label)}</button>
      `;
    })
    .join("");
  const nearbyChips = nearbyOptions
    .map((option) => {
      const approved = isLocationApproved(option.key);
      return `
        <button type="button" class="city-chip toggle nearby${approved ? " approved" : ""}" data-location-action="toggle" data-location-key="${escapeHtml(
        option.key
      )}" aria-pressed="${approved ? "true" : "false"}"${disabled}>${escapeHtml(option.label)}</button>
      `;
    })
    .join("");
  const customChips = customApproved
    .map(
      (entry) =>
        `<button type="button" class="city-chip toggle approved custom" data-location-action="toggle" data-location-key="${escapeHtml(
          entry.key
        )}" aria-pressed="true"${disabled}>${escapeHtml(entry.label)}</button>`
    )
    .join("");

  els.locationPolicy.innerHTML = `
    <div class="location-head">
      <div>
        <p class="eyebrow">מדיניות מיקום</p>
        <h2>ערי חיפוש מאושרות</h2>
      </div>
      <span class="state-pill ready">${escapeHtml(defaultApproved.length + approvedLocationEntries().length)} מיקומים מאושרים</span>
    </div>
    ${renderLocationMap(policy)}
    <div class="location-groups">
      <section class="location-group">
        <h3>ברירת מחדל</h3>
        <div class="city-grid">${defaultChips}</div>
      </section>
      <section class="location-group">
        <h3>בחירה</h3>
        <div class="city-grid">${optionalChips}</div>
      </section>
      <section class="location-group wide">
        <h3>יישובים וקיבוצים סביב שדרות</h3>
        <div class="city-grid">${nearbyChips}${customChips}</div>
      </section>
      <form class="custom-city-form" data-location-action="custom">
        <label class="search-box" for="customCityInput">
          <span>עיר נוספת</span>
          <input id="customCityInput" name="city" type="text" autocomplete="off" maxlength="80" />
        </label>
        <button type="submit" class="action-button primary"${disabled}>הוסף</button>
      </form>
    </div>
  `;
  scheduleLocationMapInit();
}

function currentJobs() {
  const query = els.searchInput.value.trim().toLowerCase();
  const minScore = Number(els.scoreFilter.value || 0);
  const selectedStatus = state.status;

  const filtered = state.data.jobs.filter((job) => {
    const matchesStatus = selectedStatus === "all" || job.status === selectedStatus;
    const matchesScore = Number(job.score || 0) >= minScore;
    const haystack = [job.company, job.title, job.location, job.link, job.requirements, job.fit, job.stop_reason]
      .join(" ")
      .toLowerCase();
    return matchesStatus && matchesScore && haystack.includes(query);
  });

  const sortBy = els.sortBy.value;
  filtered.sort((a, b) => {
    if (sortBy === "date") {
      return String(b.date || "").localeCompare(String(a.date || ""));
    }
    if (sortBy === "company") {
      return String(a.company || "").localeCompare(String(b.company || ""), "he");
    }
    return Number(b.score || 0) - Number(a.score || 0);
  });

  return filtered;
}

function renderJobs() {
  const jobs = currentJobs();
  els.visibleCount.textContent = `${jobs.length} מוצגות`;
  if (!jobs.some((job) => job.key === state.selectedKey)) {
    state.selectedKey = jobs[0]?.key || null;
  }

  if (jobs.length === 0) {
    els.jobList.innerHTML = `<div class="empty-state">אין משרות להצגה</div>`;
    return;
  }

  els.jobList.innerHTML = jobs
    .map((job) => {
      const selected = job.key === state.selectedKey ? " selected" : "";
      const pillClass = statusClass.get(job.status) || "";
      return `
        <button type="button" class="job-row${selected}" data-key="${escapeHtml(job.key)}">
          <span class="score-badge">${escapeHtml(job.score)}</span>
          <span class="job-main">
            <span class="job-title">${escapeHtml(job.title)}</span>
            <span class="job-company">${escapeHtml(job.company)}</span>
            <span class="job-location">${escapeHtml(job.location || "ללא מיקום")}</span>
          </span>
          <span class="status-pill ${pillClass}">${escapeHtml(job.status || "ללא סטטוס")}</span>
        </button>
      `;
    })
    .join("");
}

function textBlock(label, value) {
  const clean = String(value || "").trim();
  const body = clean
    ? `<p class="detail-text">${escapeHtml(clean)}</p>`
    : `<p class="detail-text empty">אין נתון</p>`;
  return `<section class="detail-section"><h3>${escapeHtml(label)}</h3>${body}</section>`;
}

function renderDetails() {
  const job = state.data.jobs.find((item) => item.key === state.selectedKey);
  if (!job) {
    els.jobDetails.innerHTML = `<div class="empty-state">אין משרה נבחרת</div>`;
    return;
  }

  const pillClass = statusClass.get(job.status) || "";
  const telegramDisabled = !state.data.telegram.configured || state.busy ? "disabled" : "";
  const actionDisabled = state.busy ? "disabled" : "";
  const enginePlan = state.enginePlans.get(job.key);
  const engineSection = enginePlan
    ? `
      <section class="detail-section engine-result">
        <h3>בדיקת מנוע</h3>
        <div class="engine-grid">
          <span>אתר</span><strong>${escapeHtml(enginePlan.site)}</strong>
          <span>החלטה</span><strong>${escapeHtml(enginePlan.decision)}</strong>
          <span>פעולה</span><strong>${escapeHtml(enginePlan.action)}</strong>
          <span>ניתן לנסות</span><strong>${enginePlan.can_attempt ? "כן" : "לא"}</strong>
        </div>
        <p class="detail-text">${escapeHtml(enginePlan.reason)}</p>
        <p class="detail-text">${escapeHtml(enginePlan.next_step)}</p>
      </section>
    `
    : "";

  els.jobDetails.innerHTML = `
    <div class="details-inner">
      <header class="details-head">
        <div class="details-title-line">
          <div>
            <h2 class="details-title">${escapeHtml(job.title)}</h2>
            <p class="details-company">${escapeHtml(job.company)}</p>
          </div>
          <span class="score-badge">${escapeHtml(job.score)}</span>
        </div>
        <div class="quick-facts">
          <span class="status-pill ${pillClass}">${escapeHtml(job.status || "ללא סטטוס")}</span>
          <span class="fact">${escapeHtml(job.location || "ללא מיקום")}</span>
          <span class="fact">${escapeHtml(job.date || "ללא תאריך")}</span>
          <span class="fact">${escapeHtml(job.cv || "ללא CV")}</span>
        </div>
        <div class="actions">
          <a class="link-button" href="${escapeHtml(job.link)}" target="_blank" rel="noreferrer">פתח משרה</a>
          <button type="button" class="action-button primary" data-action="telegram" ${telegramDisabled}>שלח לטלגרם</button>
          <button type="button" class="action-button" data-action="engine_plan" ${actionDisabled}>בדיקת מנוע</button>
          <button type="button" class="action-button" data-action="mark_submitted" ${actionDisabled}>סמן כהוגש ידנית</button>
          <button type="button" class="action-button danger" data-action="mark_rejected" ${actionDisabled}>סמן כנפסל</button>
        </div>
      </header>

      ${engineSection}
      ${textBlock("דרישות מרכזיות", job.requirements)}
      ${textBlock("סיבות התאמה", job.fit)}
      ${textBlock("סיבת עצירה או פסילה", job.stop_reason)}
      ${textBlock("נוסח פנייה", job.cover)}
      ${textBlock("שלב הבא", job.next_step)}

      <section class="detail-section note-form">
        <h3>הערת מעקב</h3>
        <textarea id="noteInput" placeholder="הערה פנימית"></textarea>
        <div class="note-row">
          <input id="cvInput" type="text" value="${escapeHtml(job.cv || "")}" placeholder="שם קובץ CV" />
          <button type="button" class="action-button warning" data-action="add_note" ${actionDisabled}>שמור הערה</button>
        </div>
      </section>
    </div>
  `;
}

function renderChrome() {
  els.candidateName.textContent = `${state.data.candidate.full_name} · ניהול מועמדויות`;
  els.generatedAt.textContent = `עודכן: ${state.data.generated_at}`;
  els.telegramState.textContent = state.data.telegram.configured ? "Telegram מחובר" : "Telegram לא מוגדר";
  els.telegramState.classList.toggle("ready", state.data.telegram.configured);
  els.telegramState.classList.toggle("missing", !state.data.telegram.configured);
}

function render() {
  if (!state.data) {
    return;
  }
  renderChrome();
  renderMetrics();
  renderLocationPolicy();
  renderJobs();
  renderDetails();
}

async function updateJob(action) {
  const note = document.querySelector("#noteInput")?.value || "";
  const cvFilename = document.querySelector("#cvInput")?.value || "";
  state.busy = true;
  renderDetails();
  try {
    const payload = await api("/api/jobs/update", {
      method: "POST",
      body: JSON.stringify({ key: state.selectedKey, action, note, cv_filename: cvFilename }),
    });
    state.data = payload.state;
    state.selectedKey = payload.job.key;
    showToast("עודכן");
    render();
  } catch (error) {
    showToast(error.message);
  } finally {
    state.busy = false;
    renderDetails();
  }
}

async function sendTelegram() {
  state.busy = true;
  renderDetails();
  try {
    await api("/api/jobs/telegram", {
      method: "POST",
      body: JSON.stringify({ key: state.selectedKey }),
    });
    showToast("נשלחה התראה לטלגרם");
  } catch (error) {
    showToast(error.message);
  } finally {
    state.busy = false;
    renderDetails();
  }
}

async function runEnginePlan() {
  state.busy = true;
  renderDetails();
  try {
    const payload = await api("/api/jobs/engine-plan", {
      method: "POST",
      body: JSON.stringify({ key: state.selectedKey }),
    });
    state.enginePlans.set(state.selectedKey, payload.engine.plan);
    showToast("בדיקת המנוע מוכנה");
  } catch (error) {
    showToast(error.message);
  } finally {
    state.busy = false;
    renderDetails();
  }
}

els.jobList.addEventListener("click", (event) => {
  const row = event.target.closest(".job-row");
  if (!row) {
    return;
  }
  state.selectedKey = row.dataset.key;
  render();
});

els.jobDetails.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) {
    return;
  }
  const action = button.dataset.action;
  if (action === "telegram") {
    sendTelegram();
  } else if (action === "engine_plan") {
    runEnginePlan();
  } else {
    updateJob(action);
  }
});

els.locationPolicy?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-location-action='toggle']");
  if (!button) {
    return;
  }
  const key = button.dataset.locationKey;
  const option = locationOptionByKey(key);
  if (!option) {
    showToast("לא נמצאו פרטי עיר לעדכון");
    return;
  }
  void saveLocationPreference(option, !isLocationApproved(key));
});

els.locationPolicy?.addEventListener("keydown", (event) => {
  if (!["Enter", " "].includes(event.key)) {
    return;
  }
  const button = event.target.closest("[data-location-action='toggle']");
  if (!button) {
    return;
  }
  event.preventDefault();
  const key = button.dataset.locationKey;
  const option = locationOptionByKey(key);
  if (!option) {
    showToast("לא נמצאו פרטי עיר לעדכון");
    return;
  }
  void saveLocationPreference(option, !isLocationApproved(key));
});

els.locationPolicy?.addEventListener("change", (event) => {
  const select = event.target.closest("[data-location-action='radius']");
  if (!select) {
    return;
  }
  void saveLocationRadius(select.value);
});

els.locationPolicy?.addEventListener("submit", (event) => {
  const form = event.target.closest("[data-location-action='custom']");
  if (!form) {
    return;
  }
  event.preventDefault();
  const input = form.querySelector("input[name='city']");
  const label = String(input?.value || "").trim();
  const key = `custom_${slugifyCity(label)}`;
  if (!label || key === "custom_") {
    showToast("יש להזין שם עיר");
    return;
  }
  if (input) {
    input.value = "";
  }
  void saveLocationPreference({ key, label, terms: [label] }, true);
});

els.searchInput.addEventListener("input", render);
els.scoreFilter.addEventListener("change", render);
els.sortBy.addEventListener("change", render);
els.segments.forEach((button) => {
  button.addEventListener("click", () => {
    state.status = button.dataset.status;
    els.segments.forEach((item) => item.classList.toggle("active", item === button));
    render();
  });
});

loadState().catch((error) => {
  showToast(error.message);
});
