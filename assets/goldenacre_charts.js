/* Golden Acre chart library - d3 v7.
 *
 * Design rules these charts follow, and the reasons, so later edits do not
 * quietly undo them:
 *
 * 1. COLOUR CARRIES ONE MEANING PER CHART. The Plotly versions coloured
 *    retailer bars by retailer, which the axis label already said - a whole
 *    visual channel spent on nothing. Here colour is reserved for direction of
 *    travel (growth/decline) wherever change matters, and used for identity
 *    only where identity is genuinely the subject.
 * 2. CHANGE IS DRAWN, NOT CAPTIONED. Every dataset behind these charts carries
 *    a year-on-year figure that the old charts printed as a text label at best.
 *    The dumbbell and the delta badges put it in the geometry.
 * 3. DIRECT LABELS INSTEAD OF LEGENDS. A legend makes the reader look away and
 *    match colours. Series are labelled where they end.
 * 4. DIRECTION IS NEVER COLOUR-ONLY. Up and down carry an arrow as well as a
 *    hue, so the charts survive colour-blind readers and greyscale printing.
 * 5. NO ZERO-BASELINE VIOLATIONS. Bars and lollipops start at zero. Where a
 *    zero baseline is meaningless (price positioning), the mark is a dot on a
 *    scale, not a bar.
 */
