"use strict";

const state = { data: null, selectedIndex: 0, briefOpen: false, visibleRows: 15, chartScope: "primary" };
const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[ch]);
const titleCase = (value) => String(value ?? "").replace(/\b\w/g, (c) => c.toUpperCase());
const number = (value) => Number(value) || 0;
const fmt = new Intl.NumberFormat("en-GB");

async function loadDashboard() {
  const response = await fetch("data/dashboard.json?v=__HQ_DASHBOARD_VERSION__", { cache: "no-store" });
  if (!response.ok) throw new Error(`Dashboard data could not be loaded (${response.status}).`);
  const payload = await response.json();
  if (!Array.isArray(payload.rows) || payload.rows.length === 0) throw new Error("The published research dataset is empty.");
  state.data = payload;
  renderAll();
}

function renderAll() {
  renderRun();
  populateSelectors();
  renderKpis();
  renderBrief();
  renderChart();
  renderFeed();
  $("load-more").addEventListener("click", () => {
    state.visibleRows += 10;
    renderFeed();
  });
  bindRoi();
  updateRoi();
}

function renderRun() {
  // Run provenance remains in dashboard.json and the immutable artifacts,
  // but is intentionally omitted from the executive-facing interface.
  $("run-caption").textContent = "";
  $("run-caption").classList.add("hidden");
  $("run-warning").textContent = "";
  $("run-warning").classList.add("hidden");
}

function populateSelectors() {
  const primaryOptions = state.data.rows.slice(0, 15).map((row, index) => `<option value="${index}">${escapeHtml(row.action_pair)}</option>`).join("");
  const allOptions = state.data.rows.map((row, index) => `<option value="${index}">${escapeHtml(row.action_pair)}</option>`).join("");
  $("trend-select").innerHTML = primaryOptions;
  $("roi-trend").innerHTML = allOptions;
  $("trend-select").addEventListener("change", (event) => {
    state.selectedIndex = Number(event.target.value);
    state.briefOpen = false;
    renderBrief();
  });
  $("brief-button").addEventListener("click", () => {
    const artifact = matchingBrief();
    if (!artifact) return;
    state.briefOpen = true;
    renderBrief();
    document.querySelector('[data-tab="ideation"]').click();
  });
}

function renderKpis() {
  const top = state.data.rows[0];
  const items = [
    ["Top Emerging Trend", titleCase(top.action_pair), ""],
    ["Peak Velocity", `${top.velocity_score} V/d`, "Age-adjusted"],
    ["Videos Assessed", number(state.data.run?.videos_collected) || state.data.rows.length, ""],
    ["Ranked Opportunities", number(state.data.run?.candidates_scored) || state.data.rows.length, ""],
  ];
  $("kpis").innerHTML = items.map(([label, value, delta]) => `
    <article class="kpi-card"><span class="kpi-label">${escapeHtml(label)}</span><strong class="kpi-value">${escapeHtml(value)}</strong>${delta ? `<span class="kpi-delta">↗ ${escapeHtml(delta)}</span>` : ""}</article>
  `).join("");
}

function matchingBrief() {
  const selected = state.data.rows[state.selectedIndex];
  const briefs = state.data.maya_briefs || {};
  const saved = briefs[selected.video_id];
  if (saved && saved.candidate_id === selected.video_id) return saved;
  const legacy = state.data.maya_brief;
  return legacy && legacy.candidate_id === selected.video_id ? legacy : null;
}

