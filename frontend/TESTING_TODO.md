# Frontend Testing — Deferred TODOs

## Unit Tests (Jest + @testing-library/react)
- [ ] Test `useDarkMode` hook: toggle, persistence in localStorage
- [ ] Test `useTrainPositions` hook: WebSocket message handling, position updates
- [ ] Test `getDelayColor()`: threshold mapping (green/yellow/orange/red)
- [ ] Test `LanguageSwitcher`: locale toggle, cookie persistence
- [ ] Test `TrainInfoPanel`: filtering, search, train selection

## E2E Tests (Cypress)
- [ ] Install Cypress: `npm install -D cypress`
- [ ] Map load: verify tiles render, stations appear
- [ ] Train markers: verify delay badge colors
- [ ] Permalink: navigate to `?lat=13.7&lng=100.5&z=10&train=42`, verify map state
- [ ] Language switch: click TH button, verify Thai text appears
- [ ] Mobile responsive: test panel overlays on small viewport
- [ ] WebSocket mock: use `mock-socket` or `cy.intercept` for WS testing

## Performance Tests
- [ ] Lighthouse CI: add to GitHub Actions for Core Web Vitals monitoring
- [ ] Bundle analysis: verify react-leaflet-cluster doesn't bloat bundle excessively
