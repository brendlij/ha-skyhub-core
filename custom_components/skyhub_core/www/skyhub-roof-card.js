// Lovelace card showing the observatory roof in 3D, driven by entity state.
//
// It deliberately makes no network call of its own. The iframe this
// replaces loaded straight from SkyHub, so a dashboard opened away from
// home — where the browser can reach Home Assistant but not the Pi — showed
// nothing at all. Everything here comes from `hass`, which is already
// solved for remote access, and the roof keeps its last known position on
// screen even while SkyHub is unreachable.

const STATIC_BASE = "/skyhub_core_static";
const VIEWER_URL = `${STATIC_BASE}/skyhub-roof-3d.js`;

// The viewer is imported lazily rather than at module scope. A top-level
// import that fails aborts the whole module, so customElements.define below
// never runs and Lovelace reports "Custom element doesn't exist" — naming
// the card, which is fine, instead of the file that actually failed.
// Loading it here keeps the card registered and able to say what went wrong.
let viewerPromise = null;
function loadViewer() {
  if (!viewerPromise) viewerPromise = import(VIEWER_URL);
  return viewerPromise;
}

class SkyHubRoofCard extends HTMLElement {
  #element = null;
  #status = null;
  #lock = null;
  #entity = null;
  #title = "";
  #locked = true;
  #lastPercent = null;
  #hass = null;

  static getStubConfig(hass) {
    const cover = Object.keys(hass?.states ?? {}).find(
      (id) => id.startsWith("cover.") && hass.states[id].attributes.device_class === "shutter",
    );
    return { entity: cover ?? "cover.skyhub" };
  }

  setConfig(config) {
    if (!config?.entity || !config.entity.startsWith("cover.")) {
      throw new Error("Set `entity` to the roof cover, e.g. cover.skyhub");
    }
    this.#entity = config.entity;
    this.#title = config.title ?? "";
    // Locked by default. An unlocked scene swallows the wheel, so scrolling
    // the dashboard past the card zooms the roof instead of moving the page,
    // and a stray drag leaves the view pointing somewhere nobody chose.
    this.#locked = config.locked !== false;
    this.#render();
  }

  getCardSize() {
    return 6;
  }

  set hass(hass) {
    this.#hass = hass;
    this.#update();
  }

  #update() {
    const hass = this.#hass;
    if (!hass || !this.#element) return;
    const state = hass.states[this.#entity];

    if (!state || state.state === "unavailable") {
      // Keep the last rendered position rather than snapping the roof to
      // an arbitrary one: an unreachable controller means the position is
      // unknown, not that the roof moved.
      this.#setStatus("Roof unavailable");
      return;
    }

    const percent = state.attributes.current_position;
    if (typeof percent === "number" && percent !== this.#lastPercent) {
      this.#lastPercent = percent;
      this.#element.setAttribute("percent", String(percent));
    }

    const stale = state.attributes.position_stale === true;
    const label =
      state.state === "opening"
        ? "Opening"
        : state.state === "closing"
          ? "Closing"
          : typeof percent === "number"
            ? `${percent}% open`
            : "Position unknown";
    this.#setStatus(stale ? `${label} · uncalibrated` : label);
  }

  #setStatus(text) {
    if (this.#status && this.#status.textContent !== text) {
      this.#status.textContent = text;
    }
  }

  #applyLock() {
    if (!this.#element) return;
    // The attribute freezes OrbitControls inside the viewer; pointer-events
    // lets the page scroll normally even before the viewer has loaded.
    if (this.#locked) {
      this.#element.setAttribute("locked", "");
      this.#element.style.pointerEvents = "none";
    } else {
      this.#element.removeAttribute("locked");
      this.#element.style.pointerEvents = "auto";
    }
    if (this.#lock) {
      this.#lock.textContent = this.#locked ? "\u{1F512}" : "\u{1F513}";
      this.#lock.title = this.#locked
        ? "Unlock to orbit and zoom"
        : "Lock, so the page scrolls again";
      this.#lock.setAttribute("aria-pressed", String(!this.#locked));
      this.#lock.setAttribute(
        "aria-label",
        this.#locked ? "Unlock the 3D view" : "Lock the 3D view",
      );
    }
  }

  #render() {
    if (this.#element) return;
    const card = document.createElement("ha-card");
    if (this.#title) card.setAttribute("header", this.#title);

    const viewport = document.createElement("div");
    viewport.style.cssText = "position:relative;height:320px;overflow:hidden;border-radius:inherit";

    this.#element = document.createElement("skyhub-roof-3d");
    // Served by the integration, not from the SkyHub host — the whole
    // point of the card.
    this.#element.setAttribute("model-base", `${STATIC_BASE}/models`);
    this.#element.style.cssText = "display:block;height:100%";

    this.#status = document.createElement("span");
    this.#status.setAttribute("role", "status");
    this.#status.style.cssText =
      "position:absolute;bottom:12px;left:16px;font-size:12px;padding:4px 8px;" +
      "border-radius:4px;background:var(--card-background-color);color:var(--primary-text-color)";

    this.#lock = document.createElement("button");
    this.#lock.type = "button";
    this.#lock.style.cssText =
      "position:absolute;top:12px;right:12px;width:32px;height:32px;line-height:1;" +
      "font-size:15px;cursor:pointer;border:none;border-radius:8px;" +
      "background:var(--card-background-color);color:var(--primary-text-color);opacity:0.85";
    this.#lock.addEventListener("click", () => {
      this.#locked = !this.#locked;
      this.#applyLock();
    });

    viewport.append(this.#element, this.#status, this.#lock);
    card.append(viewport);
    this.replaceChildren(card);
    this.#applyLock();

    loadViewer().then(
      () => this.#update(),
      (error) => {
        // Name the file that failed. The card stays registered either way,
        // so the dashboard shows this rather than a missing-element message
        // pointing at the wrong thing.
        this.#setStatus(`3D viewer failed to load from ${VIEWER_URL}`);
        console.error("skyhub-roof-card: could not load the viewer", error);
      },
    );
  }
}

customElements.define("skyhub-roof-card", SkyHubRoofCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "skyhub-roof-card",
  name: "SkyHub Roof 3D",
  description: "The observatory roof in 3D, driven by the cover entity.",
  preview: false,
});