function renderBrief() {
  const artifact = matchingBrief();
  const button = $("brief-button");
  button.disabled = !artifact;
  button.textContent = artifact ? "Open Maya brief" : "Maya brief unavailable";
  button.title = artifact ? "Open Maya's saved brief" : "No validated Maya brief is available";
  if (!artifact) {
    $("brief-content").innerHTML = '<div class="notice info">Maya brief unavailable for this candidate.</div>';
    return;
  }
  if (!state.briefOpen) {
    const selected = state.data.rows[state.selectedIndex];
    $("brief-content").innerHTML = `<div class="brief-preview"><span class="preview-rank">Primary opportunity ${state.selectedIndex + 1} of 15</span><h2>${escapeHtml(titleCase(selected.action_pair))}</h2><p>A saved creator brief is ready. Open it to review the campaign concept, hook, key beats, and thumbnail direction.</p><button type="button" class="preview-action" onclick="document.getElementById('brief-button').click()">Open campaign brief</button></div>`;
    return;
  }
  const brief = artifact.brief;
  const gap = brief.information_gap;
  const professionalText = gap ? ["", "Objective", brief.objective, "", "Audience Insight", brief.audience_insight, "", "Information Gap", `Known: ${gap.known}`, `Unknown: ${gap.unknown}`, `Payoff: ${gap.payoff}`, "", "Alternative Hooks", ...brief.hook_options.map((hook, i) => `${i + 1}. ${hook}`), "", "Product Role", brief.product_role, "", "Success Metrics", ...brief.success_metrics.map((metric) => `- ${metric}`), "", "Claims Guardrails", brief.claims_guardrails] : [];
  const plainText = [brief.title, ...professionalText, "", "Strategic Rationale", brief.strategic_rationale, "", `Audience: ${brief.audience}`, `Tone: ${brief.tone}`, "", "Hook", brief.hook, "", "YouTube Short Concept", brief.concept, "", "Key Beats", ...brief.key_beats.map((beat, i) => `${i + 1}. ${beat}`), "", "Thumbnail Direction", brief.thumbnail_direction, "", "Call to Action", brief.call_to_action].join("\n");
  const href = URL.createObjectURL(new Blob([plainText], { type: "text/plain" }));
  $("brief-content").innerHTML = `
    <div class="notice success">Active Strategy deployed for: ${escapeHtml(titleCase(state.data.rows[state.selectedIndex].action_pair))}</div>
    <article class="brief-card">
      <h2>${escapeHtml(brief.title)}</h2>
      ${gap ? `<h4>Objective</h4><p>${escapeHtml(brief.objective)}</p><h4>Audience Insight</h4><p>${escapeHtml(brief.audience_insight)}</p><h4>Information Gap</h4><p><strong>Known:</strong> ${escapeHtml(gap.known)}<br><strong>Unknown:</strong> ${escapeHtml(gap.unknown)}<br><strong>Payoff:</strong> ${escapeHtml(gap.payoff)}</p>` : ""}
      <h4>Strategic Rationale</h4><p>${escapeHtml(brief.strategic_rationale)}</p>
      <div class="brief-meta"><div><strong>Audience:</strong> ${escapeHtml(brief.audience)}</div><div><strong>Tone:</strong> ${escapeHtml(brief.tone)}</div></div>
      <h4>Hook</h4><p>${escapeHtml(brief.hook)}</p>
      ${gap ? `<h4>Alternative Hooks</h4><ul>${brief.hook_options.map((hook) => `<li>${escapeHtml(hook)}</li>`).join("")}</ul>` : ""}
      <h4>YouTube Short Concept</h4><p>${escapeHtml(brief.concept)}</p>
      <h4>Key Beats</h4><ol>${brief.key_beats.map((beat) => `<li>${escapeHtml(beat)}</li>`).join("")}</ol>
      <h4>Thumbnail Direction</h4><p>${escapeHtml(brief.thumbnail_direction)}</p>
      <h4>Call to Action</h4><p>${escapeHtml(brief.call_to_action)}</p>
      ${gap ? `<h4>Product Role</h4><p>${escapeHtml(brief.product_role)}</p><h4>Success Metrics</h4><ul>${brief.success_metrics.map((metric) => `<li>${escapeHtml(metric)}</li>`).join("")}</ul><h4>Claims Guardrails</h4><p>${escapeHtml(brief.claims_guardrails)}</p>` : ""}
      <a class="download-link" download="Dremel_Brief_${escapeHtml(state.data.rows[state.selectedIndex].action_pair.replaceAll(" ", "_"))}.txt" href="${href}">Download brief for marketing team</a>
    </article>`;
}