(function () {
  const F = {
    gbp(v) {
      const a = Math.abs(v);
      if (a < 0.005) return "£0";        // axis origin, not a price of £0.00
      if (a >= 1e9) return "£" + (v / 1e9).toFixed(2) + "bn";
      if (a >= 1e6) return "£" + (v / 1e6).toFixed(1) + "m";
      if (a >= 1e3) return "£" + Math.round(v / 1e3) + "k";
      // Prices live down here. Rounding £2.05 to "£2" loses the entire point of
      // a price-positioning chart, where the spread between brands is pennies.
      if (a >= 10) return "£" + Math.round(v);
      return "£" + v.toFixed(2);
    },
    pct(v, dp) { return (v == null ? "-" : v.toFixed(dp == null ? 1 : dp) + "%"); },
    signed(v, dp, unit) {
      if (v == null) return "-";
      const s = v > 0 ? "+" : "";
      return s + v.toFixed(dp == null ? 1 : dp) + (unit || "%");
    },
    arrow(v) { return v == null ? "" : (v > 0 ? "↑" : (v < 0 ? "↓" : "→")); },
  };

  function tooltip(root) {
    const el = root.append("div").attr("class", "ga-tip").style("opacity", 0);
    return {
      show(html, x, y) {
        el.html(html).style("opacity", 1)
          .style("left", x + "px").style("top", y + "px");
      },
      hide() { el.style("opacity", 0); },
    };
  }

  function frame(sel, cfg, margin) {
    const width = sel.node().clientWidth || cfg.width || 720;
    const height = cfg.height || 320;
    const svg = sel.append("svg")
      .attr("width", width).attr("height", height)
      .attr("viewBox", `0 0 ${width} ${height}`)
      .attr("role", "img");
    const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
    return {
      svg, g, width, height,
      iw: width - margin.left - margin.right,
      ih: height - margin.top - margin.bottom,
    };
  }

  /* ------------------------------------------------------------------ *
   * DUMBBELL - last year to this year, on one row per item.
   * Replaces a bar of the current value with the year-ago value shown as
   * a hollow dot, the current as a filled one, and the gap drawn between
   * them coloured by direction. Level and change become one read.
   * ------------------------------------------------------------------ */
  function dumbbell(sel, cfg) {
    const C = cfg.colors;
    const m = { top: 14, right: 96, bottom: 28, left: cfg.labelWidth || 108 };
    const f = frame(sel, cfg, m);
    const data = cfg.data.slice().sort((a, b) => d3.descending(a.now, b.now));
    const maxV = d3.max(data, d => Math.max(d.now, d.before)) || 1;
    const x = d3.scaleLinear().domain([0, maxV * 1.08]).range([0, f.iw]);
    const y = d3.scalePoint().domain(data.map(d => d.label)).range([0, f.ih]).padding(0.6);
    const tip = tooltip(sel);

    f.g.append("g").attr("transform", `translate(0,${f.ih})`)
      .call(d3.axisBottom(x).ticks(4).tickFormat(cfg.unit === "pct" ? (v => v + "%") : F.gbp).tickSize(-f.ih))
      .call(g => g.select(".domain").remove())
      .call(g => g.selectAll(".tick line").attr("stroke", C.grid))
      .call(g => g.selectAll("text").attr("fill", C.textFaint).attr("font-size", 10));

    const row = f.g.selectAll(".row").data(data).join("g")
      .attr("class", "row").attr("transform", d => `translate(0,${y(d.label)})`);

    row.append("text").attr("x", -12).attr("dy", "0.32em").attr("text-anchor", "end")
      .attr("fill", C.text).attr("font-size", 12).attr("font-weight", 600)
      .text(d => d.label);

    // the connector IS the change - thickness and colour both say so
    row.append("line")
      .attr("x1", d => x(d.before)).attr("x2", d => x(d.now))
      .attr("stroke", d => (d.now >= d.before ? C.positive : C.negative))
      .attr("stroke-width", 3).attr("stroke-linecap", "round").attr("opacity", 0.55);

    row.append("circle").attr("cx", d => x(d.before)).attr("r", 4.5)
      .attr("fill", C.card).attr("stroke", C.textFaint).attr("stroke-width", 1.5);

    row.append("circle").attr("cx", d => x(d.now)).attr("r", 5.5)
      .attr("fill", d => (d.now >= d.before ? C.positive : C.negative));

    row.append("text")
      .attr("x", f.iw + 10).attr("dy", "0.32em")
      .attr("fill", d => (d.now >= d.before ? C.positive : C.negative))
      .attr("font-size", 11.5).attr("font-weight", 700)
      .text(d => (d.delta == null ? "" : F.arrow(d.delta) + " " + F.signed(d.delta, cfg.deltaDp, cfg.deltaUnit)));

    row.append("rect").attr("x", -m.left).attr("y", -12).attr("width", f.iw + m.left).attr("height", 24)
      .attr("fill", "transparent")
      .on("mousemove", function (e, d) {
        tip.show(
          `<b>${d.label}</b><br>${cfg.nowLabel || "This year"}: ${cfg.unit === "pct" ? F.pct(d.now, 2) : F.gbp(d.now)}` +
          `<br>${cfg.beforeLabel || "Year ago"}: ${cfg.unit === "pct" ? F.pct(d.before, 2) : F.gbp(d.before)}` +
          (d.delta == null ? "" : `<br>Change: ${F.signed(d.delta, cfg.deltaDp, cfg.deltaUnit)}`),
          e.offsetX + 14, e.offsetY - 8);
      })
      .on("mouseleave", tip.hide);

    // one legend line, because hollow-vs-filled is not self-evident
    f.svg.append("text").attr("x", m.left).attr("y", f.height - 4)
      .attr("fill", C.textFaint).attr("font-size", 10)
      .text(`○ ${cfg.beforeLabel || "year ago"}   ● ${cfg.nowLabel || "now"}`);
  }

  /* ------------------------------------------------------------------ *
   * LOLLIPOP - a ranking. Less ink than a bar at the same accuracy, which
   * leaves room for a year-on-year badge per row, and lets one row be
   * highlighted without the highlight fighting a slab of colour.
   * ------------------------------------------------------------------ */
  function lollipop(sel, cfg) {
    const C = cfg.colors;
    const m = { top: 12, right: cfg.showDelta ? 84 : 56, bottom: 28, left: cfg.labelWidth || 150 };
    const f = frame(sel, cfg, m);
    const data = cfg.data;
    const x = d3.scaleLinear().domain([0, (d3.max(data, d => d.value) || 1) * 1.1]).range([0, f.iw]);
    const y = d3.scaleBand().domain(data.map(d => d.label)).range([0, f.ih]).padding(0.28);
    const tip = tooltip(sel);

    f.g.append("g").attr("transform", `translate(0,${f.ih})`)
      .call(d3.axisBottom(x).ticks(4).tickFormat(cfg.unit === "gbp" ? F.gbp : (v => v)).tickSize(-f.ih))
      .call(g => g.select(".domain").remove())
      .call(g => g.selectAll(".tick line").attr("stroke", C.grid))
      .call(g => g.selectAll("text").attr("fill", C.textFaint).attr("font-size", 10));

    const row = f.g.selectAll(".row").data(data).join("g")
      .attr("class", "row")
      .attr("transform", d => `translate(0,${y(d.label) + y.bandwidth() / 2})`);

    row.append("text").attr("x", -10).attr("dy", "0.32em").attr("text-anchor", "end")
      .attr("fill", d => (d.highlight ? C.text : C.textMuted))
      .attr("font-size", 12).attr("font-weight", d => (d.highlight ? 700 : 500))
      .text(d => d.label);

    row.append("line").attr("x1", 0).attr("x2", d => x(d.value))
      .attr("stroke", d => (d.highlight ? C.gold : C.primary))
      .attr("stroke-width", d => (d.highlight ? 3 : 2)).attr("opacity", d => (d.highlight ? 0.9 : 0.45));

    row.append("circle").attr("cx", d => x(d.value)).attr("r", d => (d.highlight ? 6.5 : 5))
      .attr("fill", d => (d.highlight ? C.gold : C.primary))
      .attr("stroke", C.card).attr("stroke-width", d => (d.highlight ? 2 : 0));

    row.append("text").attr("x", d => x(d.value) + 12).attr("dy", "0.32em")
      .attr("fill", C.textMuted).attr("font-size", 11)
      .text(d => (cfg.unit === "gbp" ? F.gbp(d.value) : d.value.toFixed(cfg.valueDp == null ? 2 : cfg.valueDp)));

    if (cfg.showDelta) {
      row.append("text").attr("x", f.iw + 8).attr("dy", "0.32em")
        .attr("fill", d => (d.delta == null ? C.textFaint : (d.delta > 0 ? C.positive : C.negative)))
        .attr("font-size", 11).attr("font-weight", 600)
        .text(d => (d.delta == null ? "" : F.arrow(d.delta) + " " + F.signed(d.delta, 1)));
    }

    row.append("rect").attr("x", -m.left).attr("y", -y.bandwidth() / 2)
      .attr("width", f.iw + m.left).attr("height", y.bandwidth()).attr("fill", "transparent")
      .on("mousemove", function (e, d) {
        tip.show(`<b>${d.label}</b><br>${cfg.unit === "gbp" ? F.gbp(d.value) : d.value}` +
                 (d.delta == null ? "" : `<br>YoY: ${F.signed(d.delta, 1)}`) +
                 (d.note ? `<br><i>${d.note}</i>` : ""),
                 e.offsetX + 14, e.offsetY - 8);
      })
      .on("mouseleave", tip.hide);
  }

  /* ------------------------------------------------------------------ *
   * TREEMAP - area is size, colour is growth on a diverging scale about
   * zero. Labels are drawn only where the tile can hold them, rather than
   * being clipped into unreadable fragments.
   * ------------------------------------------------------------------ */
  function treemap(sel, cfg) {
    const C = cfg.colors;
    const width = sel.node().clientWidth || 720;
    const height = cfg.height || 420;
    const tip = tooltip(sel);
    const root = d3.hierarchy({ children: cfg.data })
      .sum(d => d.value)
      .sort((a, b) => b.value - a.value);
    d3.treemap().size([width, height]).paddingInner(2).paddingTop(0).round(true)(root);

    const lim = d3.max(cfg.data, d => Math.abs(d.growth == null ? 0 : d.growth)) || 1;
    const color = d3.scaleDiverging(d3.interpolateRdYlGn).domain([-lim, 0, lim]);

    const svg = sel.append("svg").attr("width", width).attr("height", height);
    const node = svg.selectAll("g").data(root.leaves()).join("g")
      .attr("transform", d => `translate(${d.x0},${d.y0})`);

    node.append("rect")
      .attr("width", d => d.x1 - d.x0).attr("height", d => d.y1 - d.y0)
      .attr("rx", 3)
      .attr("fill", d => (d.data.growth == null ? C.surface2 : color(d.data.growth)))
      .attr("stroke", C.card).attr("stroke-width", 1);

    node.append("clipPath").attr("id", (d, i) => "clip" + i)
      .append("rect").attr("width", d => Math.max(0, d.x1 - d.x0 - 8)).attr("height", d => Math.max(0, d.y1 - d.y0 - 6));

    const label = node.filter(d => (d.x1 - d.x0) > 58 && (d.y1 - d.y0) > 28)
      .append("text").attr("clip-path", (d, i) => `url(#clip${i})`)
      .attr("transform", "translate(6,6)");
    label.append("tspan").attr("x", 0).attr("y", 11)
      .attr("font-size", 11).attr("font-weight", 700).attr("fill", "#14141a")
      .text(d => d.data.label);
    label.filter(d => (d.y1 - d.y0) > 44).append("tspan").attr("x", 0).attr("y", 25)
      .attr("font-size", 10).attr("fill", "#14141a").attr("opacity", 0.75)
      .text(d => F.gbp(d.data.value) + (d.data.growth == null ? "" : "  " + F.arrow(d.data.growth) + F.signed(d.data.growth, 0)));

    node.on("mousemove", function (e, d) {
      tip.show(`<b>${d.data.label}</b><br>${d.data.group || ""}<br>${F.gbp(d.data.value)}` +
               (d.data.growth == null ? "" : `<br>YoY: ${F.signed(d.data.growth, 1)}`),
               e.offsetX + 14, e.offsetY - 8);
    }).on("mouseleave", tip.hide);

    // a diverging scale needs its midpoint stated or the hues mean nothing
    const lw = 150, lx = width - lw - 6;
    const defs = svg.append("defs");
    const grad = defs.append("linearGradient").attr("id", "gagrad");
    d3.range(0, 1.01, 0.1).forEach(t => grad.append("stop")
      .attr("offset", (t * 100) + "%").attr("stop-color", color(-lim + t * 2 * lim)));
    svg.append("rect").attr("x", lx).attr("y", height - 16).attr("width", lw).attr("height", 7)
      .attr("fill", "url(#gagrad)").attr("rx", 3);
    svg.append("text").attr("x", lx).attr("y", height - 20).attr("font-size", 9).attr("fill", C.textFaint)
      .text(`declining`);
    svg.append("text").attr("x", lx + lw).attr("y", height - 20).attr("text-anchor", "end")
      .attr("font-size", 9).attr("fill", C.textFaint).text(`growing`);
  }

  /* ------------------------------------------------------------------ *
   * MULTILINE - series labelled where they end, so the eye never leaves
   * the plot to consult a key.
   * ------------------------------------------------------------------ */
  function multiline(sel, cfg) {
    const C = cfg.colors;
    const m = { top: 16, right: 108, bottom: 26, left: 56 };
    const f = frame(sel, cfg, m);
    const series = cfg.series;
    const parse = d3.utcParse("%Y-%m-%d");
    series.forEach(s => s.points.forEach(p => { p.d = parse(p.x) || new Date(p.x); }));
    const all = series.flatMap(s => s.points);
    const x = d3.scaleUtc().domain(d3.extent(all, p => p.d)).range([0, f.iw]);
    const y = d3.scaleLinear().domain([0, d3.max(all, p => p.y) * 1.08]).nice().range([f.ih, 0]);
    const tip = tooltip(sel);

    f.g.append("g").call(d3.axisLeft(y).ticks(5).tickFormat(F.gbp).tickSize(-f.iw))
      .call(g => g.select(".domain").remove())
      .call(g => g.selectAll(".tick line").attr("stroke", C.grid))
      .call(g => g.selectAll("text").attr("fill", C.textFaint).attr("font-size", 10));
    f.g.append("g").attr("transform", `translate(0,${f.ih})`)
      .call(d3.axisBottom(x).ticks(6).tickSizeOuter(0))
      .call(g => g.select(".domain").attr("stroke", C.grid))
      .call(g => g.selectAll("text").attr("fill", C.textFaint).attr("font-size", 10));

    const line = d3.line().x(p => x(p.d)).y(p => y(p.y)).curve(d3.curveMonotoneX);
    series.forEach(s => {
      f.g.append("path").datum(s.points).attr("fill", "none")
        .attr("stroke", s.color || C.primary).attr("stroke-width", s.emphasis ? 2.6 : 1.8)
        .attr("opacity", s.emphasis ? 1 : 0.85).attr("d", line);
      const last = s.points[s.points.length - 1];
      f.g.append("circle").attr("cx", x(last.d)).attr("cy", y(last.y)).attr("r", 3.5)
        .attr("fill", s.color || C.primary);
      f.g.append("text").attr("x", x(last.d) + 8).attr("y", y(last.y)).attr("dy", "0.32em")
        .attr("fill", s.color || C.primary).attr("font-size", 11).attr("font-weight", 700)
        .text(s.name);
    });

    f.g.append("rect").attr("width", f.iw).attr("height", f.ih).attr("fill", "transparent")
      .on("mousemove", function (e) {
        const xm = x.invert(e.offsetX - m.left);
        const rows = series.map(s => {
          const p = s.points.reduce((a, b) => (Math.abs(b.d - xm) < Math.abs(a.d - xm) ? b : a));
          return `<span style="color:${s.color || C.primary}">●</span> ${s.name}: ${F.gbp(p.y)}`;
        });
        tip.show(rows.join("<br>"), e.offsetX + 14, e.offsetY - 8);
      })
      .on("mouseleave", tip.hide);
  }

  const TYPES = { dumbbell, lollipop, treemap, multiline };

  window.renderGoldenAcreChart = function (spec) {
    const sel = d3.select("#chart");
    sel.selectAll("*").remove();
    const fn = TYPES[spec.type];
    if (!fn) { sel.append("div").text("Unknown chart type: " + spec.type); return; }
    fn(sel, spec);
  };
})();
