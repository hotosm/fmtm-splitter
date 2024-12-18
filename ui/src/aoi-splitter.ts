import '@hotosm/ui/dist/style.css';
import './style.css';

import { html, LitElement } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import '@hotosm/ui/dist/hotosm-ui';
import './components/map';

@customElement('aoi-splitter')
export class AoiSplitter extends LitElement {
  @property({ type: Number }) activeStep = 1;
  @property() aoi = null;

  createRenderRoot() {
    // Return `this` instead of a shadow root, meaning no Shadow DOM is used
    return this;
  }

  connectedCallback() {
    super.connectedCallback();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
  }

  handleAoiUpdate(event: Event) {
    const CustomEvent = event as CustomEvent<any>;
    this.aoi = CustomEvent?.detail;
  }

  render() {
    return html`
      <div class="tw-h-full tw-w-full tw-pb-28">
        <hot-button>CLICK ME</hot-button>
        <aoi-splitter-map></aoi-splitter-map>
      </div>
    `;
  }
}