function renderChart() {
  const svg = $("matrix-chart");
  const rows = state.chartScope === "primary" ? state.data.rows.slice(0, 15) : state.data.rows;
  const width = 1000, height = 430, left = 74, right = 28, top = 28, bottom = 52;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  const maxVelocity = Math.max(...rows.map((row) => number(row.velocity_score)), 1);
  const plotW = width - left - right, plotH = height - top - bottom;
  const yGrid = [0, .25, .5, .75, 1].map((part) => {
    const y = top + (1 - part) * plotH;
    return `<line x1="${left}" y1="${y}" x2="${width-right}" y2="${y}" class="chart-grid"/><text x="${left-12}" y="${y+4}" text-anchor="end" class="chart-tick">${fmt.format(Math.round(maxVelocity * part))}</text>`;
  }).join("");
  const tickRanks = state.chartScope === "primary" ? [1, 5, 10, 15] : [1, 10, 20, 30, 40, 50];
  const xGrid = tickRanks.map((rank) => {
    const x = left + ((rank - 1) / Math.max(rows.length - 1, 1)) * plotW;
    return `<line x1="${x}" y1="${top}" x2="${x}" y2="${height-bottom}" class="chart-grid vertical"/><text x="${x}" y="${height-bottom+25}" text-anchor="middle" class="chart-tick">${rank}</text>`;
  }).join("");
  const points = rows.map((row) => {
    const index = state.data.rows.indexOf(row);
    const rank = index + 1;
    const localRank = rows.indexOf(row);
    const x = left + (localRank / Math.max(rows.length - 1, 1)) * plotW;
    const y = top + (1 - number(row.velocity_score) / maxVelocity) * plotH;
    const tier = rank <= 15 ? "primary" : "secondary";
    const selected = index === state.selectedIndex ? " selected" : "";
    return `<circle class="matrix-point ${tier}${selected}" data-index="${index}" cx="${x}" cy="${y}" r="${rank <= 15 ? 9 : 6}" tabindex="0" role="button" aria-label="Rank ${rank}, ${escapeHtml(row.action_pair)}, velocity ${number(row.velocity_score).toFixed(2)}"></circle>`;
  }).join("");
  svg.innerHTML = `<rect x="${left}" y="${top}" width="${plotW}" height="${plotH}" class="chart-plot"></rect>${yGrid}${xGrid}<line x1="${left}" y1="${height-bottom}" x2="${width-right}" y2="${height-bottom}" class="chart-axis"/>${points}`;
  $("legend").innerHTML = '<span><i class="legend-primary"></i>Primary opportunity</span><span><i class="legend-secondary"></i>Secondary candidate</span><span><i class="legend-selected"></i>Selected</span>';
  bindChartInteractions();
}

function bindChartInteractions() {
  const tooltip = $("chart-tooltip");
  const shell = tooltip.parentElement;
  const show = (point) => {
    const index = number(point.dataset.index);
    const row = state.data.rows[index];
    const box = point.getBoundingClientRect();
    const shellBox = shell.getBoundingClientRect();
    tooltip.innerHTML = `<strong>${escapeHtml(titleCase(row.action_pair))}</strong><span>Rank ${index + 1} · ${number(row.velocity_score).toFixed(2)} V/d</span><small>${index < 15 ? "Select to open campaign studio" : "Secondary candidate"}</small>`;
    tooltip.style.left = `${Math.min(Math.max(box.left - shellBox.left, 110), shellBox.width - 130)}px`;
    tooltip.style.top = `${Math.max(box.top - shellBox.top - 82, 8)}px`;
    tooltip.classList.remove("hidden");
  };
  const hide = () => tooltip.classList.add("hidden");
  document.querySelectorAll(".matrix-point").forEach((point) => {
    point.addEventListener("mouseenter", () => show(point));
    point.addEventListener("focus", () => show(point));
    point.addEventListener("mouseleave", hide);
    point.addEventListener("blur", hide);
    point.addEventListener("click", () => {
      const index = number(point.dataset.index);
      if (index >= 15) return;
      state.selectedIndex = index;
      state.briefOpen = false;
      $("trend-select").value = String(index);
      renderBrief();
      renderChart();
      document.querySelector('[data-tab="ideation"]').click();
    });
    point.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); point.click(); }
    });
  });
  document.querySelectorAll(".chart-filter").forEach((button) => {
    button.onclick = () => {
      state.chartScope = button.dataset.chartScope;
      document.querySelectorAll(".chart-filter").forEach((item) => item.classList.toggle("active", item === button));
      renderChart();
    };
  });
}

