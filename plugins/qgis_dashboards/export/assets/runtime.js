/* QGIS Dashboard — exported runtime.
 *
 * Vanilla JS, no dependencies. Reads the embedded JSON model and reproduces the
 * dashboard offline, including live cross-filtering. The filter/aggregation
 * logic is a direct port of the plugin's bus.py / chart.py / pivot_engine.py so
 * behavior matches the live dashboard. Charts are hand-drawn inline SVG.
 */
(function () {
  "use strict";

  var DATA = JSON.parse(document.getElementById("dashboard-data").textContent);
  var THEME = DATA.theme || {};
  var DEFAULT_SERIES = ["#2b7de9", "#13a10e", "#c19c00", "#d13438", "#8764b8",
    "#00b7c3", "#ca5010", "#498205", "#a4262c", "#5c2e91"];
  var SERIES = (THEME.series && THEME.series.length) ? THEME.series : DEFAULT_SERIES;
  // global element gap (logical px): each card is inset by this much inside its
  // footprint, mirroring the desktop's GridTile inset. The output can't be
  // re-dragged, so this is the only way the export reflects the spacing.
  var GAP = Math.max(0, Number(DATA.gap || 0));
  var NULL_KEY = "(null)";
  var SEP = String.fromCharCode(1);   // composite (row, col) cell-key separator

  var ELEMENT_LABELS = {
    indicator: "Indicator", chart: "Chart", pivot: "Pivot / matrix",
    list: "List", map: "Map", category_selector: "Category selector",
    text: "Text", image: "Image"
  };
  var FULL_BLEED = { map: true, image: true };

  // Mirror of elements/chart_specs.CHART_SPECS. ``shape`` defaults to
  // "category"; the non-category shapes drive aggregation + painter dispatch
  // in drawChart (see chart_data.py for the matching producers).
  var CHART_SPECS = {
    bar: { painter: "bar", stat: true, fold: false, cap: 12, inner: 0 },
    barh: { painter: "barh", stat: true, fold: false, cap: 12, inner: 0 },
    lollipop: { painter: "lollipop", stat: true, fold: false, cap: 12, inner: 0 },
    lollipop_h: { painter: "lollipop_h", stat: true, fold: false, cap: 12, inner: 0 },
    dot: { painter: "dot", stat: true, fold: false, cap: 14, inner: 0 },
    radial_bar: { painter: "radial_bar", stat: true, fold: false, cap: 8, inner: 0.25 },
    radar: { painter: "radar", stat: true, fold: false, cap: 12, inner: 0 },
    line: { painter: "line", stat: true, fold: false, cap: 20, inner: 0 },
    step: { painter: "step", stat: true, fold: false, cap: 20, inner: 0 },
    spline: { painter: "spline", stat: true, fold: false, cap: 20, inner: 0 },
    area: { painter: "area", stat: true, fold: false, cap: 20, inner: 0 },
    waterfall: { painter: "waterfall", stat: true, fold: false, cap: 14, inner: 0 },
    pie: { painter: "pie", stat: false, fold: true, cap: 7, inner: 0 },
    donut: { painter: "pie", stat: false, fold: true, cap: 7, inner: 0.55 },
    rose: { painter: "rose", stat: true, fold: true, cap: 10, inner: 0 },
    funnel: { painter: "funnel", stat: true, fold: false, cap: 10, inner: 0 },
    treemap: { painter: "treemap", stat: true, fold: false, cap: 20, inner: 0 },
    grouped_bar: { painter: "grouped_bar", shape: "series", stat: true, fold: false, cap: 10, inner: 0 },
    stacked_bar: { painter: "stacked_bar", shape: "series", stat: true, fold: false, cap: 12, inner: 0 },
    scatter: { painter: "scatter", shape: "xy", stat: false, fold: false, cap: 0, inner: 0 },
    bubble: { painter: "bubble", shape: "xyz", stat: false, fold: false, cap: 0, inner: 0 },
    histogram: { painter: "histogram", shape: "bins", stat: false, fold: false, cap: 0, inner: 0 },
    candlestick: { painter: "candlestick", shape: "ohlc", stat: false, fold: false, cap: 60, inner: 0 }
  };
  function chartSpec(t) { return CHART_SPECS[t] || CHART_SPECS.bar; }
  function chartShape(t) { return chartSpec(t).shape || "category"; }

  // ---- per-page cross-filter state -------------------------------------
  // pageId -> { sourceId: {key: <string>, pairs: [{field, value}]} }
  var STATE = {};
  function selections(pageId) {
    if (!STATE[pageId]) STATE[pageId] = {};
    return STATE[pageId];
  }

  // ---- data helpers -----------------------------------------------------
  function layerOf(tile) { return (tile.layer_id && DATA.layers[tile.layer_id]) || null; }

  function baseRows(tile) {
    var layer = layerOf(tile);
    if (!layer) return [];
    if (tile.base_pass) {
      return tile.base_pass.map(function (i) { return layer.features[i]; });
    }
    return layer.features;
  }

  function eq(a, b) { return String(a) === String(b); }

  // Rows for a TARGET tile: its base rows AND-filtered by every connected
  // source that currently has an active selection (mirror combined_filter_for).
  function filteredRows(tile, page) {
    var rows = baseRows(tile);
    var conns = page.connections || {};
    var sel = selections(page.id);
    var preds = [];
    Object.keys(conns).forEach(function (src) {
      if (conns[src].indexOf(tile.id) >= 0) {
        var s = sel[src];
        if (s && s.pairs && s.pairs.length) preds = preds.concat(s.pairs);
      }
    });
    if (!preds.length) return rows;
    return rows.filter(function (r) {
      return preds.every(function (p) {
        if (p.lo !== undefined) {          // numeric range predicate (histogram)
          var n = parseFloat(r[p.field]);
          return !isNaN(n) && n >= p.lo && n < p.hi;
        }
        return eq(r[p.field], p.value);
      });
    });
  }

  function setSelection(page, sourceId, sel) {
    var s = selections(page.id);
    if (sel === null) delete s[sourceId];
    else s[sourceId] = sel;
    renderPage(page);
  }

  function toggleSelection(page, sourceId, key, pairs) {
    var cur = selections(page.id)[sourceId];
    if (cur && cur.key === key) setSelection(page, sourceId, null);
    else setSelection(page, sourceId, { key: key, pairs: pairs });
  }

  // ---- formatting -------------------------------------------------------
  function fmtNum(v) {
    if (typeof v !== "number") return String(v);
    if (Number.isInteger(v)) return v.toLocaleString();
    return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function fmtIndicator(cfg, v) {
    if (v === null || v === undefined) return cfg.no_value_text || "No data";
    var out = v;
    if (typeof v === "number" && !Number.isInteger(v)) {
      var dp = (cfg.decimals != null) ? cfg.decimals : 0;
      out = Number(v.toFixed(dp));
    }
    var s = (typeof out === "number") ? out.toLocaleString() : String(out);
    return (cfg.prefix || "") + s + (cfg.suffix || "");
  }

  // ---- aggregation (port of chart._aggregate + fold_categories) ---------
  function foldCategories(items, cap, fold) {
    if (!cap || cap <= 0 || items.length <= cap) return items.slice();
    var head = items.slice(0, cap);
    if (fold) {
      var other = items.slice(cap).reduce(function (a, p) { return a + Number(p[1]); }, 0);
      head.push(["Other", other]);
    }
    return head;
  }

  function aggregateChart(tile, rows) {
    var cfg = tile.config;
    var catField = cfg.category_field;
    if (!catField) return [];
    var spec = chartSpec(cfg.chart_type);
    var stat = spec.stat ? (cfg.statistic || "count") : "count";
    var valField = cfg.value_field;
    var buckets = {};
    rows.forEach(function (r) {
      var key = String(r[catField]);
      if (!buckets[key]) buckets[key] = [];
      if (stat === "count") { buckets[key].push(1); }
      else {
        var v = parseFloat(r[valField]);
        if (!isNaN(v)) buckets[key].push(v);
      }
    });
    var out = Object.keys(buckets).map(function (k) {
      var vals = buckets[k];
      if (stat === "sum") return [k, vals.reduce(function (a, b) { return a + b; }, 0)];
      if (stat === "mean") return [k, vals.length ? vals.reduce(function (a, b) { return a + b; }, 0) / vals.length : 0];
      return [k, vals.length];
    });
    out.sort(function (a, b) { return b[1] - a[1]; });
    var cap = parseInt(cfg.max_categories, 10) || spec.cap;
    return foldCategories(out, cap, spec.fold);
  }

  // ---- non-category producers (port of chart_data.py) ------------------
  function reduceStat(vals, stat) {
    if (stat === "count") return vals.length;
    var nums = vals.map(function (v) { return parseFloat(v); })
      .filter(function (v) { return !isNaN(v); });
    if (!nums.length) return 0;
    if (stat === "sum") return nums.reduce(function (a, b) { return a + b; }, 0);
    if (stat === "mean") return nums.reduce(function (a, b) { return a + b; }, 0) / nums.length;
    return vals.length;
  }

  function aggregateSeries(cfg, rows) {
    var cat = cfg.category_field, ser = cfg.series_field, vf = cfg.value_field;
    var stat = cfg.statistic || "count";
    if (!cat || !ser) return { categories: [], series: [], matrix: [] };
    var buckets = {}, catTot = {}, serTot = {};
    rows.forEach(function (r) {
      var ck = String(r[cat]), sk = String(r[ser]);
      var key = ck + SEP + sk;
      (buckets[key] = buckets[key] || []).push(stat === "count" ? 1 : r[vf]);
    });
    var cells = {};
    Object.keys(buckets).forEach(function (key) {
      var v = reduceStat(buckets[key], stat);
      cells[key] = v;
      var parts = key.split(SEP);
      catTot[parts[0]] = (catTot[parts[0]] || 0) + v;
      serTot[parts[1]] = (serTot[parts[1]] || 0) + v;
    });
    var cap = parseInt(cfg.max_categories, 10) || chartSpec(cfg.chart_type).cap || 10;
    var cats = Object.keys(catTot).sort(function (a, b) { return catTot[b] - catTot[a]; }).slice(0, cap);
    var sers = Object.keys(serTot).sort(function (a, b) { return serTot[b] - serTot[a]; }).slice(0, 8);
    var matrix = cats.map(function (c) {
      return sers.map(function (s) { var v = cells[c + SEP + s]; return v === undefined ? 0 : v; });
    });
    return { categories: cats, series: sers, matrix: matrix };
  }

  function collectPoints(cfg, rows, withSize) {
    var xf = cfg.x_field, yf = cfg.y_field, sf = cfg.size_field;
    if (!xf || !yf) return [];
    var out = [];
    for (var i = 0; i < rows.length && out.length < 2000; i++) {
      var x = parseFloat(rows[i][xf]), y = parseFloat(rows[i][yf]);
      if (isNaN(x) || isNaN(y)) continue;
      if (withSize) {
        var s = parseFloat(rows[i][sf]);
        if (isNaN(s)) continue;
        out.push([x, y, s, ""]);
      } else { out.push([x, y, ""]); }
    }
    return out;
  }

  function rangeLabel(lo, hi) {
    function f(v) { return String(Math.round(v * 100) / 100); }
    return f(lo) + "–" + f(hi);
  }
  function histogramBins(cfg, rows) {
    var vf = cfg.value_field;
    var nums = rows.map(function (r) { return parseFloat(r[vf]); })
      .filter(function (v) { return !isNaN(v); });
    if (!nums.length) return [];
    var bins = Math.max(1, parseInt(cfg.bin_count, 10) || 10);
    var lo = Math.min.apply(null, nums), hi = Math.max.apply(null, nums);
    if (hi === lo) return [[rangeLabel(lo, hi), nums.length, lo, hi]];
    var width = (hi - lo) / bins, counts = [];
    for (var k = 0; k < bins; k++) counts.push(0);
    nums.forEach(function (v) {
      var idx = Math.floor((v - lo) / width);
      if (idx >= bins) idx = bins - 1;
      counts[idx]++;
    });
    return counts.map(function (c, i) {
      var blo = lo + i * width, bhi = lo + (i + 1) * width;
      return [rangeLabel(blo, bhi), c, blo, bhi];
    });
  }

  function aggregateOhlc(cfg, rows) {
    var cf = cfg.category_field, of = cfg.open_field, hf = cfg.high_field,
      lf = cfg.low_field, clf = cfg.close_field;
    if (!cf || !of || !hf || !lf || !clf) return [];
    var order = [], groups = {};
    rows.forEach(function (r) {
      var o = parseFloat(r[of]), h = parseFloat(r[hf]),
        l = parseFloat(r[lf]), c = parseFloat(r[clf]);
      if (isNaN(o) || isNaN(h) || isNaN(l) || isNaN(c)) return;
      var k = String(r[cf]);
      if (!groups[k]) { groups[k] = [o, h, l, c]; order.push(k); }
      else { var g = groups[k]; g[1] = Math.max(g[1], h); g[2] = Math.min(g[2], l); g[3] = c; }
    });
    return order.slice(0, 60).map(function (k) {
      var g = groups[k]; return [k, g[0], g[1], g[2], g[3]];
    });
  }

  // Squarified treemap layout (port of chart_data.squarify).
  function squarify(values, x, y, width, height) {
    var items = [];
    values.forEach(function (v, i) { if (v > 0) items.push([i, v]); });
    if (!items.length || width <= 0 || height <= 0) return [];
    var total = items.reduce(function (a, p) { return a + p[1]; }, 0);
    var scale = (width * height) / total;
    var scaled = items.map(function (p) { return [p[0], p[1] * scale]; });
    var rects = [], rx = x, ry = y, rw = width, rh = height, row = [], i = 0;
    function worst(rw2) {
      var areas = rw2.map(function (p) { return p[1]; });
      var s = areas.reduce(function (a, b) { return a + b; }, 0);
      if (s <= 0) return Infinity;
      var shortest = Math.min(rw, rh), side = s / shortest;
      var hi = Math.max.apply(null, areas), lo = Math.min.apply(null, areas);
      return Math.max((side * side * hi) / (s * s), (s * s) / (side * side * lo));
    }
    function layoutRow(r) {
      var s = r.reduce(function (a, p) { return a + p[1]; }, 0);
      if (rw >= rh) {
        var colW = s / rh, oy = ry;
        r.forEach(function (p) { var hh = p[1] / colW; rects.push([p[0], rx, oy, colW, hh]); oy += hh; });
        rx += colW; rw -= colW;
      } else {
        var rowH = s / rw, ox = rx;
        r.forEach(function (p) { var ww = p[1] / rowH; rects.push([p[0], ox, ry, ww, rowH]); ox += ww; });
        ry += rowH; rh -= rowH;
      }
    }
    while (i < scaled.length) {
      if (!row.length) { row = [scaled[i]]; i++; continue; }
      if (worst(row) >= worst(row.concat([scaled[i]]))) { row.push(scaled[i]); i++; }
      else { layoutRow(row); row = []; }
    }
    if (row.length) layoutRow(row);
    return rects;
  }

  // ---- pivot engine (port of pivot_engine.compute_pivot) ----------------
  var FINALIZERS = {
    count: function (a) { return a.length; },
    sum: function (a) { return a.reduce(function (x, y) { return x + y; }, 0); },
    mean: function (a) { return a.length ? a.reduce(function (x, y) { return x + y; }, 0) / a.length : 0; },
    min: function (a) { return Math.min.apply(null, a); },
    max: function (a) { return Math.max.apply(null, a); }
  };
  function keyOf(r, field) {
    var v = r[field];
    return (v === null || v === undefined) ? NULL_KEY : String(v);
  }
  function computePivot(rows, rowField, colField, valueField, statistic, maxRows, maxCols) {
    var fin = FINALIZERS[statistic] || FINALIZERS.count;
    if (!rowField) return { rowField: rowField, colField: colField, statistic: statistic, rowKeys: [], colKeys: [], cells: {}, rowTotals: {}, colTotals: {}, grandTotal: null, truncated: false };
    var cell = {}, rowb = {}, colb = {}, grand = [];
    rows.forEach(function (r) {
      var rk = keyOf(r, rowField);
      var ck = colField ? keyOf(r, colField) : "";
      var v;
      if (statistic === "count") v = 1;
      else { v = parseFloat(r[valueField]); if (isNaN(v)) return; }
      var ckey = rk + SEP + ck;
      (cell[ckey] = cell[ckey] || []).push(v);
      (rowb[rk] = rowb[rk] || []).push(v);
      grand.push(v);
      if (colField) (colb[ck] = colb[ck] || []).push(v);
    });
    var rowKeysAll = Object.keys(rowb).sort(function (a, b) { return fin(rowb[b]) - fin(rowb[a]); });
    var colKeysAll = colField ? Object.keys(colb).sort(function (a, b) { return fin(colb[b]) - fin(colb[a]); }) : [];
    var truncated = rowKeysAll.length > maxRows || colKeysAll.length > maxCols;
    var rowKeys = rowKeysAll.slice(0, maxRows);
    var colKeys = colKeysAll.slice(0, maxCols);
    var rowSet = {}, colSet = {};
    rowKeys.forEach(function (k) { rowSet[k] = 1; });
    colKeys.forEach(function (k) { colSet[k] = 1; });
    var cells = {};
    Object.keys(cell).forEach(function (ckey) {
      var parts = ckey.split(SEP);
      if (rowSet[parts[0]] && (!colField || colSet[parts[1]])) cells[ckey] = fin(cell[ckey]);
    });
    var rowTotals = {}, colTotals = {};
    rowKeys.forEach(function (k) { rowTotals[k] = fin(rowb[k]); });
    colKeys.forEach(function (k) { colTotals[k] = fin(colb[k]); });
    return {
      rowField: rowField, colField: colField, statistic: statistic,
      rowKeys: rowKeys, colKeys: colKeys, cells: cells,
      rowTotals: rowTotals, colTotals: colTotals,
      grandTotal: grand.length ? fin(grand) : null, truncated: truncated
    };
  }

  // ---- indicator aggregate-expression evaluator ------------------------
  // Supports the common QgsExpression aggregate forms; returns undefined for
  // anything else so the caller can fall back to the server-computed value.
  function evalAggregate(rows, expr) {
    expr = (expr || "count(1)").trim();
    if (/^count\s*\(\s*(1|\*)?\s*\)$/i.test(expr)) return rows.length;
    var m = expr.match(/^count\s*\(\s*distinct\s+"?([^")]+)"?\s*\)$/i);
    if (m) {
      var seen = {};
      rows.forEach(function (r) { seen[String(r[m[1]])] = 1; });
      return Object.keys(seen).length;
    }
    m = expr.match(/^(sum|mean|avg|average|min|max|count)\s*\(\s*"?([^")]+)"?\s*\)$/i);
    if (m) {
      var fn = m[1].toLowerCase(), field = m[2];
      var vals = rows.map(function (r) { return parseFloat(r[field]); })
        .filter(function (v) { return !isNaN(v); });
      if (fn === "count") return vals.length;
      if (!vals.length) return null;
      if (fn === "sum") return vals.reduce(function (a, b) { return a + b; }, 0);
      if (fn === "mean" || fn === "avg" || fn === "average") return vals.reduce(function (a, b) { return a + b; }, 0) / vals.length;
      if (fn === "min") return Math.min.apply(null, vals);
      if (fn === "max") return Math.max.apply(null, vals);
    }
    return undefined;
  }

  // ---- DOM helpers ------------------------------------------------------
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  var SVGNS = "http://www.w3.org/2000/svg";
  function svgEl(tag, attrs) {
    var n = document.createElementNS(SVGNS, tag);
    if (attrs) Object.keys(attrs).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    return n;
  }
  function color(i) { return SERIES[i % SERIES.length]; }
  function escapeHtml(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  // ---- SVG chart painters ----------------------------------------------
  function drawChart(host, tile, page) {
    host.innerHTML = "";
    var cfg = tile.config;
    var rows = filteredRows(tile, page);
    var shape = chartShape(cfg.chart_type);
    var spec = chartSpec(cfg.chart_type);
    var w = host.clientWidth || 300, h = host.clientHeight || 200;
    var sel = selections(page.id)[tile.id];
    var selKey = sel ? sel.key : null;
    var svg = svgEl("svg", { "class": "dash-chart", width: w, height: h, viewBox: "0 0 " + w + " " + h });
    var empty = function () { host.appendChild(el("div", "dash-empty", "No data")); };

    // category equality cross-filter (bar/line/pie family + series/ohlc)
    var pickCat = function (cat) {
      if (cat === "Other") return;
      toggleSelection(page, tile.id, cat, [{ field: cfg.category_field, value: cat }]);
    };

    if (shape === "series") {
      var sdata = aggregateSeries(cfg, rows);
      if (!sdata.categories.length) return empty();
      if (spec.painter === "stacked_bar") paintStacked(svg, w, h, sdata, selKey, pickCat);
      else paintGrouped(svg, w, h, sdata, selKey, pickCat);
    } else if (shape === "xy" || shape === "xyz") {
      var pts = collectPoints(cfg, rows, shape === "xyz");
      if (!pts.length) return empty();
      paintScatter(svg, w, h, pts, shape === "xyz");
    } else if (shape === "bins") {
      var bins = histogramBins(cfg, rows);
      if (!bins.length) return empty();
      var pickBin = function (label, lo, hi) {
        toggleSelection(page, tile.id, label, [{ field: cfg.value_field, lo: lo, hi: hi }]);
      };
      paintHistogram(svg, w, h, bins, selKey, pickBin);
    } else if (shape === "ohlc") {
      var candles = aggregateOhlc(cfg, rows);
      if (!candles.length) return empty();
      paintCandles(svg, w, h, candles, selKey, pickCat);
    } else {
      var data = aggregateChart(tile, rows);
      if (!data.length) return empty();
      var p = spec.painter;
      if (p === "bar") paintBars(svg, w, h, data, selKey, pickCat, false);
      else if (p === "barh") paintBars(svg, w, h, data, selKey, pickCat, true);
      else if (p === "lollipop") paintLollipop(svg, w, h, data, selKey, pickCat, false);
      else if (p === "lollipop_h") paintLollipop(svg, w, h, data, selKey, pickCat, true);
      else if (p === "dot") paintDot(svg, w, h, data, selKey, pickCat);
      else if (p === "line") paintLine(svg, w, h, data, selKey, pickCat, false, "line");
      else if (p === "step") paintLine(svg, w, h, data, selKey, pickCat, false, "step");
      else if (p === "spline") paintLine(svg, w, h, data, selKey, pickCat, false, "spline");
      else if (p === "area") paintLine(svg, w, h, data, selKey, pickCat, true, "line");
      else if (p === "waterfall") paintWaterfall(svg, w, h, data, selKey, pickCat);
      else if (p === "pie") paintPie(svg, w, h, data, selKey, pickCat, spec.inner);
      else if (p === "rose") paintRose(svg, w, h, data, selKey, pickCat);
      else if (p === "radial_bar") paintRadial(svg, w, h, data, selKey, pickCat, spec.inner);
      else if (p === "radar") paintRadar(svg, w, h, data, selKey, pickCat);
      else if (p === "funnel") paintFunnel(svg, w, h, data, selKey, pickCat);
      else if (p === "treemap") paintTreemap(svg, w, h, data, selKey, pickCat);
      else paintBars(svg, w, h, data, selKey, pickCat, false);
    }
    host.appendChild(svg);
  }

  function paintBars(svg, w, h, data, selKey, onPick, horizontal) {
    var pad = 8, labelH = 16, topPad = 14;
    var maxV = Math.max.apply(null, data.map(function (d) { return Number(d[1]); })) || 1;
    if (!horizontal) {
      var plotBottom = h - pad - labelH, plotTop = pad + topPad;
      var plotH = Math.max(plotBottom - plotTop, 1);
      var slotW = (w - 2 * pad) / data.length, barW = slotW * 0.6;
      data.forEach(function (d, i) {
        var x = pad + i * slotW, bh = plotH * (Number(d[1]) / maxV), y = plotBottom - bh;
        var fill = (d[0] === selKey) ? "var(--muted)" : color(i);
        var rect = svgEl("rect", { x: x + (slotW - barW) / 2, y: y, width: barW, height: bh, fill: fill, cursor: "pointer" });
        rect.addEventListener("click", function () { onPick(d[0]); });
        svg.appendChild(rect);
        addText(svg, x + slotW / 2, y - 3, fmtNum(Number(d[1])), "middle", "var(--text)", 10);
        addText(svg, x + slotW / 2, plotBottom + 12, clip(d[0], slotW), "middle", "var(--muted)", 10);
      });
    } else {
      var labelW = Math.min(w * 0.32, 140), valW = 46;
      var plotLeft = pad + labelW, plotW = Math.max(w - pad - labelW - valW, 1);
      var slotH = (h - 2 * pad) / data.length, barH = Math.min(slotH * 0.6, 26);
      data.forEach(function (d, i) {
        var top = pad + i * slotH, bw = plotW * (Number(d[1]) / maxV), y = top + (slotH - barH) / 2;
        var fill = (d[0] === selKey) ? "var(--muted)" : color(i);
        addText(svg, pad, top + slotH / 2, clip(d[0], labelW - 6), "start", "var(--muted)", 10);
        var rect = svgEl("rect", { x: plotLeft, y: y, width: bw, height: barH, fill: fill, cursor: "pointer" });
        rect.addEventListener("click", function () { onPick(d[0]); });
        svg.appendChild(rect);
        addText(svg, plotLeft + bw + 4, top + slotH / 2, fmtNum(Number(d[1])), "start", "var(--text)", 10);
      });
    }
  }

  // mode: "line" (straight), "step" (orthogonal), "spline" (smoothed cubic)
  function linePathD(pts, mode) {
    if (!pts.length) return "";
    var d = "M" + pts[0].x + "," + pts[0].y;
    if (mode === "step") {
      for (var i = 1; i < pts.length; i++) {
        var mx = (pts[i - 1].x + pts[i].x) / 2;
        d += " L" + mx + "," + pts[i - 1].y + " L" + mx + "," + pts[i].y + " L" + pts[i].x + "," + pts[i].y;
      }
    } else if (mode === "spline") {
      for (var j = 0; j < pts.length - 1; j++) {
        var p0 = pts[j - 1] || pts[j], p1 = pts[j], p2 = pts[j + 1], p3 = pts[j + 2] || p2;
        var c1x = p1.x + (p2.x - p0.x) / 6, c1y = p1.y + (p2.y - p0.y) / 6;
        var c2x = p2.x - (p3.x - p1.x) / 6, c2y = p2.y - (p3.y - p1.y) / 6;
        d += " C" + c1x + "," + c1y + " " + c2x + "," + c2y + " " + p2.x + "," + p2.y;
      }
    } else {
      for (var k = 1; k < pts.length; k++) d += " L" + pts[k].x + "," + pts[k].y;
    }
    return d;
  }

  function paintLine(svg, w, h, data, selKey, onPick, fill, mode) {
    var pad = 8, labelH = 16, topPad = 14;
    var maxV = Math.max.apply(null, data.map(function (d) { return Number(d[1]); })) || 1;
    var plotBottom = h - pad - labelH, plotTop = pad + topPad;
    var plotH = Math.max(plotBottom - plotTop, 1);
    var slotW = (w - 2 * pad) / data.length;
    var pts = data.map(function (d, i) {
      return { x: pad + slotW * (i + 0.5), y: plotBottom - plotH * (Number(d[1]) / maxV), cat: d[0] };
    });
    var dPath = linePathD(pts, mode);
    if (fill && pts.length) {
      var fillD = dPath + " L" + pts[pts.length - 1].x + "," + plotBottom +
        " L" + pts[0].x + "," + plotBottom + " Z";
      svg.appendChild(svgEl("path", { d: fillD, fill: color(0), "fill-opacity": 0.22, stroke: "none" }));
    }
    svg.appendChild(svgEl("path", { d: dPath, fill: "none", stroke: color(0), "stroke-width": 2 }));
    pts.forEach(function (p, i) {
      var selp = (p.cat === selKey);
      var c = svgEl("circle", { cx: p.x, cy: p.y, r: selp ? 5 : 3, fill: selp ? "var(--muted)" : color(0), stroke: "var(--chart-bg)", cursor: "pointer" });
      c.addEventListener("click", function () { onPick(p.cat); });
      svg.appendChild(c);
      addText(svg, p.x, plotBottom + 12, clip(p.cat, slotW), "middle", "var(--muted)", 10);
    });
  }

  function paintPie(svg, w, h, data, selKey, onPick, inner) {
    var total = data.reduce(function (a, d) { return a + Number(d[1]); }, 0);
    if (total <= 0) return;
    var legendW = w > 260 ? Math.min(w * 0.4, 180) : 0;
    var pieW = w - legendW;
    var diameter = Math.max(Math.min(pieW, h) - 8, 10);
    var cx = pieW / 2, cy = h / 2, radius = diameter / 2;
    var innerR = inner ? radius * inner : 0;
    var start = -90;
    data.forEach(function (d, i) {
      var span = 360 * Number(d[1]) / total;
      var explode = (d[0] === selKey) ? 8 : 0;
      var mid = (start + span / 2) * Math.PI / 180;
      var ox = Math.cos(mid) * explode, oy = Math.sin(mid) * explode;
      var path = arcPath(cx + ox, cy + oy, radius, start, start + span, innerR);
      var seg = svgEl("path", { d: path, fill: color(i), stroke: "#ffffff", "stroke-width": 1, cursor: "pointer" });
      seg.addEventListener("click", function () { onPick(d[0]); });
      svg.appendChild(seg);
      start += span;
    });
    if (legendW) {
      var ry = 6;
      data.forEach(function (d, i) {
        if (ry + 16 > h) return;
        svg.appendChild(svgEl("rect", { x: pieW + 6, y: ry, width: 11, height: 11, fill: color(i) }));
        addText(svg, pieW + 22, ry + 9, clip(d[0] + " (" + fmtNum(Number(d[1])) + ")", legendW - 24), "start", "var(--text)", 10);
        ry += 18;
      });
    }
  }

  function arcPath(cx, cy, r, a0, a1, innerR) {
    var large = (a1 - a0) > 180 ? 1 : 0;
    var p0 = polar(cx, cy, r, a0), p1 = polar(cx, cy, r, a1);
    if (!innerR) {
      return "M" + cx + "," + cy + " L" + p0.x + "," + p0.y +
        " A" + r + "," + r + " 0 " + large + " 1 " + p1.x + "," + p1.y + " Z";
    }
    var i0 = polar(cx, cy, innerR, a0), i1 = polar(cx, cy, innerR, a1);
    return "M" + p0.x + "," + p0.y +
      " A" + r + "," + r + " 0 " + large + " 1 " + p1.x + "," + p1.y +
      " L" + i1.x + "," + i1.y +
      " A" + innerR + "," + innerR + " 0 " + large + " 0 " + i0.x + "," + i0.y + " Z";
  }
  function polar(cx, cy, r, deg) {
    var rad = deg * Math.PI / 180;
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
  }
  function addText(svg, x, y, text, anchor, fill, size) {
    var t = svgEl("text", { x: x, y: y, "text-anchor": anchor, fill: fill, "font-size": size, "dominant-baseline": "middle" });
    t.textContent = text;
    svg.appendChild(t);
  }
  function clip(text, px) {
    text = String(text);
    var max = Math.max(Math.floor(px / 6), 1);
    return text.length > max ? text.slice(0, max - 1) + "…" : text;
  }

  function textOn(hex) {
    var m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex || "");
    if (!m) return "#ffffff";
    var luma = 0.299 * parseInt(m[1], 16) + 0.587 * parseInt(m[2], 16) + 0.114 * parseInt(m[3], 16);
    return luma > 150 ? "#1b2733" : "#ffffff";
  }

  function paintLollipop(svg, w, h, data, selKey, onPick, horizontal) {
    var pad = 8, labelH = 16, topPad = 14;
    var maxV = Math.max.apply(null, data.map(function (d) { return Number(d[1]); })) || 1;
    if (!horizontal) {
      var plotBottom = h - pad - labelH, plotTop = pad + topPad;
      var plotH = Math.max(plotBottom - plotTop, 1), slotW = (w - 2 * pad) / data.length;
      data.forEach(function (d, i) {
        var cx = pad + slotW * (i + 0.5), y = plotBottom - plotH * (Number(d[1]) / maxV);
        var c = (d[0] === selKey) ? "var(--muted)" : color(i);
        svg.appendChild(svgEl("line", { x1: cx, y1: plotBottom, x2: cx, y2: y, stroke: c, "stroke-width": 2 }));
        var dot = svgEl("circle", { cx: cx, cy: y, r: 5, fill: c, cursor: "pointer" });
        dot.addEventListener("click", function () { onPick(d[0]); });
        svg.appendChild(dot);
        addText(svg, cx, y - 8, fmtNum(Number(d[1])), "middle", "var(--text)", 10);
        addText(svg, cx, plotBottom + 12, clip(d[0], slotW), "middle", "var(--muted)", 10);
      });
    } else {
      var labelW = Math.min(w * 0.32, 140), valW = 46;
      var plotLeft = pad + labelW, plotW = Math.max(w - pad - labelW - valW, 1);
      var slotH = (h - 2 * pad) / data.length;
      data.forEach(function (d, i) {
        var cy = pad + i * slotH + slotH / 2, x = plotLeft + plotW * (Number(d[1]) / maxV);
        var c = (d[0] === selKey) ? "var(--muted)" : color(i);
        addText(svg, pad, cy, clip(d[0], labelW - 6), "start", "var(--muted)", 10);
        svg.appendChild(svgEl("line", { x1: plotLeft, y1: cy, x2: x, y2: cy, stroke: c, "stroke-width": 2 }));
        var dot = svgEl("circle", { cx: x, cy: cy, r: 5, fill: c, cursor: "pointer" });
        dot.addEventListener("click", function () { onPick(d[0]); });
        svg.appendChild(dot);
        addText(svg, x + 8, cy, fmtNum(Number(d[1])), "start", "var(--text)", 10);
      });
    }
  }

  function paintDot(svg, w, h, data, selKey, onPick) {
    var pad = 8, valW = 46, labelW = Math.min(w * 0.32, 140);
    var maxV = Math.max.apply(null, data.map(function (d) { return Number(d[1]); })) || 1;
    var plotLeft = pad + labelW, plotW = Math.max(w - pad - labelW - valW, 1);
    var slotH = (h - 2 * pad) / data.length;
    data.forEach(function (d, i) {
      var cy = pad + i * slotH + slotH / 2, x = plotLeft + plotW * (Number(d[1]) / maxV);
      var c = (d[0] === selKey) ? "var(--muted)" : color(i);
      addText(svg, pad, cy, clip(d[0], labelW - 6), "start", "var(--muted)", 10);
      svg.appendChild(svgEl("line", { x1: plotLeft, y1: cy, x2: x, y2: cy, stroke: "var(--grid-line)", "stroke-width": 1, "stroke-dasharray": "2,2" }));
      var dot = svgEl("circle", { cx: x, cy: cy, r: 5, fill: c, cursor: "pointer" });
      dot.addEventListener("click", function () { onPick(d[0]); });
      svg.appendChild(dot);
      addText(svg, x + 8, cy, fmtNum(Number(d[1])), "start", "var(--text)", 10);
    });
  }

  function paintWaterfall(svg, w, h, data, selKey, onPick) {
    var pad = 8, labelH = 16, topPad = 14;
    var cum = 0, lo = 0, hi = 0, steps = [];
    data.forEach(function (d) {
      var start = cum; cum += Number(d[1]);
      steps.push([d[0], start, cum, Number(d[1])]);
      lo = Math.min(lo, start, cum); hi = Math.max(hi, start, cum);
    });
    var rng = (hi - lo) || 1;
    var plotBottom = h - pad - labelH, plotTop = pad + topPad;
    var plotH = Math.max(plotBottom - plotTop, 1), slotW = (w - 2 * pad) / data.length, barW = slotW * 0.6;
    function yOf(v) { return plotBottom - plotH * ((v - lo) / rng); }
    steps.forEach(function (s, i) {
      var x = pad + i * slotW, y0 = yOf(s[1]), y1 = yOf(s[2]);
      var top = Math.min(y0, y1), bh = Math.max(Math.abs(y1 - y0), 1);
      var c = (s[0] === selKey) ? "var(--muted)" : (s[3] >= 0 ? color(0) : "var(--muted)");
      var rect = svgEl("rect", { x: x + (slotW - barW) / 2, y: top, width: barW, height: bh, fill: c, cursor: "pointer" });
      rect.addEventListener("click", function () { onPick(s[0]); });
      svg.appendChild(rect);
      addText(svg, x + slotW / 2, plotBottom + 12, clip(s[0], slotW), "middle", "var(--muted)", 10);
    });
  }

  function paintRose(svg, w, h, data, selKey, onPick) {
    var total = data.reduce(function (a, d) { return a + Number(d[1]); }, 0);
    if (total <= 0) return;
    var maxV = Math.max.apply(null, data.map(function (d) { return Number(d[1]); })) || 1;
    var radius = Math.max(Math.min(w, h) / 2 - 6, 10), cx = w / 2, cy = h / 2;
    var span = 360 / data.length, start = -90;
    data.forEach(function (d, i) {
      var r = radius * Math.sqrt(Number(d[1]) / maxV);
      var c = (d[0] === selKey) ? "var(--muted)" : color(i);
      var seg = svgEl("path", { d: arcPath(cx, cy, r, start, start + span, 0), fill: c, stroke: "#ffffff", "stroke-width": 1, cursor: "pointer" });
      seg.addEventListener("click", function () { onPick(d[0]); });
      svg.appendChild(seg);
      start += span;
    });
  }

  function paintRadial(svg, w, h, data, selKey, onPick, inner) {
    var SWEEP = 270;
    var maxV = Math.max.apply(null, data.map(function (d) { return Number(d[1]); })) || 1;
    var radius = Math.max(Math.min(w, h) / 2 - 6, 10), cx = w / 2, cy = h / 2;
    var innerR = radius * (inner || 0.25), gap = (radius - innerR) / data.length;
    var thick = Math.max(gap * 0.6, 3);
    data.forEach(function (d, i) {
      var r = radius - (i + 0.5) * gap;
      var c = (d[0] === selKey) ? "var(--muted)" : color(i);
      svg.appendChild(svgEl("path", { d: ringArc(cx, cy, r, -90, -90 + SWEEP), fill: "none", stroke: "var(--grid-line)", "stroke-width": thick, "stroke-linecap": "round" }));
      var sweep = SWEEP * (Number(d[1]) / maxV);
      var arc = svgEl("path", { d: ringArc(cx, cy, r, -90, -90 + sweep), fill: "none", stroke: c, "stroke-width": thick, "stroke-linecap": "round", cursor: "pointer" });
      arc.addEventListener("click", function () { onPick(d[0]); });
      svg.appendChild(arc);
      addText(svg, cx + 3, cy - r, clip(d[0] + " (" + fmtNum(Number(d[1])) + ")", r), "start", "var(--muted)", 9);
    });
  }
  function ringArc(cx, cy, r, a0, a1) {
    var large = Math.abs(a1 - a0) > 180 ? 1 : 0, sweep = a1 > a0 ? 1 : 0;
    var p0 = polar(cx, cy, r, a0), p1 = polar(cx, cy, r, a1);
    return "M" + p0.x + "," + p0.y + " A" + r + "," + r + " 0 " + large + " " + sweep + " " + p1.x + "," + p1.y;
  }

  function paintRadar(svg, w, h, data, selKey, onPick) {
    var n = data.length;
    var maxV = Math.max.apply(null, data.map(function (d) { return Number(d[1]); })) || 1;
    var radius = Math.max(Math.min(w, h) / 2 - 6, 10) * 0.78, cx = w / 2, cy = h / 2;
    for (var k = 1; k <= 3; k++) {
      svg.appendChild(svgEl("circle", { cx: cx, cy: cy, r: radius * k / 3, fill: "none", stroke: "var(--grid-line)", "stroke-width": 1 }));
    }
    var pts = [];
    data.forEach(function (d, i) {
      var deg = -90 + i * 360 / n, axis = polar(cx, cy, radius, deg);
      svg.appendChild(svgEl("line", { x1: cx, y1: cy, x2: axis.x, y2: axis.y, stroke: "var(--grid-line)", "stroke-width": 1 }));
      var pt = polar(cx, cy, radius * (Number(d[1]) / maxV), deg);
      pts.push({ x: pt.x, y: pt.y, cat: d[0] });
      var lbl = polar(cx, cy, radius + 12, deg);
      addText(svg, lbl.x, lbl.y, clip(d[0], 70), "middle", "var(--muted)", 9);
    });
    if (pts.length) {
      svg.appendChild(svgEl("polygon", { points: pts.map(function (p) { return p.x + "," + p.y; }).join(" "), fill: color(0), "fill-opacity": 0.28, stroke: color(0), "stroke-width": 2 }));
      pts.forEach(function (p) {
        var c = svgEl("circle", { cx: p.x, cy: p.y, r: 4, fill: (p.cat === selKey) ? "var(--muted)" : color(0), cursor: "pointer" });
        c.addEventListener("click", function () { onPick(p.cat); });
        svg.appendChild(c);
      });
    }
  }

  function paintFunnel(svg, w, h, data, selKey, onPick) {
    var pad = 8;
    var maxV = Math.max.apply(null, data.map(function (d) { return Number(d[1]); })) || 1;
    var slotH = (h - 2 * pad) / data.length, barH = Math.min(slotH * 0.7, 46), cx = w / 2;
    data.forEach(function (d, i) {
      var bw = (w - 2 * pad) * (Number(d[1]) / maxV);
      var top = pad + i * slotH + (slotH - barH) / 2;
      var c = (d[0] === selKey) ? "var(--muted)" : color(i);
      var rect = svgEl("rect", { x: cx - bw / 2, y: top, width: bw, height: barH, rx: 3, fill: c, cursor: "pointer" });
      rect.addEventListener("click", function () { onPick(d[0]); });
      svg.appendChild(rect);
      addText(svg, cx, top + barH / 2, clip(d[0] + "  " + fmtNum(Number(d[1])), w - 2 * pad), "middle", textOn(SERIES[i % SERIES.length]), 10);
    });
  }

  function paintTreemap(svg, w, h, data, selKey, onPick) {
    var pad = 6;
    var values = data.map(function (d) { return Math.max(Number(d[1]), 0); });
    var rects = squarify(values, pad, pad, w - 2 * pad, h - 2 * pad);
    rects.forEach(function (r) {
      var idx = r[0], d = data[idx];
      var sel = (d[0] === selKey);
      var fill = sel ? "var(--muted)" : color(idx);
      var rect = svgEl("rect", { x: r[1], y: r[2], width: r[3], height: r[4], fill: fill, stroke: "#ffffff", "stroke-width": 1, cursor: "pointer" });
      rect.addEventListener("click", function () { onPick(d[0]); });
      svg.appendChild(rect);
      if (r[3] > 38 && r[4] > 14) {
        addText(svg, r[1] + 4, r[2] + 11, clip(d[0] + " (" + fmtNum(Number(d[1])) + ")", r[3] - 6), "start", textOn(SERIES[idx % SERIES.length]), 10);
      }
    });
  }

  function seriesLegend(svg, x, h, series) {
    var ry = 6;
    series.forEach(function (name, j) {
      if (ry + 16 > h) return;
      svg.appendChild(svgEl("rect", { x: x + 6, y: ry, width: 11, height: 11, fill: color(j) }));
      addText(svg, x + 22, ry + 9, clip(name, 130), "start", "var(--text)", 10);
      ry += 18;
    });
  }

  function paintGrouped(svg, w, h, sdata, selKey, onPick) {
    var pad = 8, labelH = 16;
    var cats = sdata.categories, series = sdata.series, matrix = sdata.matrix;
    var legendW = (w > 280 && series.length) ? Math.min(w * 0.32, 160) : 0;
    var plotW = w - legendW;
    var maxV = Math.max.apply(null, matrix.map(function (row) { return Math.max.apply(null, row.concat([0])); })) || 1;
    var plotBottom = h - pad - labelH, plotTop = pad + 4, plotH = Math.max(plotBottom - plotTop, 1);
    var slotW = (plotW - 2 * pad) / cats.length, groupW = slotW * 0.8, barW = groupW / series.length;
    cats.forEach(function (cat, i) {
      var sel = (cat === selKey);
      var slotLeft = pad + i * slotW + (slotW - groupW) / 2;
      series.forEach(function (s, j) {
        var v = matrix[i][j] || 0, bh = plotH * (v / maxV);
        var rect = svgEl("rect", { x: slotLeft + j * barW, y: plotBottom - bh, width: barW * 0.9, height: bh, fill: color(j), "fill-opacity": sel ? 0.6 : 1, cursor: "pointer" });
        rect.addEventListener("click", function () { onPick(cat); });
        svg.appendChild(rect);
      });
      addText(svg, pad + i * slotW + slotW / 2, plotBottom + 12, clip(cat, slotW), "middle", "var(--muted)", 10);
    });
    if (legendW) seriesLegend(svg, plotW, h, series);
  }

  function paintStacked(svg, w, h, sdata, selKey, onPick) {
    var pad = 8, labelH = 16;
    var cats = sdata.categories, series = sdata.series, matrix = sdata.matrix;
    var legendW = (w > 280 && series.length) ? Math.min(w * 0.32, 160) : 0;
    var plotW = w - legendW;
    var totals = matrix.map(function (row) { return row.reduce(function (a, b) { return a + b; }, 0); });
    var maxV = Math.max.apply(null, totals.concat([0])) || 1;
    var plotBottom = h - pad - labelH, plotTop = pad + 4, plotH = Math.max(plotBottom - plotTop, 1);
    var slotW = (plotW - 2 * pad) / cats.length, barW = slotW * 0.6;
    cats.forEach(function (cat, i) {
      var sel = (cat === selKey), x = pad + i * slotW + (slotW - barW) / 2, y = plotBottom;
      series.forEach(function (s, j) {
        var v = matrix[i][j] || 0, bh = plotH * (v / maxV);
        var rect = svgEl("rect", { x: x, y: y - bh, width: barW, height: bh, fill: color(j), "fill-opacity": sel ? 0.6 : 1, cursor: "pointer" });
        rect.addEventListener("click", function () { onPick(cat); });
        svg.appendChild(rect);
        y -= bh;
      });
      addText(svg, pad + i * slotW + slotW / 2, plotBottom + 12, clip(cat, slotW), "middle", "var(--muted)", 10);
    });
    if (legendW) seriesLegend(svg, plotW, h, series);
  }

  function paintScatter(svg, w, h, pts, withSize) {
    var pad = 8, axisL = 34, axisB = 24;
    var xs = pts.map(function (d) { return d[0]; }), ys = pts.map(function (d) { return d[1]; });
    var xlo = Math.min.apply(null, xs), xhi = Math.max.apply(null, xs);
    var ylo = Math.min.apply(null, ys), yhi = Math.max.apply(null, ys);
    if (xhi === xlo) xhi += 1;
    if (yhi === ylo) yhi += 1;
    var left = pad + axisL, bottom = h - pad - axisB;
    var plotW = Math.max(w - pad - left, 1), plotH = Math.max(bottom - pad, 1);
    svg.appendChild(svgEl("line", { x1: left, y1: pad, x2: left, y2: bottom, stroke: "var(--grid-line)", "stroke-width": 1 }));
    svg.appendChild(svgEl("line", { x1: left, y1: bottom, x2: w - pad, y2: bottom, stroke: "var(--grid-line)", "stroke-width": 1 }));
    var smax = withSize ? (Math.max.apply(null, pts.map(function (d) { return d[2]; })) || 1) : 1;
    pts.forEach(function (d) {
      var x = left + (d[0] - xlo) / (xhi - xlo) * plotW;
      var y = bottom - (d[1] - ylo) / (yhi - ylo) * plotH;
      var r = withSize ? (4 + 18 * Math.sqrt(Math.max(d[2], 0) / smax)) : 4;
      svg.appendChild(svgEl("circle", { cx: x, cy: y, r: r, fill: color(0), "fill-opacity": 0.6, stroke: "#ffffff", "stroke-width": 1 }));
    });
    addText(svg, left, bottom + 12, fmtNum(xlo), "start", "var(--muted)", 9);
    addText(svg, w - pad, bottom + 12, fmtNum(xhi), "end", "var(--muted)", 9);
    addText(svg, left - 4, pad + 4, fmtNum(yhi), "end", "var(--muted)", 9);
    addText(svg, left - 4, bottom, fmtNum(ylo), "end", "var(--muted)", 9);
  }

  function paintHistogram(svg, w, h, bins, selKey, onPick) {
    var pad = 8, labelH = 16, topPad = 6;
    var maxC = Math.max.apply(null, bins.map(function (b) { return Number(b[1]); })) || 1;
    var plotBottom = h - pad - labelH, plotTop = pad + topPad, plotH = Math.max(plotBottom - plotTop, 1);
    var barW = (w - 2 * pad) / bins.length;
    bins.forEach(function (b, i) {
      var x = pad + i * barW, bh = plotH * (Number(b[1]) / maxC);
      var c = (b[0] === selKey) ? "var(--muted)" : color(0);
      var rect = svgEl("rect", { x: x, y: plotBottom - bh, width: barW, height: bh, fill: c, stroke: "#ffffff", "stroke-width": 1, cursor: "pointer" });
      rect.addEventListener("click", function () { onPick(b[0], b[2], b[3]); });
      svg.appendChild(rect);
      if (barW > 26) addText(svg, x + barW / 2, plotBottom + 12, clip(b[0], barW), "middle", "var(--muted)", 9);
    });
  }

  function paintCandles(svg, w, h, candles, selKey, onPick) {
    var pad = 8, labelH = 16;
    var hi = Math.max.apply(null, candles.map(function (d) { return d[2]; }));
    var lo = Math.min.apply(null, candles.map(function (d) { return d[3]; }));
    var rng = (hi - lo) || 1;
    var plotBottom = h - pad - labelH, plotTop = pad + 4, plotH = Math.max(plotBottom - plotTop, 1);
    var slotW = (w - 2 * pad) / candles.length, bodyW = slotW * 0.6;
    function yOf(v) { return plotBottom - plotH * ((v - lo) / rng); }
    candles.forEach(function (d, i) {
      var cx = pad + slotW * (i + 0.5), sel = (d[0] === selKey);
      var c = sel ? "var(--muted)" : (d[4] >= d[1] ? color(0) : "var(--muted)");
      svg.appendChild(svgEl("line", { x1: cx, y1: yOf(d[2]), x2: cx, y2: yOf(d[3]), stroke: c, "stroke-width": 1 }));
      var yo = yOf(d[1]), yc = yOf(d[4]), top = Math.min(yo, yc), bh = Math.max(Math.abs(yc - yo), 1);
      var rect = svgEl("rect", { x: cx - bodyW / 2, y: top, width: bodyW, height: bh, fill: c, stroke: "#ffffff", "stroke-width": 1, cursor: "pointer" });
      rect.addEventListener("click", function () { onPick(d[0]); });
      svg.appendChild(rect);
      addText(svg, cx, plotBottom + 12, clip(d[0], slotW), "middle", "var(--muted)", 9);
    });
  }

  // ---- indicator value animations (mirror elements/indicator_anim.py) ----
  // The page DOM is rebuilt on every filter change, so the previous numeric
  // value is kept per tile id to drive odometer/rolling transitions.
  var IND_LAST = {};
  function easeOutCubic(t) { return 1 - Math.pow(1 - Math.min(Math.max(t, 0), 1), 3); }

  function animateNumber(node, cfg, from, to, dur) {
    var start = null;
    function frame(ts) {
      if (start === null) start = ts;
      var t = Math.min((ts - start) / dur, 1);
      node.textContent = fmtIndicator(cfg, from + (to - from) * easeOutCubic(t));
      if (t < 1) requestAnimationFrame(frame); else node.textContent = fmtIndicator(cfg, to);
    }
    requestAnimationFrame(frame);
  }
  function animateTypewriter(node, text, dur) {
    var start = null;
    function frame(ts) {
      if (start === null) start = ts;
      var t = Math.min((ts - start) / dur, 1);
      node.textContent = text.slice(0, Math.round(text.length * t));
      if (t < 1) requestAnimationFrame(frame); else node.textContent = text;
    }
    requestAnimationFrame(frame);
  }

  // ---- tile renderers ---------------------------------------------------
  function renderIndicator(body, tile, page) {
    var cfg = tile.config, rows = filteredRows(tile, page);
    var box = el("div", "dash-indicator");
    if (cfg.top_text) box.appendChild(el("div", "dash-ind-top", cfg.top_text));

    var live = evalAggregate(rows, cfg.value_expression || "count(1)");
    var value = (live === undefined) ? tile.indicator_value : live;
    var text = fmtIndicator(cfg, value);

    // value + optional icon (left / right / above)
    var wrap = el("div", "dash-ind-valuewrap pos-" + (cfg.icon_position || "left"));
    if (cfg.icon_gap != null) wrap.style.gap = (cfg.icon_gap | 0) + "px";
    if (tile.icon_uri) {
      var img = el("img", "dash-ind-icon");
      img.src = tile.icon_uri;
      var isz = cfg.icon_size || 48;
      img.style.width = isz + "px"; img.style.height = isz + "px";
      wrap.appendChild(img);
    }
    var valNode = el("div", "dash-ind-value");
    if (cfg.value_size) valNode.style.fontSize = cfg.value_size + "px";
    wrap.appendChild(valNode);
    box.appendChild(wrap);

    var mode = (cfg.animation || "").toLowerCase();
    var dur = cfg.animation_duration_ms || 900;
    var last = IND_LAST[tile.id];
    if ((mode === "odometer" || mode === "rolling") && typeof value === "number"
        && typeof last === "number" && last !== value) {
      animateNumber(valNode, cfg, last, value, dur);
    } else if (mode === "typewriter") {
      animateTypewriter(valNode, text, dur);
    } else if (mode === "fade") {
      valNode.textContent = text;
      valNode.classList.add("fade-in");
    } else {
      valNode.textContent = text;
    }
    if (typeof value === "number") IND_LAST[tile.id] = value;

    if (cfg.reference_expression && typeof value === "number") {
      var ref = evalAggregate(rows, cfg.reference_expression);
      if (typeof ref === "number") {
        var delta = value - ref;
        var arrow = delta > 0 ? "▲" : (delta < 0 ? "▼" : "—");
        var cls = "dash-ind-bottom " + (delta > 0 ? "up" : delta < 0 ? "down" : "");
        box.appendChild(el("div", cls, arrow + " " + fmtIndicator(cfg, Math.abs(delta)) + " vs ref"));
      }
    }
    body.appendChild(box);
  }

  function renderList(body, tile, page) {
    var cfg = tile.config, layer = layerOf(tile);
    var fields = (cfg.display_fields && cfg.display_fields.length) ? cfg.display_fields
      : (layer ? layer.fields.slice(0, 3) : []);
    var rows = filteredRows(tile, page).slice(0, cfg.max_rows || 200);
    var wrap = el("div", "dash-table-wrap");
    var table = el("table", "dash-table");
    var thead = el("thead"), htr = el("tr");
    fields.forEach(function (f, i) {
      var th = el("th", i === 0 ? "rowhead" : null, f); htr.appendChild(th);
    });
    thead.appendChild(htr); table.appendChild(thead);
    var tbody = el("tbody");
    rows.forEach(function (r) {
      var tr = el("tr");
      fields.forEach(function (f, i) {
        var td = el("td", i === 0 ? "rowhead" : null, r[f] == null ? "" : String(r[f]));
        tr.appendChild(td);
      });
      tr.addEventListener("click", function () {
        Array.prototype.forEach.call(tbody.children, function (c) { c.classList.remove("selected"); });
        tr.classList.add("selected");
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody); wrap.appendChild(table); body.appendChild(wrap);
  }

  function renderPivot(body, tile, page) {
    var cfg = tile.config, rows = filteredRows(tile, page);
    var res = computePivot(rows, cfg.row_field, cfg.col_field || null,
      cfg.value_field, cfg.statistic || "count",
      parseInt(cfg.max_rows, 10) || 50, parseInt(cfg.max_cols, 10) || 20);
    var hasCols = res.colKeys.length > 0;
    var showTotals = (cfg.show_totals !== false) && res.rowKeys.length > 0;
    var sel = selections(page.id)[tile.id]; var selKey = sel ? sel.key : null;
    var wrap = el("div", "dash-table-wrap");
    var table = el("table", "dash-table");

    var headers = [res.rowField || "(rows)"];
    if (hasCols) headers = headers.concat(res.colKeys);
    else headers.push((cfg.statistic || "count").replace(/^./, function (c) { return c.toUpperCase(); }));
    var totalsCol = hasCols && showTotals;
    if (totalsCol) headers.push("Total");

    var thead = el("thead"), htr = el("tr");
    headers.forEach(function (hLabel, ci) {
      var th = el("th", ci === 0 ? "rowhead" : null, hLabel);
      if (hasCols && ci >= 1 && ci <= res.colKeys.length) {
        var colKey = res.colKeys[ci - 1];
        if (colKey !== NULL_KEY && cfg.col_field) {
          th.className += " clickable";
          if (selKey === "col|" + colKey) th.classList.add("selected");
          th.addEventListener("click", function () {
            toggleSelection(page, tile.id, "col|" + colKey, [{ field: cfg.col_field, value: colKey }]);
          });
        }
      }
      htr.appendChild(th);
    });
    thead.appendChild(htr); table.appendChild(thead);

    var tbody = el("tbody");
    res.rowKeys.forEach(function (rk) {
      var tr = el("tr");
      var rh = el("td", "rowhead", rk);
      if (rk !== NULL_KEY && cfg.row_field) {
        rh.className += " clickable";
        if (selKey === "row|" + rk) rh.classList.add("selected");
        rh.addEventListener("click", function () {
          toggleSelection(page, tile.id, "row|" + rk, [{ field: cfg.row_field, value: rk }]);
        });
      }
      tr.appendChild(rh);
      if (hasCols) {
        res.colKeys.forEach(function (ck) {
          var v = res.cells[rk + SEP + ck];
          var td = el("td", null, v == null ? "" : fmtNum(v));
          if (rk !== NULL_KEY && ck !== NULL_KEY && cfg.row_field && cfg.col_field) {
            var k = "cell|" + rk + SEP + ck;
            td.className = "clickable";
            if (selKey === k) td.classList.add("selected");
            td.addEventListener("click", function () {
              toggleSelection(page, tile.id, k, [
                { field: cfg.row_field, value: rk }, { field: cfg.col_field, value: ck }]);
            });
          }
          tr.appendChild(td);
        });
        if (totalsCol) tr.appendChild(el("td", "rowhead", fmtNum(res.rowTotals[rk])));
      } else {
        tr.appendChild(el("td", null, fmtNum(res.rowTotals[rk])));
      }
      tbody.appendChild(tr);
    });
    if (showTotals) {
      var trt = el("tr");
      trt.appendChild(el("td", "rowhead", "Total"));
      if (hasCols) {
        res.colKeys.forEach(function (ck) { trt.appendChild(el("td", "rowhead", fmtNum(res.colTotals[ck]))); });
        if (totalsCol) trt.appendChild(el("td", "rowhead", res.grandTotal == null ? "" : fmtNum(res.grandTotal)));
      } else {
        trt.appendChild(el("td", "rowhead", res.grandTotal == null ? "" : fmtNum(res.grandTotal)));
      }
      tbody.appendChild(trt);
    }
    table.appendChild(tbody); wrap.appendChild(table); body.appendChild(wrap);
  }

  function renderSelector(body, tile, page) {
    var cfg = tile.config, layer = layerOf(tile), field = cfg.category_field;
    var box = el("div", "dash-selector");
    var select = el("select");
    select.appendChild(new Option("(All)", "(All)"));
    if (layer && field) {
      var seen = {};
      layer.features.forEach(function (r) { seen[String(r[field])] = 1; });
      Object.keys(seen).sort().forEach(function (v) { select.appendChild(new Option(v, v)); });
    }
    var cur = selections(page.id)[tile.id];
    select.value = cur ? cur.key : "(All)";
    select.addEventListener("change", function () {
      if (select.value === "(All)" || !field) setSelection(page, tile.id, null);
      else setSelection(page, tile.id, { key: select.value, pairs: [{ field: field, value: select.value }] });
    });
    box.appendChild(select); body.appendChild(box);
  }

  function renderText(body, tile) {
    var cfg = tile.config;
    var wrap = el("div", "dash-text");
    var inner = el("div", "inner");
    var heading = !!cfg.heading;
    var size = heading ? Math.round((THEME.title_size || 13) * 1.7) : (THEME.font_size || 11);
    inner.textContent = cfg.text || "";
    inner.style.fontSize = size + "px";
    inner.style.fontWeight = heading ? "700" : "400";
    inner.style.textAlign = cfg.align || "left";
    wrap.style.justifyContent = cfg.align === "center" ? "center" : (cfg.align === "right" ? "flex-end" : "flex-start");
    wrap.appendChild(inner); body.appendChild(wrap);
  }

  function renderImage(body, tile) {
    var wrap = el("div", "dash-image-wrap");
    if (tile.image_uri) {
      var img = el("img", "dash-image");
      img.src = tile.image_uri;
      if (tile.config.fit === "stretch") img.style.objectFit = "fill";
      wrap.appendChild(img);
    } else {
      wrap.appendChild(el("div", "dash-note", "Image unavailable"));
    }
    body.appendChild(wrap);
  }

  // ---- interactive Leaflet map ----------------------------------------
  var MAP_HOSTS = [];      // {host, tile} for the post-layout init pass
  var MAP_INSTANCES = [];  // live L.map objects, torn down on page switch

  function renderMap(body, tile) {
    var wrap = el("div", "dash-map-wrap");
    body.appendChild(wrap);
    if (tile.map && typeof L !== "undefined") {
      MAP_HOSTS.push({ host: wrap, tile: tile });
    } else if (tile.map && tile.map.fallback_image) {
      var img = el("img", "dash-map"); img.src = tile.map.fallback_image;
      wrap.appendChild(img);
    } else {
      wrap.appendChild(el("div", "dash-note", "Map — view in QGIS"));
    }
  }

  function featureCollection(layer) {
    var rows = layer.features || [];
    var geoms = layer.geometry || [];
    var feats = [];
    for (var i = 0; i < rows.length; i++) {
      if (!geoms[i]) continue;
      feats.push({ type: "Feature", geometry: geoms[i], properties: rows[i] });
    }
    return { type: "FeatureCollection", features: feats };
  }

  function identifyHtml(fields, props) {
    props = props || {};
    var names = (fields && fields.length) ? fields : Object.keys(props);
    var rows = names.map(function (name) {
      var v = props[name];
      if (v === null || v === undefined) v = "";
      return "<tr><th>" + escapeHtml(name) + "</th><td>" +
             escapeHtml(v) + "</td></tr>";
    }).join("");
    return '<div class="dash-identify"><table>' + rows + "</table></div>";
  }

  function initMap(host, tile) {
    var m = tile.map || {};
    var map;
    try {
      map = L.map(host);
    } catch (e) {
      if (m.fallback_image) {
        var img = el("img", "dash-map"); img.src = m.fallback_image;
        host.appendChild(img);
      }
      return;
    }
    var bm = m.basemap || {};
    var opts = { maxZoom: bm.max_zoom || 19 };
    if (bm.attribution) opts.attribution = bm.attribution;
    if (bm.subdomains) opts.subdomains = bm.subdomains;
    if (bm.tms) opts.tms = true;
    L.tileLayer(bm.url_template ||
      "https://tile.openstreetmap.org/{z}/{x}/{y}.png", opts).addTo(map);

    var bounds = null;
    (m.layer_ids || []).forEach(function (lid, idx) {
      var layer = DATA.layers[lid];
      if (!layer || !layer.geometry) return;
      var fc = featureCollection(layer);
      if (!fc.features.length) return;
      var col = color(idx);
      var gj = L.geoJSON(fc, {
        style: function () {
          return { color: col, weight: 2, fillColor: col, fillOpacity: 0.25 };
        },
        pointToLayer: function (f, latlng) {
          return L.circleMarker(latlng, { radius: 5, color: col,
            fillColor: col, fillOpacity: 0.85, weight: 1 });
        },
        onEachFeature: function (f, lyr) {
          lyr.bindPopup(identifyHtml(layer.fields, f.properties));
        }
      }).addTo(map);
      try {
        var b = gj.getBounds();
        if (b.isValid()) bounds = bounds ? bounds.extend(b) : b;
      } catch (e) {}
    });

    var ext = m.extent;
    if (ext && ext.length === 4) {
      map.fitBounds([[ext[1], ext[0]], [ext[3], ext[2]]]);
    } else if (bounds) {
      map.fitBounds(bounds);
    } else {
      map.setView([0, 0], 2);
    }
    map.invalidateSize();
    MAP_INSTANCES.push(map);
  }

  // ---- tile + page assembly --------------------------------------------
  var CHART_HOSTS = [];   // {host, tile, page} for the post-layout draw pass

  function renderTile(tile, page) {
    var node = el("div", "dash-tile" + (FULL_BLEED[tile.type] ? " full-bleed" : ""));
    var g = tile.grid || {};
    // free-form layout: tiles carry a logical pixel rect (x, y, w, h). The card
    // is inset by GAP on every side inside that footprint (matching the desktop
    // GridTile inset) so adjacent cards always keep their breathing room.
    node.style.position = "absolute";
    // GAP is the unified spacing S: the page reserves an S/2 margin inside each
    // edge and every card is inset S/2 inside its footprint, so a card flush to
    // the content edge sits S from the page edge and two touching footprints
    // show an S gap between their cards (matching the desktop canvas).
    node.style.left = (Number(g.x || 0) + GAP) + "px";
    node.style.top = (Number(g.y || 0) + GAP) + "px";
    node.style.width = Math.max(Number(g.w || 120) - GAP, 1) + "px";
    node.style.height = Math.max(Number(g.h || 120) - GAP, 1) + "px";

    var showTitle = !FULL_BLEED[tile.type] && tile.type !== "text" && tile.type !== "header";
    if (showTitle) {
      var title = tile.config.title || ELEMENT_LABELS[tile.type] || tile.type;
      node.appendChild(el("div", "dash-tile-title", title));
    }
    var body = el("div", "dash-tile-body");
    node.appendChild(body);

    if (tile.type === "indicator") renderIndicator(body, tile, page);
    else if (tile.type === "list") renderList(body, tile, page);
    else if (tile.type === "pivot") renderPivot(body, tile, page);
    else if (tile.type === "category_selector") renderSelector(body, tile, page);
    else if (tile.type === "text") renderText(body, tile);
    else if (tile.type === "header") renderHeader(body, tile);
    else if (tile.type === "image") renderImage(body, tile);
    else if (tile.type === "map") renderMap(body, tile);
    else if (tile.type === "chart") {
      var host = el("div"); host.style.width = "100%"; host.style.height = "100%";
      body.appendChild(host);
      CHART_HOSTS.push({ host: host, tile: tile, page: page });
    } else {
      body.appendChild(el("div", "dash-note", tile.type));
    }
    return node;
  }

  // ---- header (brand banner) tile --------------------------------------
  // Mirrors theme fallbacks so a chosen family degrades gracefully.
  var FONT_FALLBACK = '"Segoe UI", "Helvetica Neue", Arial, sans-serif';

  function renderHeader(body, tile) {
    var cfg = tile.config || {};
    var inner = el("div", "dash-banner-inner");
    var slot = cfg.logo_slot || "left";
    inner.style.flexDirection = (slot === "above" || slot === "below") ? "column" : "row";
    inner.style.height = "100%";
    if (cfg.logo_gap != null) inner.style.gap = (cfg.logo_gap | 0) + "px";
    var logoFirst = (slot === "left" || slot === "above");

    var logo = null;
    if (tile.logo_uri) {
      logo = el("img", "dash-banner-logo");
      logo.src = tile.logo_uri;
      var sz = Number(cfg.logo_size || 40);
      logo.style.width = sz + "px";
      logo.style.height = sz + "px";
    }
    var title = el("div", "dash-banner-title", cfg.title || "");
    if (cfg.font_family) title.style.fontFamily = '"' + cfg.font_family + '", ' + FONT_FALLBACK;
    title.style.fontSize = Number(cfg.font_size || 22) + "px";
    title.style.textAlign = cfg.align || "left";
    title.style.flex = "1 1 auto";

    if (logo && logoFirst) inner.appendChild(logo);
    inner.appendChild(title);
    if (logo && !logoFirst) inner.appendChild(logo);
    body.appendChild(inner);
  }

  function buildGrid(page) {
    var grid = el("div", "dash-grid");
    // size the surface to the content extent so it scrolls when it overflows
    var maxR = 0, maxB = 0;
    page.tiles.forEach(function (tile) {
      var g = tile.grid || {};
      maxR = Math.max(maxR, Number(g.x || 0) + Math.max(Number(g.w || 0), 0));
      maxB = Math.max(maxB, Number(g.y || 0) + Math.max(Number(g.h || 0), 0));
    });
    // grow the surface by one spacing beyond the content so the right/bottom
    // page margins match the left/top margins and the inter-card gaps
    grid.style.width = (maxR + GAP) + "px";
    grid.style.height = (maxB + GAP) + "px";
    page.tiles.forEach(function (tile) { grid.appendChild(renderTile(tile, page)); });
    return grid;
  }

  function renderPage(page) {
    CHART_HOSTS = [];
    MAP_INSTANCES.forEach(function (mp) { try { mp.remove(); } catch (e) {} });
    MAP_INSTANCES = [];
    MAP_HOSTS = [];
    var area = document.getElementById("page-area");
    area.innerHTML = "";
    var wrap = el("div", "dash-pagewrap");
    var scroll = el("div", "dash-scroll");
    scroll.appendChild(buildGrid(page));
    wrap.appendChild(scroll);
    area.appendChild(wrap);
    // charts and maps need their host measured after layout
    requestAnimationFrame(function () {
      CHART_HOSTS.forEach(function (c) { drawChart(c.host, c.tile, c.page); });
      MAP_HOSTS.forEach(function (h) { initMap(h.host, h.tile); });
    });
  }

  // ---- top-level app ----------------------------------------------------
  var ACTIVE_PAGE = null;

  function showPage(page) {
    ACTIVE_PAGE = page;
    Array.prototype.forEach.call(document.querySelectorAll(".dash-tab"), function (t) {
      t.classList.toggle("active", t.getAttribute("data-id") === page.id);
    });
    renderPage(page);
  }

  function build() {
    var app = document.getElementById("app");
    app.innerHTML = "";
    if (DATA.pages.length > 1) {
      var tabs = el("div", "dash-tabs");
      DATA.pages.forEach(function (page) {
        var tab = el("button", "dash-tab", page.title);
        tab.setAttribute("data-id", page.id);
        tab.addEventListener("click", function () { showPage(page); });
        tabs.appendChild(tab);
      });
      app.appendChild(tabs);
    }
    var area = el("div", "dash-page-area");
    area.id = "page-area";
    app.appendChild(area);

    var start = DATA.pages.filter(function (p) { return p.id === DATA.active_page; })[0] || DATA.pages[0];
    if (start) showPage(start);
  }

  var resizeTimer = null;
  window.addEventListener("resize", function () {
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      CHART_HOSTS.forEach(function (c) { drawChart(c.host, c.tile, c.page); });
      MAP_INSTANCES.forEach(function (mp) {
        try { mp.invalidateSize(); } catch (e) {}
      });
    }, 150);
  });

  if (DATA.pages && DATA.pages.length) build();
  else document.getElementById("app").appendChild(el("div", "dash-note", "Empty dashboard."));
})();
