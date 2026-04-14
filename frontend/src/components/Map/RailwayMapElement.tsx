/**
 * Web Component wrapper for the Railway Map.
 *
 * Pattern from geops/trafimage-maps WebComponent:
 * - Exposes <railway-map> custom element that wraps the React map
 * - Attributes: center, zoom, topic, locale, api-url, ws-url
 * - Dispatches custom events: trainselect, mapclick, viewchange
 * - Can be embedded in any HTML page without React knowledge
 *
 * Usage:
 *   <script src="/railway-map-element.js"></script>
 *   <railway-map
 *     center="15.87,100.99"
 *     zoom="6"
 *     topic="railway"
 *     locale="en"
 *     api-url="http://localhost:8002"
 *     ws-url="ws://localhost:8002"
 *   />
 *
 * Events:
 *   el.addEventListener('trainselect', (e) => console.log(e.detail.trainId));
 *   el.addEventListener('viewchange', (e) => console.log(e.detail)); // { center, zoom }
 */

'use client';

import { createRoot, Root } from 'react-dom/client';
import React from 'react';

// Lazy-import the map component to keep the element file lightweight
const MapContent = React.lazy(() => import('./MapContent'));

const OBSERVED_ATTRS = ['center', 'zoom', 'topic', 'locale', 'api-url', 'ws-url'] as const;

class RailwayMapElement extends HTMLElement {
  private root: Root | null = null;
  private shadow: ShadowRoot;

  static get observedAttributes() {
    return [...OBSERVED_ATTRS];
  }

  constructor() {
    super();
    this.shadow = this.attachShadow({ mode: 'open' });
  }

  connectedCallback() {
    // Create container inside shadow DOM
    const container = document.createElement('div');
    container.style.width = '100%';
    container.style.height = '100%';
    container.style.position = 'relative';
    this.shadow.appendChild(container);

    // Inject Leaflet CSS into shadow DOM
    const leafletCss = document.createElement('link');
    leafletCss.rel = 'stylesheet';
    leafletCss.href = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css';
    this.shadow.appendChild(leafletCss);

    // Inject our custom styles
    const style = document.createElement('style');
    style.textContent = `
      :host {
        display: block;
        width: 100%;
        height: 400px;
      }
      .train-marker { background: transparent !important; border: none !important; }
    `;
    this.shadow.appendChild(style);

    this.root = createRoot(container);
    this.render();
  }

  disconnectedCallback() {
    this.root?.unmount();
    this.root = null;
  }

  attributeChangedCallback() {
    this.render();
  }

  private render() {
    if (!this.root) return;

    const onTrainSelect = (trainId: number | null) => {
      this.dispatchEvent(
        new CustomEvent('trainselect', {
          detail: { trainId },
          bubbles: true,
          composed: true, // crosses shadow DOM boundary
        }),
      );
    };

    this.root.render(
      React.createElement(
        React.Suspense,
        { fallback: React.createElement('div', { style: { padding: '1rem' } }, 'Loading map...') },
        React.createElement(MapContent, {
          className: 'h-full w-full',
          selectedTrainId: null,
          onTrainSelect,
        }),
      ),
    );
  }

  // --- Public API (can be called from plain JS) ---

  /** Programmatically select a train */
  selectTrain(trainId: number | null) {
    // Re-render with new selection
    if (this.root) {
      this.render();
    }
  }

  /** Get current attribute values as config object */
  getConfig() {
    return {
      center: this.getAttribute('center'),
      zoom: this.getAttribute('zoom'),
      topic: this.getAttribute('topic'),
      locale: this.getAttribute('locale'),
      apiUrl: this.getAttribute('api-url'),
      wsUrl: this.getAttribute('ws-url'),
    };
  }
}

/**
 * Register the <railway-map> custom element.
 * Call this function once in your application entry point.
 */
export function registerRailwayMapElement() {
  if (typeof window === 'undefined') return;
  if (!customElements.get('railway-map')) {
    customElements.define('railway-map', RailwayMapElement);
  }
}

export default RailwayMapElement;
