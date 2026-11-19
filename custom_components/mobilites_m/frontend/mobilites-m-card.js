class MobilitesMCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity) {
      throw new Error("Vous devez définir une entité (entity)");
    }
    this.config = {
      max_passages: 4,
      ...config,
    };
  }

  set hass(hass) {
    this._hass = hass;
    const entityId = this.config.entity;
    const stateObj = hass.states[entityId];

    if (!this.content) {
      this.innerHTML = `
        <ha-card>
          <div class="card-content" id="mm-container"></div>
        </ha-card>
        <style>
          ha-card {
            padding: 16px;
            border-radius: 12px;
            cursor: pointer;
          }
          .header {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 14px;
            padding-bottom: 10px;
            border-bottom: 1px solid var(--divider-color, rgba(255,255,255,0.12));
          }
          .line-badge {
            padding: 4px 10px;
            border-radius: 8px;
            font-weight: 800;
            font-size: 1.05em;
            letter-spacing: 0.5px;
            flex-shrink: 0;
          }
          .header-text {
            display: flex;
            flex-direction: column;
            overflow: hidden;
          }
          .stop-name {
            font-weight: 700;
            font-size: 1.05em;
          }
          .dest-name {
            font-size: 0.85em;
            opacity: 0.75;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }
          .passage-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 9px 12px;
            margin-bottom: 7px;
            border-radius: 8px;
            background: var(--secondary-background-color, rgba(127,127,127,0.08));
          }
          .passage-row:last-child {
            margin-bottom: 0;
          }
          .passage-row.next {
            border-left: 4px solid var(--primary-color, #03a9f4);
          }
          .left-info {
            display: flex;
            align-items: center;
            gap: 8px;
          }
          .wait-min {
            font-size: 1.15em;
            font-weight: 700;
          }
          .rt-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #4caf50;
            display: inline-block;
            box-shadow: 0 0 6px #4caf50;
          }
          .sched-badge {
            font-size: 0.75em;
            opacity: 0.65;
          }
          .clock-time {
            font-weight: 600;
            font-size: 0.95em;
            padding: 3px 8px;
            border-radius: 6px;
            background: rgba(127,127,127,0.15);
          }
          .arrow {
            opacity: 0.5;
            margin: 0 4px;
            font-weight: normal;
          }
          .delay-tag {
            font-size: 0.78em;
            color: #ff9800;
            margin-left: 4px;
          }
          .empty {
            text-align: center;
            opacity: 0.6;
            padding: 10px 0;
            font-style: italic;
          }
        </style>
      `;
      this.content = this.querySelector("#mm-container");
      this.querySelector("ha-card").addEventListener("click", () => {
        const event = new Event("hass-more-info", { bubbles: true, composed: true });
        event.detail = { entityId };
        this.dispatchEvent(event);
      });
    }

    if (!stateObj) {
      this.content.innerHTML = `<div class="empty">Entité introuvable : ${entityId}</div>`;
      return;
    }

    const attrs = stateObj.attributes;
    const line = attrs.line || "BUS";
    const bgColor = attrs.line_color || "#0055A4";
    const txtColor = attrs.line_text_color || "#FFFFFF";
    const stopName = attrs.stop_name || stateObj.attributes.friendly_name || "";
    const destination = attrs.destination || "";
    const passages = (attrs.passages || []).slice(0, this.config.max_passages);

    let html = `
      <div class="header">
        <div class="line-badge" style="background:${bgColor}; color:${txtColor};">${line}</div>
        <div class="header-text">
          <span class="stop-name">${stopName}</span>
          <span class="dest-name">→ ${destination}</span>
        </div>
      </div>
    `;

    if (passages.length === 0) {
      html += `<div class="empty">Aucun passage à venir gg</div>`;
    } else {
      passages.forEach((p, idx) => {
        const waitLabel = p.wait_minutes === 0 ? "À l'approche" : `${p.wait_minutes} min`;
        const rtIndicator = p.realtime
          ? `<span class="rt-dot" title="Temps réel"></span>`
          : `<span class="sched-badge" title="Horaire théorique">théo.</span>`;
        const arrivalHtml = p.arrival_time
          ? `<span class="arrow">→</span><span>${p.arrival_time}</span>`
          : "";
        const delayHtml =
          p.delay_minutes > 0 ? `<span class="delay-tag">(+${p.delay_minutes}m)</span>` : "";

        html += `
          <div class="passage-row ${idx === 0 ? "next" : ""}">
            <div class="left-info">
              <span class="wait-min">${waitLabel}</span>
              ${rtIndicator}
            </div>
            <div>
              <span class="clock-time">${p.departure_time}${arrivalHtml}</span>
              ${delayHtml}
            </div>
          </div>
        `;
      });
    }

    this.content.innerHTML = html;
  }

  getCardSize() {
    return 3;
  }

  static getStubConfig(hass) {
    const mmEntity = Object.keys(hass.states).find(
      (e) => e.startsWith("sensor.") && hass.states[e].attributes.passages !== undefined
    );
    return { entity: mmEntity || "" };
  }
}

customElements.define("mobilites-m-card", MobilitesMCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "mobilites-m-card",
  name: "Mobilités M Card",
  description: "Affiche les prochains passages bus/tram TAG & SMMAG en temps réel.",
  preview: true,
});