function renderFeed() {
  const max = Math.max(...state.data.rows.map((row) => number(row.velocity_score)), 1);
  const visible = state.data.rows.slice(0, state.visibleRows);
  $("feed-body").innerHTML = visible.map((row) => `
    <tr>
      <td><img class="thumb" src="${escapeHtml(row.thumbnail_url)}" alt="Thumbnail for ${escapeHtml(row.video_title || row.action_pair)}" loading="lazy"></td>
      <td>${escapeHtml(row.action_pair)}</td>
      <td>${number(row.velocity_score).toFixed(2)}<div class="progress"><i style="width:${Math.max(1, number(row.velocity_score) / max * 100)}%"></i></div></td>
      <td>${thumbnailSignals(row)}</td>
      <td>${paletteDisplay(row)}</td>
      <td>${sentimentDisplay(row)}</td>
      <td>${row.source_url ? `<a href="${escapeHtml(row.source_url)}" target="_blank" rel="noopener">Open source ↗</a>` : "—"}</td>
    </tr>`).join("");
  $("load-more").classList.toggle("hidden", state.visibleRows >= state.data.rows.length);
}

function parsedList(value) {
  if (Array.isArray(value)) return value;
  if (typeof value !== "string" || !value.trim()) return [];
  try {
    const parsed = JSON.parse(value.replaceAll("'", '"'));
    return Array.isArray(parsed) ? parsed : [];
  } catch (_) {
    return [];
  }
}

function thumbnailSignals(row) {
  const lines = [];
  const faces = number(row.cv_face_count);
  if (faces) lines.push(`${faces} ${faces === 1 ? "face" : "faces"}: ${escapeHtml(row.cv_emotion || "expression unavailable")}`);
  else lines.push(escapeHtml(row.cv_emotion || "No face detected"));
  const tools = parsedList(row.cv_tools);
  const objects = parsedList(row.cv_objects);
  if (tools.length) lines.push(`<strong>Tools:</strong> ${tools.map(escapeHtml).join(", ")}`);
  if (objects.length) lines.push(`<strong>Objects:</strong> ${objects.map(escapeHtml).join(", ")}`);
  if (row.cv_color_temperature && row.cv_color_temperature !== "unavailable") lines.push(`${escapeHtml(titleCase(row.cv_color_temperature))} palette`);
  if (number(row.cv_contrast) >= 0.55) lines.push("High contrast");
  if (number(row.cv_saturation) >= 0.55) lines.push("Vivid saturation");
  if (row.cv_visual_clutter && row.cv_visual_clutter !== "unavailable") lines.push(`${escapeHtml(titleCase(row.cv_visual_clutter))} visual density`);
  return lines.join("<br>");
}

function paletteDisplay(row) {
  const colors = parsedList(row.cv_palette).filter((color) => /^#[0-9a-f]{6}$/i.test(color));
  const palette = colors.length ? colors : [row.cv_color_hex];
  return palette.map((color) => `<span class="palette"><i style="background:${escapeHtml(color)}"></i>${escapeHtml(color)}</span>`).join(" ");
}

function sentimentDisplay(row) {
  const label = escapeHtml(row.viewer_sentiment || "Unavailable");
  const sample = number(row.viewer_comments_sampled);
  if (!sample) return `${label}<br><small>No usable comment sample</small>`;
  const score = Number(row.viewer_sentiment_score);
  const details = Number.isFinite(score) ? `score ${score.toFixed(2)}` : "score unavailable";
  return `<strong>${label}</strong><br><small>${details} · ${fmt.format(sample)} comments · ${escapeHtml(row.viewer_sentiment_confidence || "unavailable")} confidence</small>`;
}

function bindRoi() {
  document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => {
    document.querySelectorAll(".tab,.panel").forEach((item) => item.classList.remove("active"));
    tab.classList.add("active");
    $(tab.dataset.tab).classList.add("active");
  }));
  $("roi-form").addEventListener("input", updateRoi);
}

