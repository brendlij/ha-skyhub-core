// Lovelace card showing the observatory roof in 3D, driven by entity state.
//
// It deliberately makes no network call of its own. The iframe this
// replaces loaded straight from SkyHub, so a dashboard opened away from
// home — where the browser can reach Home Assistant but not the Pi — showed
// nothing at all. Everything here comes from `hass`, which is already
// solved for remote access, and the roof keeps its last known position on
// screen even while SkyHub is unreachable.

// The viewer itself, built from the same source as SkyHub's own 3D view.
// Imported statically so the element is defined before the first render;
// the integration loads this file as a module.
import "/skyhub_core_static/skyhub-roof-3d.js";

const STATIC_BASE = "/skyhub_core_static";

class SkyHubRoofCard extends HTMLElement {
  #element = null;
  #status = null;
  #entity = null;
  #title = "";
  #lastPercent = null;

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
    this.#render();
  }

  getCardSize() {
    return 6;
  }

  set hass(hass) {
    const state = hass.states[this.#entity];
    if (!this.#element) return;

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

    viewport.append(this.#element, this.#status);
    card.append(viewport);
    this.replaceChildren(card);
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
