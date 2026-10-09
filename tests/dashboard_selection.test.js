"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const source = fs
  .readFileSync(path.join(__dirname, "../web_dashboard/app.js"), "utf8")
  .replace(/\nloadDashboard\(\)\.catch\([\s\S]*$/, "\n");
const context = { console, Intl };
vm.createContext(context);
vm.runInContext(
  `${source}\nthis.approvedTrendEntries = approvedTrendEntries;\nthis.dashboardSelection = dashboardSelection;\n`,
  context,
);

const ranked = {
  rows: [
    { video_id: "rejected", action_pair: "rejected top", velocity_score: 90 },
    { video_id: "approved-a", action_pair: "restore table", velocity_score: 40 },
    { video_id: "pending", action_pair: "pending work", velocity_score: 10 },
    { video_id: "approved-b", action_pair: "carve wood", velocity_score: 5 },
  ],
  approved_video_ids: ["approved-a", "approved-b"],
  maya_briefs: {
    "approved-b": { candidate_id: "approved-b", brief: { title: "B" } },
    "approved-a": { candidate_id: "approved-a", brief: { title: "A" } },
  },
};
const selection = JSON.parse(JSON.stringify(context.dashboardSelection(ranked)));
assert.deepStrictEqual(selection.approvedIds, ["approved-a", "approved-b"]);
assert.strictEqual(selection.selectedIndex, 1);
assert.strictEqual(selection.topTrendLabel, "Restore Table");
assert.strictEqual(selection.peakVelocity, 90);

const entries = JSON.parse(JSON.stringify(context.approvedTrendEntries(ranked)));
assert.deepStrictEqual(entries.map((item) => item.row.action_pair), ["restore table", "carve wood"]);

const empty = JSON.parse(JSON.stringify(context.dashboardSelection({
  rows: [{ video_id: "rejected", action_pair: "rejected top", velocity_score: 90 }],
  approved_video_ids: [],
  maya_briefs: {},
})));
assert.strictEqual(empty.selectedIndex, -1);
assert.deepStrictEqual(empty.approvedIds, []);
assert.strictEqual(empty.topTrendLabel, "No approved trends yet");
assert.strictEqual(empty.peakVelocity, 90);

const withoutList = JSON.parse(JSON.stringify(context.dashboardSelection({
  rows: ranked.rows,
  maya_briefs: ranked.maya_briefs,
})));
assert.deepStrictEqual(withoutList.approvedIds, ["approved-a", "approved-b"]);
assert.strictEqual(withoutList.selectedIndex, 1);

const stray = JSON.parse(JSON.stringify(context.approvedTrendEntries({
  rows: ranked.rows,
  approved_video_ids: ["rejected", "approved-a", "missing"],
  maya_briefs: ranked.maya_briefs,
})));
assert.deepStrictEqual(stray.map((item) => item.row.video_id), ["approved-a"]);
