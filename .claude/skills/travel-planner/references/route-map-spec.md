# Route Map Spec

Full Leaflet implementation spec for the route map artifact.
Derived from a working Colombia route map. Apply this pattern exactly.

---

## Page structure

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>[Country] Route Map — [Traveler names] [Year]</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"/>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet-polylinedecorator/1.6.0/leaflet.polylineDecorator.min.js"></script>
<style>/* inline CSS */</style>
</head>
<body>
<div id="header">...</div>
<div id="map"></div>
<div id="legend">...</div>
<script>/* all map logic */</script>
</body>
</html>
```

---

## CSS layout

```css
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0ede8; }

#header { padding: 14px 18px 10px; background: #fff; border-bottom: 1px solid #e0ddd5; }
#header h1 { font-size: 16px; font-weight: 600; color: #1a1a1a; }
#header p  { font-size: 12px; color: #777; margin-top: 2px; }
/* Header meta line format: "Traveler names · Start–End date · N nights · Exit FLIGHT CODES ROUTE"
   Example: "Cosmin & Georgiana · Mar 21–Apr 11 · 21 nights · Exit AV8505+AV159 SMR→MDE→UIO"
   Omit the exit segment if no exit flight is booked yet. */

#map { width: 100%; height: calc(100vh - 104px); }  /* fills viewport between header and legend */

