import 'leaflet';

declare module 'leaflet' {
  namespace control {
    function fullscreen(options?: {
      position?: string;
      title?: string;
      titleCancel?: string;
      forceSeparateButton?: boolean;
      forcePseudoFullscreen?: boolean;
      fullscreenElement?: HTMLElement | false;
    }): L.Control;
  }
}
