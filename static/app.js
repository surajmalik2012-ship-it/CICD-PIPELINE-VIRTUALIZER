(() => {
  "use strict";

  // ---- layout constants for the graph drawing
  const NODE_W = 184, NODE_H = 66, COL_GAP = 44, ROW_GAP = 24, PAD = 24, HEAD = 30;
  const SVG_NS = "http://www.w3.org/2000/svg";

  const $ = (id) => document.getElementById(id);
  const source = $("source"), svg = $("graph"), errorsBox = $("errors"), emptyBox = $("empty");
  const summary = $("summary"), sampleSelect = $("sample"), critBox = $("crit");

  const state = { graph: null, run: null, willFail: new Set(), timer: null };

  // ---------------------------------------------------------------- API
  async function post(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error((data.errors || ["Something went wrong."]).join("\n"));
    return data;
  }

  function showErrors(messages) {
    errorsBox.replaceChildren();
    if (!messages.length) { errorsBox.hidden = true; return; }
    const title = document.createElement("p");
    title.textContent = "Fix this to see the graph:";
    const list = document.createElement("ul");
    messages.forEach((m) => { const li = document.createElement("li"); li.textContent = m; list.append(li); });
    errorsBox.append(title, list);
    errorsBox.hidden = false;
  }

  async function analyze() {
    stopAnimation();
    state.run = null;
    try {
      const data = await post("/api/analyze", { text: source.value });
      state.graph = data.graph;
      // forget "will fail" marks for jobs that no longer exist
      const ids = new Set(state.graph.jobs.map((j) => j.id));
      state.willFail = new Set([...state.willFail].filter((id) => ids.has(id)));
      showErrors([]);
    } catch (err) {
      state.graph = null;
      showErrors(err.message.split("\n"));
    }
    render();
  }

  async function runSimulation() {
    if (!state.graph) return;
    stopAnimation();
    try {
      const data = await post("/api/simulate", { text: source.value, fail: [...state.willFail] });
      state.graph = data.graph;
      state.run = data.run;
      showErrors([]);
      animate(data.run);
    } catch (err) {
      showErrors(err.message.split("\n"));
    }
  }

  // ------------------------------------------------------------ drawing
  function el(name, attrs = {}, text) {
    const node = document.createElementNS(SVG_NS, name);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function clip(text, max) { return text.length > max ? text.slice(0, max - 1) + "…" : text; }

  function positions(graph) {
    const rows = {};
    const pos = {};
    graph.jobs.forEach((j) => {
      const row = rows[j.stage] = (rows[j.stage] ?? -1) + 1;
      pos[j.id] = { x: PAD + j.stage * (NODE_W + COL_GAP), y: PAD + HEAD + row * (NODE_H + ROW_GAP) };
    });
    return pos;
  }

  function criticalEdgeSet(graph) {
    const set = new Set();
    for (let i = 1; i < graph.critical_path.length; i++) set.add(graph.critical_path[i - 1] + ">" + graph.critical_path[i]);
    return set;
  }

  // `view` maps job id -> {status} for what to show right now (animation) or the final run.
  function render(view) {
    svg.replaceChildren();
    const g = state.graph;
    emptyBox.hidden = !!g || !errorsBox.hidden;
    svg.parentElement.hidden = !g;
    if (!g) { renderSummary(); return; }

    const pos = positions(g);
    const maxRow = Math.max(...Object.values(pos).map((p) => p.y)) + NODE_H + PAD;
    const totalW = PAD * 2 + g.stage_count * NODE_W + (g.stage_count - 1) * COL_GAP;
    svg.setAttribute("viewBox", `0 0 ${totalW} ${maxRow}`);
    svg.setAttribute("width", totalW);  // CSS max-width:100% shrinks it on narrow screens
    svg.setAttribute("height", maxRow);

    for (let s = 0; s < g.stage_count; s++) {
      svg.append(el("text", { class: "stage", x: PAD + s * (NODE_W + COL_GAP), y: PAD + 8 }, "Stage " + (s + 1)));
    }

    const showCrit = critBox.checked;
    const critEdges = criticalEdgeSet(g);
    g.edges.forEach((e) => {
      const a = pos[e.from], b = pos[e.to];
      const x1 = a.x + NODE_W, y1 = a.y + NODE_H / 2, x2 = b.x, y2 = b.y + NODE_H / 2;
      const mid = (x1 + x2) / 2;
      const isCrit = critEdges.has(e.from + ">" + e.to);
      const cls = "edge" + (showCrit && isCrit ? " critical" : "") + (showCrit && !isCrit ? " dim" : "");
      svg.append(el("path", { class: cls, d: `M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}` }));
    });

    g.jobs.forEach((j) => {
      const p = pos[j.id];
      const status = view ? view[j.id]?.status : state.run?.jobs[j.id]?.status;
      const cls = ["node"];
      if (showCrit && j.on_critical_path) cls.push("critical");
      if (status) cls.push("st-" + status);
      if (state.willFail.has(j.id)) cls.push("will-fail");
      const node = el("g", {
        class: cls.join(" "), transform: `translate(${p.x},${p.y})`, tabindex: "0", role: "button",
        "aria-label": `${j.name}, ${j.minutes} minutes${status ? ", " + status : ""}${state.willFail.has(j.id) ? ", set to fail" : ""}`,
      });
      node.append(
        el("rect", { class: "card", width: NODE_W, height: NODE_H, rx: 6 }),
        el("rect", { class: "bar", width: 8, height: NODE_H, rx: 3 }),
        el("text", { class: "title", x: 20, y: 25 }, clip(j.name, 21)),
        el("text", { class: "meta", x: 20, y: 44 }, metaLine(j, status)),
        el("title", {}, `${j.name} (${j.id})\nRuns on: ${j.runs_on}\nSteps: ${j.steps}`),
      );
      const toggle = () => { toggleFail(j.id); };
      node.addEventListener("click", toggle);
      node.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); toggle(); } });
      svg.append(node);
    });
    renderSummary();
  }

  function metaLine(j, status) {
    const parts = [`${j.minutes} min`];
    if (j.matrix_size > 1) parts.push(`${j.matrix_size} combos`);
    if (j.condition) parts.push(`if ${clip(j.condition, 10)}`);
    if (status && status !== "pending") parts.push(status === "success" ? "passed" : status);
    return parts.join("  ·  ");
  }

  function toggleFail(id) {
    if (state.willFail.has(id)) state.willFail.delete(id); else state.willFail.add(id);
    stopAnimation();
    if (state.run) runSimulation(); else render();
  }

  // ---------------------------------------------------------- animation
  function stopAnimation() { if (state.timer) { cancelAnimationFrame(state.timer); state.timer = null; } }

  function animate(run) {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce || run.wall_clock_minutes === 0) { render(); return; }
    const total = Math.min(5000, Math.max(2000, run.wall_clock_minutes * 250)); // ms
    const t0 = performance.now();
    const step = (now) => {
      const t = ((now - t0) / total) * run.wall_clock_minutes; // simulated minutes
      const view = {};
      for (const [id, r] of Object.entries(run.jobs)) {
        if (r.status === "skipped") view[id] = { status: t >= r.start ? "skipped" : "pending" };
        else if (t >= r.end) view[id] = { status: r.status };
        else view[id] = { status: t >= r.start ? "running" : "pending" };
      }
      if (t >= run.wall_clock_minutes) { state.timer = null; render(); return; }
      render(view);
      state.timer = requestAnimationFrame(step);
    };
    state.timer = requestAnimationFrame(step);
  }

  // ------------------------------------------------------------ summary
  function stat(value, label, cls = "") {
    const box = document.createElement("div");
    box.className = "stat " + cls;
    const b = document.createElement("b"); b.textContent = value;
    const s = document.createElement("span"); s.textContent = label;
    box.append(b, s);
    return box;
  }

  function renderSummary() {
    summary.replaceChildren();
    const g = state.graph;
    if (!g) return;
    const names = (ids) => ids.map((id) => g.jobs.find((j) => j.id === id)?.name ?? id).join(", ");
    summary.append(
      stat(g.jobs.length, "jobs"),
      stat(g.stage_count, "stages"),
      stat(g.max_parallel_jobs, "most jobs running together"),
      stat(g.critical_minutes + " min", "fastest possible finish"),
    );
    const r = state.run;
    if (r) {
      summary.append(
        stat(r.overall === "failed" ? "Failed" : "Passed", "simulated run", "verdict-" + r.overall),
        stat(r.wall_clock_minutes + " min", "run time with parallel jobs"),
        stat(r.minutes_saved_by_parallelism + " min", "saved by running jobs together"),
      );
      if (r.failed_jobs.length) summary.append(stat(names(r.failed_jobs), "failed", "wide"));
      if (r.skipped_jobs.length) summary.append(stat(names(r.skipped_jobs), "skipped because a job they depend on did not pass", "wide"));
    }
    summary.append(stat(names(g.critical_path), "critical path: the chain that decides the total time", "wide"));
  }

  // -------------------------------------------------------------- setup
  async function loadSample(name) {
    const res = await fetch("/api/samples/" + encodeURIComponent(name));
    source.value = await res.text();
    state.willFail.clear();
    analyze();
  }

  async function init() {
    const names = await (await fetch("/api/samples")).json();
    names.forEach((n) => {
      const o = document.createElement("option");
      o.value = n; o.textContent = n.replace(/-/g, " ");
      sampleSelect.append(o);
    });
    sampleSelect.addEventListener("change", () => loadSample(sampleSelect.value));
    let debounce;
    source.addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(analyze, 350); });
    $("run").addEventListener("click", runSimulation);
    $("reset").addEventListener("click", () => { state.willFail.clear(); stopAnimation(); state.run = null; render(); });
    critBox.addEventListener("change", () => render());
    if (names.length) { sampleSelect.value = names.includes("web-app") ? "web-app" : names[0]; loadSample(sampleSelect.value); }
  }

  init();
})();