#legend {
  display: flex; flex-wrap: wrap; gap: 10px; padding: 8px 18px;
  background: #fff; border-top: 1px solid #e0ddd5;
  font-size: 11px; color: #555; align-items: center;
}
.li { display: flex; align-items: center; gap: 4px; }
.dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
.line { width: 26px; height: 3px; border-radius: 2px; display: inline-block; }
.badge { color: #fff; font-size: 8.5px; font-weight: 700; padding: 1px 5px; border-radius: 3px; }
```

---

## Transport mode colors

```js
const modeColors = {
  FLY:      '#1d4ed8',  // blue
  BUS:      '#b45309',  // amber
  WILLY:    '#b45309',  // amber (jeep/colectivo — same as BUS)
  BOAT:     '#0891b2',  // teal
  TAXI:     '#6b7280',  // grey
  TRANSFER: '#16a34a',  // green (pre-booked private)
  METRO:    '#7c3aed',  // purple
  WALK:     '#9ca3af',  // light grey
};
```

Day trip arcs always use `#9333ea` (purple), dashed.

---

## Location data model

```js
const N = {
  // KEY: [lat, lng]
  BOG: [4.711, -74.072],
  MDE: [6.244, -75.581],
  // etc.
};
```

Use 3-letter IATA codes or short alphanumeric keys. Look up approximate
coordinates for cities — exact precision not required (within 0.1° is fine).

---

## Core helper functions

### `mid()` — midpoint with offset for label placement

```js
function mid(a, b, dlat, dlon) {
  return [(a[0]+b[0])/2 + (dlat||0), (a[1]+b[1])/2 + (dlon||0)];
}
```

Adjust `dlat`/`dlon` to push labels away from overlapping arcs.

### `drawArc()` — polyline with optional arrowhead

```js
function drawArc(pts, color, weight, dash, arrowOffset) {
  const pl = L.polyline(pts, { color, weight, opacity: 0.82, dashArray: dash }).addTo(map);
  if (L.Symbol && L.Symbol.arrowHead) {
    L.polylineDecorator(pl, { patterns: [{
      offset: arrowOffset || '55%', repeat: 0,
      symbol: L.Symbol.arrowHead({
        pixelSize: 12, polygon: false,
        pathOptions: { stroke: true, color, weight: 2.5, opacity: 0.9 }
      })
    }]}).addTo(map);
  }
  return pl;
}
```

Parameters: `pts` = array of `[lat,lng]`, `dash` = dashArray string or null, `arrowOffset` = '55%' default.

### `arcLabel()` — mode + distance/time label at a point

```js
function arcLabel(mode, dist, time, lat, lon) {
  const c = modeColors[mode] || '#374151';
  L.marker([lat, lon], {
    icon: L.divIcon({
      className: '',
      html: `<div style="transform:translate(-50%,-50%);display:inline-flex;align-items:center;gap:3px;white-space:nowrap;pointer-events:none;">
        <span style="background:${c};color:#fff;font-size:8px;font-weight:700;padding:1px 4px;border-radius:3px;">${mode}</span>
        <span style="background:rgba(255,255,255,0.96);color:#222;font-size:9px;font-weight:600;padding:1px 5px;border-radius:3px;border:.5px solid #bbb;">${dist} &middot; ${time}</span>
      </div>`,
      iconSize: [0,0], iconAnchor: [0,0]
    }), interactive: false
  }).addTo(map);
}
```

Call like: `arcLabel('FLY', '~520km', '1h', ...mid(N.MDE, N.CTG, 0.05, 0.22))`

---

## Drawing arcs

### Main route arcs (solid, one direction)

```js
drawArc([N.BOG, N.MDE], modeColors.FLY, 3.5);
arcLabel('FLY', '~500km', '1h', ...mid(N.BOG, N.MDE, 0.1, 0.1));
```

For return/transfer legs (slightly offset arrow):
```js
drawArc([N.SAL, N.PEI], modeColors.TRANSFER, 3.5, null, '45%');
arcLabel('TRANSFER', '~44km', '1h15m', offsetLat, offsetLon);
```

### Day trip arcs (dashed, bidirectional)

```js
// Both directions to show round trip
drawArc([N.MDE, N.GUA], '#9333ea', 2, '7,5', '75%');
drawArc([N.GUA, N.MDE], '#9333ea', 2, '7,5', '75%');
arcLabel('BUS', '~80km', '2h ea.', ...mid(N.MDE, N.GUA, 0.1, 0.05));
```

---

## Base markers (numbered circles)

```js
[
  { key:'BOG', num:'1', color:'#374151', name:'Bogotá',
    info:'<b>① Mar 21–24 · 3 nights</b><br>WiFi: Excellent<br>Chapinero / Zona G<br>Day 1: rest. Day 2: museums. Day 3: day trip.' },
  // ...
].forEach(n => {
  L.marker(N[n.key], {
    icon: L.divIcon({
      className: '',
      html: `<div style="background:${n.color};color:#fff;border-radius:50%;width:34px;height:34px;display:flex;align-items:center;justify-content:center;font-size:10.5px;font-weight:700;border:2.5px solid #fff;box-shadow:0 2px 7px rgba(0,0,0,.4);line-height:1;">${n.num}</div>`,
      iconSize: [34,34], iconAnchor: [17,17]
    }), zIndexOffset: 1000
  }).addTo(map).bindPopup(
    `<b style="font-size:13px;">${n.name}</b><br><span style="font-size:11px;color:#444;line-height:1.8;">${n.info}</span>`,
    { maxWidth: 260 }
  );
});
```

Popup `info` format:
```
<b>① Mar 21–24 · 3 nights</b><br>
WiFi: Excellent<br>
Neighborhood / sector<br>
2-3 key logistics or activity notes
```

---

## Day trip markers (purple pills)

```js
[
  { key:'GUA', name:'Guatapé', info:'Day trip from Medellín · BUS ~80km · 2h each way<br>El Peñón 740 steps. Book agency.' },
  // ...
].forEach(n => {
  L.marker(N[n.key], {
    icon: L.divIcon({
      className: '',
      html: `<div style="background:#9333ea;color:#fff;border-radius:5px;padding:2px 8px;font-size:9.5px;font-weight:700;border:2px solid #fff;box-shadow:0 1px 5px rgba(0,0,0,.3);white-space:nowrap;transform:translate(10px,-50%);">${n.name}</div>`,
      iconSize: [0,0], iconAnchor: [0,0]
    })
  }).addTo(map).bindPopup(
    `<b>${n.name}</b><br><span style="font-size:11px;color:#555;line-height:1.7;">${n.info}</span>`,
    { maxWidth: 240 }
  );
});
```

---

## Signal / WiFi zones

```js
// Red — fully offline inside this area
L.circle(N.TAY, { radius: 9000, color:'rgba(239,68,68,0.65)', fillColor:'rgba(239,68,68,0.18)', fillOpacity:1, weight:1.5 })
  .addTo(map).bindTooltip('Location name — fully offline inside');

// Orange — variable WiFi, confirm before booking
L.circle(N.PEI, { radius: 30000, color:'rgba(251,146,60,0.5)', fillColor:'rgba(251,146,60,0.1)', fillOpacity:1, weight:1.5 })
  .addTo(map).bindTooltip('Location name — WiFi varies. Always confirm before booking.');
```

Radius in meters. Match to real geographic extent of the area.

---

## Legend HTML

```html
<div id="legend">
  <div class="li"><span class="line" style="background:#1d4ed8;"></span><span class="badge" style="background:#1d4ed8;">FLY</span> flight</div>
  <div class="li"><span class="line" style="background:#b45309;"></span><span class="badge" style="background:#b45309;">BUS</span> bus / coach</div>
  <div class="li"><span class="line" style="background:#b45309;"></span><span class="badge" style="background:#b45309;">WILLY</span> jeep colectivo</div>
  <div class="li"><span class="line" style="background:#16a34a;"></span><span class="badge" style="background:#16a34a;">TRANSFER</span> pre-booked transfer</div>
  <div class="li"><span class="line" style="background:#0891b2;"></span><span class="badge" style="background:#0891b2;">BOAT</span> boat / ferry</div>
  <div class="li"><span class="line" style="background:#6b7280;"></span><span class="badge" style="background:#6b7280;">TAXI</span> taxi / Uber</div>
  <div class="li"><span style="width:26px;height:0;border-top:2.5px dashed #9333ea;display:inline-block;"></span><span class="badge" style="background:#9333ea;">DAY TRIP</span> round trip</div>
  <div class="li"><span class="dot" style="background:rgba(239,68,68,0.3);border:1.5px solid rgba(239,68,68,0.7);"></span> No signal</div>
  <div class="li"><span class="dot" style="background:rgba(251,146,60,0.3);border:1.5px solid rgba(251,146,60,0.6);"></span> Variable signal</div>
</div>
```

Only include legend items for modes actually used in this map.

---

## Map initialization

```js
const map = L.map('map', { zoomControl: true });
map.fitBounds([[southLat, westLon], [northLat, eastLon]]);

L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}', {
  attribution: 'Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ, TomTom, and the GIS community',
  maxZoom: 18
}).addTo(map);
```

Set `fitBounds` to a rectangle that contains all markers with some padding.
Never hardcode a center coordinate — always derive from the data.
