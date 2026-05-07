"""
Dashboard generator for med-insights.

Reads cluster results and current ChromaDB state, then writes
dashboard/index.html — a single self-contained file with embedded data
and vanilla JS + D3 visualizations. No build step, no server required.

Regenerated every pipeline run so it always reflects the latest state.
"""

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from pipeline.clusterer import ClusterResult


_SENTIMENT_COLORS = {
    "frustrated":     "#ef4444",   # red
    "uncertain":      "#f59e0b",   # amber
    "seeking_advice": "#3b82f6",   # blue
    "informational":  "#10b981",   # green
    "debating":       "#8b5cf6",   # purple
}

_SENTIMENT_EMOJI = {
    "frustrated":     "😤",
    "uncertain":      "🤔",
    "seeking_advice": "🙋",
    "informational":  "📋",
    "debating":       "⚖️",
}


def _clusters_to_json(clusters: list[ClusterResult]) -> str:
    """Serialize cluster list for embedding into the HTML."""
    data = []
    for c in clusters:
        if c.cluster_id == -1:
            continue   # omit noise cluster from viz
        data.append({
            "id":                c.cluster_id,
            "label":             c.label,
            "post_count":        c.post_count,
            "dominant_sentiment": c.dominant_sentiment,
            "color":             _SENTIMENT_COLORS.get(c.dominant_sentiment, "#6b7280"),
            "communities":       c.communities,
            "top_unmet_needs":   c.top_unmet_needs[:3],
            "sample_posts":      c.sample_posts,   # top 10 by comment_count, fixed size
            "x":                 c.x,
            "y":                 c.y,
        })
    return json.dumps(data, indent=2)


def _specialty_breakdown_json(clusters: list[ClusterResult]) -> str:
    counts: Counter = Counter()
    for c in clusters:
        if c.cluster_id == -1:
            continue
        for comm in c.communities:
            counts[comm] += c.post_count // max(len(c.communities), 1)
    return json.dumps([{"community": k, "count": v} for k, v in counts.most_common()])


def _sentiment_breakdown_json(clusters: list[ClusterResult]) -> str:
    counts: Counter = Counter()
    for c in clusters:
        if c.cluster_id == -1:
            continue
        counts[c.dominant_sentiment] += c.post_count
    total = sum(counts.values()) or 1
    return json.dumps([
        {
            "sentiment": k,
            "count": v,
            "pct": round(v / total * 100),
            "color": _SENTIMENT_COLORS.get(k, "#6b7280"),
            "emoji": _SENTIMENT_EMOJI.get(k, "💬"),
        }
        for k, v in counts.most_common()
    ])