function updateRoi() {
  const values = Object.fromEntries(["views", "cpm", "fixed", "ctr", "cvr", "price", "margin", "discount", "inventory"].map((id) => [id, number($(id).value)]));
  [["views", fmt.format(values.views)], ["cpm", `£${values.cpm}`], ["fixed", `£${values.fixed}`], ["ctr", `${values.ctr.toFixed(1)}%`], ["cvr", `${values.cvr.toFixed(1)}%`], ["price", `£${values.price}`], ["margin", `£${values.margin}`], ["discount", `${values.discount}%`]].forEach(([id, value]) => $(`${id}-output`).textContent = value);
  const trend = state.data.rows[number($("roi-trend").value)];
  const maxVelocity = Math.max(...state.data.rows.map((row) => number(row.velocity_score)), 1);
  const campaignCost = values.views / 1000 * values.cpm + values.fixed;
  const finalCtr = values.ctr + number(trend.velocity_score) / maxVelocity * 1.5;
  const traffic = values.views * finalCtr / 100;
  const projectedDemand = traffic * values.cvr / 100;
  const availableUnits = Math.max(values.inventory, 0);
  const fulfillableUnits = Math.min(projectedDemand, availableUnits);
  const excessUnits = Math.max(projectedDemand - availableUnits, 0);
  const adjustedMargin = values.margin - values.price * values.discount / 100 + ($("clv").checked ? 15 : 0);
  const unconstrainedNetProfit = projectedDemand * adjustedMargin - campaignCost;
  const unconstrainedRoi = campaignCost > 0 ? unconstrainedNetProfit / campaignCost * 100 : 0;
  const constrainedNetProfit = fulfillableUnits * adjustedMargin - campaignCost;
  const constrainedRoi = campaignCost > 0 ? constrainedNetProfit / campaignCost * 100 : 0;
  const fulfillableRounded = Math.trunc(fulfillableUnits);
  const fulfillableLabel = `${fmt.format(fulfillableRounded)} ${fulfillableRounded === 1 ? "unit" : "units"}`;
  const salesLabel = `${fmt.format(fulfillableRounded)} ${fulfillableRounded === 1 ? "sale" : "sales"}`;
  const cards = [
    ["Total Campaign Cost", `£${fmt.format(Math.round(campaignCost))}`, "Media + Seeding"],
    ["Projected Demand", `${fmt.format(Math.trunc(projectedDemand))} units`, `${fmt.format(Math.trunc(traffic))} Site Visitors`],
    ["Fulfillable Sales", fulfillableLabel, `Campaign availability: ${fmt.format(availableUnits)}`],
    ["Unconstrained Campaign ROI", `${fmt.format(Math.round(unconstrainedRoi))}%`, unconstrainedRoi > 0 ? "Profitable" : "Negative ROI"],
    ["Availability-Constrained ROI", `${fmt.format(Math.round(constrainedRoi))}%`, constrainedRoi > 0 ? "Profitable" : "Negative ROI"],
  ];
  $("roi-kpis").innerHTML = cards.map(([label, value, delta]) => `<article class="kpi-card"><span class="kpi-label">${label}</span><strong class="kpi-value">${value}</strong><span class="kpi-delta">${escapeHtml(delta)}</span></article>`).join("");
  const warning = $("inventory-warning");
  warning.classList.toggle("hidden", excessUnits <= 0);
  warning.textContent = excessUnits > 0
    ? `⚠️ Projected demand exceeds available inventory by ${fmt.format(Math.ceil(excessUnits))} units. ROI is capped at ${fulfillableLabel}. Consider reducing campaign scale or timing the campaign with availability.`
    : "";
  $("roi-takeaway").innerHTML = `<strong>Strategic Takeaway:</strong> By hiring a creator with an audience of ${fmt.format(values.views)}, Dremel spends £${fmt.format(Math.round(campaignCost))} (Media + Seeding). The high velocity of the <strong>'${escapeHtml(titleCase(trend.action_pair))}'</strong> trend lifts CTR to ${finalCtr.toFixed(2)}%. Accounting for a ${values.discount}% promo code, adjusted margin is £${adjustedMargin.toFixed(2)}. The funnel projects ${fmt.format(Math.trunc(projectedDemand))} units of demand and an unconstrained ROI of ${fmt.format(Math.round(unconstrainedRoi))}%; campaign availability supports ${salesLabel}, producing a constrained net profit of £${fmt.format(Math.round(constrainedNetProfit))}.`;
}

loadDashboard().catch((error) => {
  document.querySelector("main").innerHTML = `<div class="error-state"><h1>Dashboard unavailable</h1><p>${escapeHtml(error.message)}</p></div>`;
});
