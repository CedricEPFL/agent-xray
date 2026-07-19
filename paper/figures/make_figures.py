"""Publication figures for the Agent X-Ray paper. Reads real result JSONs."""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2] / "poc" / "agent-xray" / "results"
OUT = Path(__file__).resolve().parent

# Validated categorical slots (dataviz reference palette, light mode, fixed roles)
BLUE, GREEN, MAGENTA, YELLOW = "#2a78d6", "#008300", "#e87ba4", "#eda100"
INK, INK2 = "#0b0b0b", "#52514e"

plt.rcParams.update({
    "font.size": 8, "axes.labelsize": 8, "axes.titlesize": 8.5,
    "xtick.labelsize": 7.5, "ytick.labelsize": 7.5, "legend.fontsize": 7.5,
    "axes.edgecolor": INK2, "axes.linewidth": 0.6, "text.color": INK,
    "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
    "figure.dpi": 300, "savefig.bbox": "tight", "font.family": "sans-serif",
})

# ---------------- Figure 1: accuracy vs cost Pareto ----------------
r = json.load(open(ROOT / "results_math500_final.json", encoding="utf-8"))
V = r["variants"]
GROUPS = {  # role -> (color, marker, systems)
    "Self-consistency baselines": (BLUE, "o", ["cot@1", "sc@3", "sc@9", "sc@budget"]),
    "Fixed workflow": (GREEN, "s", ["full"]),
    "Agreement-gated escalation": (MAGENTA, "D", ["escalate_structure", "escalate_sc"]),
}
LABEL = {"cot@1": "CoT@1", "sc@3": "SC@3", "sc@9": "SC@9", "sc@budget": "SC@budget",
         "full": "workflow", "escalate_structure": "esc→workflow", "escalate_sc": "esc→SC"}
NUDGE = {"cot@1": (10, -13), "sc@3": (0, 8), "sc@9": (-6, -17), "sc@budget": (6, -17),
         "full": (0, 11), "escalate_structure": (-8, -17), "escalate_sc": (-18, 8)}

fig, ax = plt.subplots(figsize=(3.4, 2.5))
for role, (color, marker, systems) in GROUPS.items():
    xs = [V[s]["mean_cost_usd"] * 1000 for s in systems]
    ys = [V[s]["accuracy"] * 100 for s in systems]
    lo = [(V[s]["accuracy"] - V[s]["ci"]["lower"]) * 100 for s in systems]
    hi = [(V[s]["ci"]["upper"] - V[s]["accuracy"]) * 100 for s in systems]
    ax.errorbar(xs, ys, yerr=[lo, hi], fmt=marker, color=color, ms=5,
                elinewidth=0.8, capsize=2, capthick=0.8, lw=0, label=role,
                markeredgecolor="white", markeredgewidth=0.5, zorder=3)
    for s, x, y in zip(systems, xs, ys):
        dx, dy = NUDGE[s]
        ax.annotate(LABEL[s], (x, y), textcoords="offset points", xytext=(dx, dy),
                    ha="center", fontsize=7, color=INK2)
ax.set_xscale("log")
ax.set_xlabel("Mean cost per problem (m$, log scale)")
ax.set_ylabel("Accuracy (%)")
ax.set_ylim(84.3, 96.5)
ax.grid(True, which="major", lw=0.3, color="#e6e5e0", zorder=0)
ax.legend(loc="upper left", frameon=False, handletextpad=0.2, borderaxespad=0.2)
for spine in ("top", "right"):
    ax.spines[spine].set_visible(False)
fig.savefig(OUT / "fig_pareto.pdf")
plt.close(fig)

# ---------------- Figure 2: audit decomposition ----------------
# Human-confirmed audit: 25 consensus flags -> 20 scorer / 3 label / 2 broken;
# 50 random -> 49 clean / 1 scorer.
cats = [("Scorer artifact", BLUE), ("Gold label wrong", MAGENTA),
        ("Problem broken/ambiguous", YELLOW), ("Label correct", GREEN)]
rows = {"Consensus flags (n=25)": [20, 3, 2, 0], "Random sample (n=50)": [1, 0, 0, 49]}

fig, ax = plt.subplots(figsize=(3.4, 1.55))
ypos = {name: i for i, name in enumerate(reversed(list(rows)))}
for name, vals in rows.items():
    left = 0.0
    total = sum(vals)
    for (cat, color), v in zip(cats, vals):
        if v == 0:
            continue
        frac = v / total * 100
        ax.barh(ypos[name], frac, left=left, color=color, height=0.55,
                edgecolor="white", linewidth=1.5, zorder=3)
        txt_color = "white" if color in (BLUE, GREEN) else INK
        if frac > 6:
            ax.text(left + frac / 2, ypos[name], str(v), va="center", ha="center",
                    fontsize=7.5, color=txt_color, fontweight="bold")
        left += frac
ax.set_yticks(list(ypos.values()), list(ypos.keys()), fontsize=7.5)
ax.set_xlim(0, 100)
ax.set_xlabel("Share of audited items (%)")
ax.tick_params(left=False)
for spine in ("top", "right", "left"):
    ax.spines[spine].set_visible(False)
handles = [plt.Rectangle((0, 0), 1, 1, color=c) for _, c in cats]
ax.legend(handles, [c for c, _ in cats], loc="upper center", ncol=2, frameon=False,
          bbox_to_anchor=(0.5, -0.42), columnspacing=1.0, handlelength=1.2)
fig.savefig(OUT / "fig_audit.pdf")
plt.close(fig)
print("wrote", OUT / "fig_pareto.pdf", "and", OUT / "fig_audit.pdf")