def generate(clusters: list[ClusterResult], output_path: str = "dashboard/index.html") -> str:
    """
    Generate the dashboard HTML and write it to output_path.
    Returns the path written.
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    n_clusters = sum(1 for c in clusters if c.cluster_id != -1)

    # Pull true total from ChromaDB (includes posts added after last cluster run)
    import chromadb
    import config as _config
    _chroma = chromadb.PersistentClient(path=_config.CHROMA_DIR)
    _col = _chroma.get_or_create_collection(_config.CHROMA_COLLECTION)
    total_posts = _col.count()

    clusters_json    = _clusters_to_json(clusters)
    specialty_json   = _specialty_breakdown_json(clusters)
    sentiment_json   = _sentiment_breakdown_json(clusters)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>med-insights dashboard — {date_str}</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: #f8fafc; color: #1e293b; min-height: 100vh; }}
  header {{ padding: 12px 32px; border-bottom: 1px solid #e2e8f0; background: #fff;
            display: flex; align-items: center; gap: 28px; }}
  header h1 {{ font-size: 1.1rem; font-weight: 700; color: #0f172a; flex-shrink: 0; }}
  .sources {{ display: flex; align-items: center; gap: 6px; flex-shrink: 0; }}
  .sources-label {{ font-size: 0.65rem; color: #94a3b8; text-transform: uppercase;
                    letter-spacing: 0.08em; margin-right: 2px; }}
  .source-badge {{ display: flex; align-items: center; gap: 5px; background: #fff5f0;
                   border: 1px solid #fed7c7; border-radius: 6px; padding: 3px 8px; }}
  .source-badge svg {{ width: 16px; height: 16px; flex-shrink: 0; }}
  .source-badge span {{ font-size: 0.75rem; color: #FF4500; font-weight: 500; }}
  .header-stats {{ display: flex; gap: 20px; flex: 1; }}
  .stat {{ display: flex; align-items: baseline; gap: 5px; }}
  .stat .value {{ font-size: 1.05rem; font-weight: 700; color: #0284c7; }}
  .stat .label {{ font-size: 0.7rem; color: #94a3b8; text-transform: uppercase;
                  letter-spacing: 0.05em; }}
  header .meta {{ font-size: 0.75rem; color: #94a3b8; flex-shrink: 0; }}
  .main {{ display: grid; grid-template-columns: 1fr 320px;
           gap: 0; height: calc(100vh - 53px); }}
  .chart-area {{ padding: 20px 32px; overflow: hidden; background: #f8fafc; }}
  .chart-area h2 {{ font-size: 0.9rem; color: #94a3b8; text-transform: uppercase;
                    letter-spacing: 0.08em; margin-bottom: 16px; }}
  #bubble-chart {{ width: 100%; height: calc(100% - 36px); }}
  .sidebar {{ border-left: 1px solid #e2e8f0; background: #fff;
              display: flex; flex-direction: column; overflow: hidden; }}
  .tab-bar {{ display: flex; border-bottom: 1px solid #e2e8f0; flex-shrink: 0; }}
  .tab-btn {{ flex: 1; padding: 10px 0; font-size: 0.78rem; font-weight: 500;
              color: #94a3b8; background: none; border: none; cursor: pointer;
              border-bottom: 2px solid transparent; margin-bottom: -1px;
              transition: color 0.15s; }}
  .tab-btn:hover {{ color: #334155; }}
  .tab-btn.active {{ color: #0f172a; border-bottom-color: #0284c7; }}
  .tab-content {{ display: none; flex: 1; overflow-y: auto; padding: 16px 20px; }}
  .tab-content.active {{ display: flex; flex-direction: column; gap: 20px; }}
  .panel h2 {{ font-size: 0.85rem; color: #94a3b8; text-transform: uppercase;
               letter-spacing: 0.08em; margin-bottom: 14px; }}
  .bar-row {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px;
              font-size: 0.8rem; }}
  .bar-row .name {{ width: 110px; flex-shrink: 0; color: #334155; overflow: hidden;
                    text-overflow: ellipsis; white-space: nowrap; }}
  .bar-track {{ flex: 1; background: #e2e8f0; border-radius: 3px; height: 8px; }}
  .bar-fill {{ height: 8px; border-radius: 3px; background: #0284c7; }}
  .bar-count {{ color: #94a3b8; font-size: 0.75rem; width: 28px; text-align: right; }}
  .sentiment-row {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px;
                    font-size: 0.8rem; }}
  .senti-pill {{ padding: 2px 8px; border-radius: 99px; font-size: 0.72rem;
                 font-weight: 500; }}
  .senti-pct {{ margin-left: auto; color: #94a3b8; }}
  #detail-panel {{ background: #f1f5f9; border-radius: 8px; padding: 16px;
                   font-size: 0.82rem; min-height: 120px; }}
  #detail-panel .detail-title {{ font-size: 0.95rem; font-weight: 600;
                                  color: #0f172a; margin-bottom: 10px; }}
  #detail-panel .detail-label {{ color: #94a3b8; font-size: 0.72rem;
                                  text-transform: uppercase; letter-spacing: 0.05em;
                                  margin-top: 10px; margin-bottom: 4px; }}
  #detail-panel .detail-tag {{ display: inline-block; background: #e2e8f0;
                                border-radius: 4px; padding: 2px 6px; margin: 2px;
                                font-size: 0.72rem; color: #475569; }}
  #detail-panel ul {{ padding-left: 14px; color: #334155; }}
  #detail-panel li {{ margin-bottom: 4px; }}
  .sample-post {{ margin-bottom: 8px; }}
  .sample-post a {{ color: #0284c7; text-decoration: none; font-size: 0.8rem;
                    line-height: 1.4; display: block; }}
  .sample-post a:hover {{ text-decoration: underline; }}
  .sample-meta {{ font-size: 0.7rem; color: #94a3b8; }}
  .tooltip {{ position: fixed; background: #fff; border: 1px solid #e2e8f0;
              box-shadow: 0 4px 12px rgba(0,0,0,0.08);
              padding: 10px 14px; border-radius: 6px; font-size: 0.8rem;
              pointer-events: none; opacity: 0; transition: opacity 0.15s;
              max-width: 240px; color: #1e293b; z-index: 100; }}
</style>
</head>
<body>

<header>
  <h1>🏥 med-insights</h1>
  <div class="sources">
    <span class="sources-label">sources</span>
    <div class="source-badge" title="Reddit">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
        <circle cx="10" cy="10" r="10" fill="#FF4500"/>
        <path d="M16.67 10a1.46 1.46 0 0 0-2.47-1 7.12 7.12 0 0 0-3.85-1.23l.65-3.08 2.13.45a1 1 0 1 0 .98-1.09 1 1 0 0 0-.96.68l-2.38-.5a.16.16 0 0 0-.19.12l-.73 3.44a7.14 7.14 0 0 0-3.89 1.23 1.46 1.46 0 1 0-1.61 2.39 2.87 2.87 0 0 0 0 .44c0 2.24 2.61 4.06 5.83 4.06s5.83-1.82 5.83-4.06a2.87 2.87 0 0 0 0-.44 1.46 1.46 0 0 0 .66-1.41zM7.27 11a1 1 0 1 1 1 1 1 1 0 0 1-1-1zm5.58 2.71a3.58 3.58 0 0 1-2.85.79 3.58 3.58 0 0 1-2.85-.79.19.19 0 0 1 .26-.26 3.23 3.23 0 0 0 2.59.66 3.23 3.23 0 0 0 2.59-.66.19.19 0 0 1 .26.26zm-.17-1.71a1 1 0 1 1 1-1 1 1 0 0 1-1 1z" fill="#FFF"/>
      </svg>
      <span>reddit</span>
    </div>
  </div>
  <div class="header-stats" id="stats-bar"></div>
  <div class="meta">Updated {date_str}</div>
</header>

<div class="main">
  <div class="chart-area">
    <h2>Cluster map — bubble size = post count, color = dominant sentiment</h2>
    <svg id="bubble-chart"></svg>
  </div>

  <div class="sidebar">
    <div class="tab-bar">
      <button class="tab-btn active" onclick="switchTab('clusters')">Cluster Detail</button>
      <button class="tab-btn" onclick="switchTab('specialty')">Specialty &amp; Sentiment</button>
    </div>
    <div class="tab-content active" id="tab-clusters">
      <div id="detail-panel"><span style="color:#94a3b8">Click a bubble to explore</span></div>
    </div>
    <div class="tab-content" id="tab-specialty">
      <div class="panel">
        <h2>Specialty breakdown</h2>
        <div id="specialty-bars"></div>
      </div>
      <div class="panel">
        <h2>Sentiment distribution</h2>
        <div id="sentiment-rows"></div>
      </div>
    </div>
  </div>
</div>

<div class="tooltip" id="tooltip"></div>

<script>
const CLUSTERS   = {clusters_json};
const SPECIALTY  = {specialty_json};
const SENTIMENT  = {sentiment_json};

// --- Stats bar ---
const totalPosts   = CLUSTERS.reduce((s, c) => s + c.post_count, 0);
const nClusters    = CLUSTERS.length;
const topCluster   = CLUSTERS.slice().sort((a,b) => b.post_count - a.post_count)[0];
document.getElementById("stats-bar").innerHTML = `
  <div class="stat"><div class="value">${{totalPosts}}</div><div class="label">posts</div></div>
  <div class="stat"><div class="value">${{nClusters}}</div><div class="label">clusters</div></div>
  <div class="stat"><div class="value">${{topCluster ? topCluster.post_count : 0}}</div><div class="label">largest</div></div>
  <div class="stat"><div class="value">${{SPECIALTY.length}}</div><div class="label">specialties</div></div>
`;

// --- Specialty bars ---
const maxSpec = SPECIALTY[0]?.count || 1;
document.getElementById("specialty-bars").innerHTML = SPECIALTY.map(s => `
  <div class="bar-row">
    <div class="name" title="${{s.community}}">r/${{s.community}}</div>
    <div class="bar-track"><div class="bar-fill" style="width:${{Math.round(s.count/maxSpec*100)}}%"></div></div>
    <div class="bar-count">${{s.count}}</div>
  </div>`).join("");

// --- Sentiment rows ---
document.getElementById("sentiment-rows").innerHTML = SENTIMENT.map(s => `
  <div class="sentiment-row">
    <span style="font-size:1rem">${{s.emoji}}</span>
    <span class="senti-pill" style="background:${{s.color}}22;color:${{s.color}}">${{s.sentiment}}</span>
    <div class="bar-track" style="flex:1"><div class="bar-fill" style="width:${{s.pct}}%;background:${{s.color}}"></div></div>
    <span class="senti-pct">${{s.pct}}%</span>
  </div>`).join("");

// --- Bubble chart ---
const svg = d3.select("#bubble-chart");
const container = document.getElementById("bubble-chart").parentElement;

function drawBubbles() {{
  svg.selectAll("*").remove();
  const W = container.clientWidth - 64;
  const H = container.clientHeight - 56;
  svg.attr("viewBox", `0 0 ${{W}} ${{H}}`).attr("width", W).attr("height", H);

  if (!CLUSTERS.length) return;

  const xExt = d3.extent(CLUSTERS, d => d.x);
  const yExt = d3.extent(CLUSTERS, d => d.y);
  const pad = 60;
  const xScale = d3.scaleLinear().domain(xExt).range([pad, W - pad]);
  const yScale = d3.scaleLinear().domain(yExt).range([pad, H - pad]);
  const rScale = d3.scaleSqrt()
    .domain([0, d3.max(CLUSTERS, d => d.post_count)])
    .range([10, Math.min(W, H) / 7]);

  const tooltip = document.getElementById("tooltip");

  const g = svg.append("g");
  const nodes = g.selectAll("g.node")
    .data(CLUSTERS)
    .join("g")
    .attr("class", "node")
    .attr("transform", d => `translate(${{xScale(d.x)}},${{yScale(d.y)}})`)
    .style("cursor", "pointer")
    .on("mouseenter", (event, d) => {{
      tooltip.style.opacity = "1";
      tooltip.innerHTML = `<strong>${{d.label}}</strong><br>${{d.post_count}} posts · ${{d.dominant_sentiment}}`;
    }})
    .on("mousemove", (event) => {{
      tooltip.style.left = (event.clientX + 14) + "px";
      tooltip.style.top  = (event.clientY - 10) + "px";
    }})
    .on("mouseleave", () => {{ tooltip.style.opacity = "0"; }})
    .on("click", (event, d) => {{ switchTab("clusters"); showDetail(d); }});

  nodes.append("circle")
    .attr("r", d => rScale(d.post_count))
    .attr("fill", d => d.color + "33")
    .attr("stroke", d => d.color)
    .attr("stroke-width", 1.5);

  // Only render text when the bubble is big enough to hold at least one word legibly.
  // Smaller bubbles show nothing — hover tooltip has the full label.
  nodes.each(function(d) {{
    const r = rScale(d.post_count);
    const MIN_R_FOR_TEXT = 22;   // px — below this, text always bleeds out
    if (r < MIN_R_FOR_TEXT) return;

    const fontSize = Math.max(9, Math.min(11, r / 4));
    const charW = fontSize * 0.52;   // approximate char width for this font size
    const maxLineChars = Math.floor((r * 1.7) / charW);  // chord width ≈ 1.7r
    const lineH = fontSize + 3;

    // Word-wrap into lines that fit inside the chord
    const words = d.label.split(" ");
    const lines = [];
    let cur = "";
    words.forEach(w => {{
      const test = cur ? cur + " " + w : w;
      if (test.length > maxLineChars && cur) {{ lines.push(cur); cur = w; }}
      else cur = test;
    }});
    if (cur) lines.push(cur);

    // Drop lines that would overflow vertically (keep only lines that fit in r*1.5 height)
    const maxLines = Math.floor((r * 1.4) / lineH);
    const visibleLines = lines.slice(0, maxLines);

    const textEl = d3.select(this).append("text")
      .attr("text-anchor", "middle")
      .attr("font-size", fontSize)
      .attr("fill", "#1e293b")
      .attr("pointer-events", "none");

    textEl.selectAll("tspan")
      .data(visibleLines)
      .join("tspan")
      .attr("x", 0)
      .attr("dy", (_, i) => i === 0 ? -(visibleLines.length - 1) * lineH / 2 : lineH)
      .text(t => t);
  }});
}}

function switchTab(name) {{
  document.querySelectorAll(".tab-btn").forEach((b, i) =>
    b.classList.toggle("active", i === (name === "clusters" ? 0 : 1)));
  document.querySelectorAll(".tab-content").forEach(c =>
    c.classList.toggle("active", c.id === "tab-" + name));
}}

function showDetail(d) {{
  const needs = d.top_unmet_needs.length
    ? "<ul>" + d.top_unmet_needs.map(n => `<li>${{n}}</li>`).join("") + "</ul>"
    : "<span style='color:#94a3b8'>No unmet needs recorded</span>";
  const tags = d.communities.map(c => `<span class="detail-tag">r/${{c}}</span>`).join("");
  const posts = d.sample_posts.length
    ? d.sample_posts.map(p => `
        <div class="sample-post">
          <a href="${{p.url}}" target="_blank">${{p.headline}}</a>
          <span class="sample-meta">r/${{p.community}} · ${{p.comment_count}} comments</span>
        </div>`).join("")
    : "<span style='color:#94a3b8'>No posts</span>";
  document.getElementById("detail-panel").innerHTML = `
    <div class="detail-title">${{d.label}}</div>
    <div class="detail-label">Posts</div>${{d.post_count}}
    <div class="detail-label">Dominant sentiment</div>${{d.dominant_sentiment}}
    <div class="detail-label">Communities</div>${{tags}}
    <div class="detail-label">Top unmet needs</div>${{needs}}
    <div class="detail-label">Top threads (spot-check)</div>${{posts}}
  `;
}}

drawBubbles();
window.addEventListener("resize", drawBubbles);
</script>
</body>
</html>"""

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    return str(out)
