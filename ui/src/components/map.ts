import '@openlayers-elements/core/ol-map.js'
import '@openlayers-elements/maps/ol-layer-openstreetmap.js'

import { css, html, LitElement } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import { Map as OlMapInstance } from 'ol';
import VectorSource from 'ol/source/Vector';
import VectorLayer from 'ol/layer/Vector';
import { Style, Icon } from 'ol/style';
import GeoTIFF from 'ol/source/GeoTIFF';
// import { GeoJSON } from 'ol/format';
import type { GeoJSON, FeatureCollection } from 'geojson'

@customElement('aoi-splitter-map')
export class MapSection extends LitElement {
  @property({ type: Object }) aoiGeojson: GeoJSON;
  @property({ type: Object }) splitAreasGeojson: FeatureCollection;

  private map!: OlMapInstance;

  static styles = css`
    :host {
      display: block;
      padding: 10px;
    }
    #map-container {
      display: flex;
      height: 80vh;
      width: 100%;
      border-radius: 8px;
      overflow: hidden;
      position: relative;
    }
  `;

  firstUpdated(): void {
    // const mapEl: OlMap = this.renderRoot.querySelector('ol-map#aoi-splitter-map')!;
    // mapEl?.updateComplete?.then(() => {
    //   this.map = mapEl.map!;
    //   // do stuff
    // });
  }

  protected render() {
    return html`
      <div id="map-container">
        <ol-map id="aoi-splitter-map">
            <ol-layer-openstreetmap></ol-layer-openstreetmap>
        </ol-map>
      </div>
    `;
  }
}
