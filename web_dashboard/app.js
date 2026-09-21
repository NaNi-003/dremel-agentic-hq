"use strict";

const state = { data: null, selectedIndex: 0, briefOpen: false, visibleRows: 15 };
const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[ch]);
const titleCase = (value) => String(value ?? "").replace(/\b\w/g, (c) => c.toUpperCase());
const number = (value) => Number(value) || 0;
const fmt = new Intl.NumberFormat("en-GB");

async function loadDashboard() {
  const response = await fetch("data/dashboard.json", { cache: "no-store" });
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
    ["🔥 Top Emerging Trend", titleCase(top.action_pair), ""],
    ["📈 Peak Velocity", `${top.velocity_score} V/d`, "Accelerating"],
    ["🎬 Videos Scraped", number(state.data.run?.videos_collected) || state.data.rows.length, ""],
    ["📡 Ranked Opportunities", number(state.data.run?.candidates_scored) || state.data.rows.length, ""],
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
  button.textContent = artifact ? "📝 Open Maya brief" : "📝 Maya brief unavailable";
  button.title = artifact ? "Open Maya's saved brief" : "No validated Maya brief is available";
  if (!artifact) {
    $("brief-content").innerHTML = '<div class="notice info">Maya brief unavailable for this candidate.</div>';
    return;
  }
  if (!state.briefOpen) {
    $("brief-content").innerHTML = '<div class="notice info">A Maya content brief is ready for this approved trend. Open it from the sidebar.</div>';
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
      <a class="download-link" download="Dremel_Brief_${escapeHtml(state.data.rows[state.selectedIndex].action_pair.replaceAll(" ", "_"))}.txt" href="${href}">📥 Download Brief for Marketing Team</a>
    </article>`;
}

function renderChart() {
  const svg = $("matrix-chart");
  const rows = state.data.rows;
  const width = 1000, height = 410, pad = 38;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  const maxVelocity = Math.max(...rows.map((row) => number(row.velocity_score)), 1);
  const emotions = [...new Set(rows.map((row) => row.cv_emotion))];
  const colors = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f", "#edc949"];
  const colorFor = (emotion) => colors[emotions.indexOf(emotion) % colors.length];
  const grid = [0, .25, .5, .75, 1].map((part) => {
    const y = height - pad - part * (height - pad * 2);
    return `<line x1="${pad}" y1="${y}" x2="${width - pad}" y2="${y}" stroke="#e6ebf0"/><text x="${pad - 8}" y="${y + 4}" text-anchor="end" font-size="12" fill="#69727d">${Math.round(maxVelocity * part)}</text>`;
  }).join("");
  const points = rows.map((row, index) => {
    const x = pad + ((number(row.velocity_score) * 14) / (maxVelocity * 14)) * (width - pad * 2);
    const y = height - pad - (number(row.velocity_score) / maxVelocity) * (height - pad * 2);
    return `<circle cx="${x}" cy="${y}" r="12" fill="${colorFor(row.cv_emotion)}" fill-opacity=".9"><title>${escapeHtml(row.action_pair)} · ${row.velocity_score} · ${escapeHtml(row.cv_emotion)}</title></circle>`;
  }).join("");
  svg.innerHTML = `${grid}<line x1="${pad}" y1="${height-pad}" x2="${width-pad}" y2="${height-pad}" stroke="#8c96a1"/>${points}`;
  $("legend").innerHTML = emotions.map((emotion) => `<span><i style="background:${colorFor(emotion)}"></i>${escapeHtml(emotion)}</span>`).join("");
}

function renderFeed() {
  const max = Math.max(...state.data.rows.map((row) => number(row.velocity_score)), 1);
  const visible = state.data.rows.slice(0, state.visibleRows);
  $("feed-body").innerHTML = visible.map((row) => `
    <tr>
      <td><img class="thumb" src="${escapeHtml(row.thumbnail_url)}" alt="Thumbnail for ${escapeHtml(row.video_title || row.action_pair)}" loading="lazy"></td>
      <td>${escapeHtml(row.action_pair)}</td>
      <td>${number(row.velocity_score).toFixed(2)}<div class="progress"><i style="width:${Math.max(1, number(row.velocity_score) / max * 100)}%"></i></div></td>
      <td>${escapeHtml(row.cv_emotion)}</td>
      <td><span class="palette"><i style="background:${escapeHtml(row.cv_color_hex)}"></i>${escapeHtml(row.cv_color_hex)}</span></td>
      <td>${row.source_url ? `<a href="${escapeHtml(row.source_url)}" target="_blank" rel="noopener">Open source ↗</a>` : "—"}</td>
    </tr>`).join("");
  $("load-more").classList.toggle("hidden", state.visibleRows >= state.data.rows.length);
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
