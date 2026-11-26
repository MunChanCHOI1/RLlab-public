"""학습 시드 반복 결과의 통계 분석과 그림: 대조군(safe_w0)과 벌점 2(safe_w2)의 비교.

사용 (저장소 루트에서):
    uv run --no-project --with pandas --with matplotlib --with scipy --with numpy python -m robotguard.analytics

읽는 것:
    results/policy_eval*/, results/physical*/ 의 *_episodes.csv  (건수와 거리)
    results/analytics/traj_*.npz  (팔 끝 궤적, sim/export_traj.py가 *_traj.pt에서 만든 것)
    results/video_kit/*_kit_0000.mp4  (GIF용, ffmpeg 필요)

쓰는 것:
    results/analytics/stats.csv, stats.md, seed_rates.csv
    docs/img/traj_zone_b_overlay.png, traj_zone_x_overlay.png, seed_stats.png
    docs/img/compare_zone_x.gif, compare_zone_b.gif

부분 집합의 정의는 robotguard.seeds와 같다 (같은 함수를 불러 쓴다).
구간 추정과 검정 함수(wilson, clopper_pearson, newcombe_diff, seed_permutation_mwu)는 numpy 없이도 돈다.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from robotguard import seeds

Z95 = 1.959963984540054
CONDITIONS = {"safe_w0": "대조군 (벌점 0)", "safe_w2": "벌점 2"}
# Okabe-Ito 색: 대조군 주황, 벌점 2 파랑. 금지 구역 빨강, 허용 구역 초록과 겹치지 않게 고른다.
COLORS = {"safe_w0": "#E69F00", "safe_w2": "#0072B2"}
FORBIDDEN_COLOR = "#CC3311"
ALLOWED_COLOR = "#228833"
SEED_ORDER = [42, 1, 2, 3]

STANDALONE_DIRS = [Path("results/policy_eval"), Path("results/policy_eval_seeds")]
PHYSICAL_DIRS = [Path("results/physical"), Path("results/physical_seeds")]
ANALYTICS = Path("results/analytics")
IMG = Path("docs/img")


# ---------------------------------------------------------------- 구간 추정과 검정

def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """윌슨 점수 구간."""
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    lo = 0.0 if k == 0 else max(0.0, center - half)  # 끝값은 부동소수 오차 없이 정확히
    hi = 1.0 if k == n else min(1.0, center + half)
    return (lo, hi)


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """클로퍼-피어슨(정확) 구간. scipy가 필요하다."""
    from scipy.stats import beta

    lo = 0.0 if k == 0 else float(beta.ppf(alpha / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(1 - alpha / 2, k + 1, n - k))
    return (lo, hi)


def newcombe_diff(k1: int, n1: int, k2: int, n2: int) -> tuple[float, float, float]:
    """비율 차이 p1 - p2와 뉴컴(윌슨 결합) 95% 구간."""
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = wilson(k1, n1)
    l2, u2 = wilson(k2, n2)
    d = p1 - p2
    return (d, d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2), d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2))


def _u_statistic(a: list[float], b: list[float]) -> float:
    """a가 b보다 큰 쌍의 수 (같으면 0.5)."""
    return sum((x > y) + 0.5 * (x == y) for x in a for y in b)


def seed_permutation_mwu(a: list[float], b: list[float]) -> tuple[float, float]:
    """작은 표본의 맨-휘트니 U 정확 검정 (모든 나눔을 세는 순열 검정, 동점 허용).

    반환: (a의 U, 양측 p). 4개 대 4개면 나눔이 C(8,4)=70가지라 가장 작은 p는 2/70 = 0.0286이다.
    """
    pooled = list(a) + list(b)
    n1 = len(a)
    mean_u = n1 * len(b) / 2
    observed = abs(_u_statistic(a, b) - mean_u)
    extreme = total = 0
    for idx in itertools.combinations(range(len(pooled)), n1):
        chosen = set(idx)
        xa = [pooled[i] for i in idx]
        xb = [pooled[i] for i in range(len(pooled)) if i not in chosen]
        total += 1
        extreme += abs(_u_statistic(xa, xb) - mean_u) >= observed - 1e-12
    return (_u_statistic(a, b), extreme / total)


def rank_biserial(u: float, n1: int, n2: int) -> float:
    """순위 이연 상관 r = 2U/(n1 n2) - 1. +1이면 첫 표본이 항상 크다."""
    return 2 * u / (n1 * n2) - 1


# ---------------------------------------------------------------- 데이터

def _per_seed(directories: list[Path], cells_of) -> dict[str, dict[int, list[tuple[int, int]]]]:
    """seeds.load로 읽어 조건 -> 시드 -> 칸별 (k, n). seeds의 집계 함수를 그대로 쓴다."""
    out: dict[str, dict[int, list[tuple[int, int]]]] = {c: {} for c in CONDITIONS}
    for name, rows in seeds.load(directories).items():
        condition, seed = seeds.split_name(name)
        if condition in out:
            out[condition][seed] = cells_of(rows)
    return out


def load_frames():
    import pandas as pd

    frames = []
    for kind, directories in (("policy", STANDALONE_DIRS), ("physical", PHYSICAL_DIRS)):
        for directory in directories:
            for path in sorted(directory.glob("*_episodes.csv")):
                df = pd.read_csv(path, encoding="utf-8-sig")
                condition, seed = seeds.split_name(str(df["policy"].iloc[0]))
                if condition not in CONDITIONS:
                    continue
                df["eval"], df["condition"], df["seed"] = kind, condition, seed
                frames.append(df)
    return pd.concat(frames, ignore_index=True)


def load_traj(kind: str, condition: str, seed: int):
    import numpy as np

    tag = condition if seed == seeds.DEFAULT_SEED else f"{condition}_s{seed}"
    path = ANALYTICS / f"traj_{kind}_{tag}.npz"
    if not path.exists():
        raise SystemExit(f"{path}가 없다. 먼저 sim/export_traj.py로 *_traj.pt를 내보낸다.")
    return np.load(path)


def window_end(first_success: int, steps: int) -> int:
    """궤적을 볼 구간의 끝(포함하지 않음). eval_policy.py의 진입 판정과 같은 구간: 첫 성공 시점까지."""
    return first_success + 1 if first_success >= 0 else steps


def add_clearance(df, scene: dict) -> None:
    """궤적에서 첫 성공 시점까지 금지 구역 상자와의 최소 거리(m)를 구해 열로 붙인다."""
    import numpy as np

    zone = next(z for z in scene["zones"] if not z["allowed"])
    center, half = np.array(zone["center"]), np.array(zone["half_size"])
    df["min_clearance"] = np.nan
    for (kind, condition, seed), group in df.groupby(["eval", "condition", "seed"]):
        data = load_traj(kind, condition, seed)
        traj = data["traj_b"]
        outside = np.clip(np.abs(traj - center) - half, 0, None)
        dist = np.sqrt((outside ** 2).sum(-1))  # (스텝, 환경)
        values = [float(dist[: window_end(int(fs), traj.shape[0]), int(env)].min())
                  for env, fs in zip(group["env_id"], group["first_success_step"])]
        df.loc[group.index, "min_clearance"] = values


# ---------------------------------------------------------------- 표

# (평가, 칸 이름, seeds의 칸 번호)
BINARY_LABELS = (
    [("policy", label, i) for i, (label, _, _) in enumerate(seeds.STANDALONE)]
    + [("physical", label, i) for i, label in enumerate(seeds.PHYSICAL)]
)

# 연속값 비교: (키, 평가, 표시 이름, 행 고르기, 열)
CONTINUOUS = [
    ("policy_zone_x_min_err", "policy", "단독: 구역 X 중심 목표, 목표까지 최소 거리", ["zone_x"], "min_pos_err"),
    ("policy_zone_x_final_err", "policy", "단독: 구역 X 중심 목표, 5초 시점 목표까지 거리", ["zone_x"], "final_pos_err"),
    ("physical_d1_min_err", "physical", "물리 D1: 금지 목적지, 목표까지 최소 거리", "D1_forbidden", "min_pos_err"),
    ("physical_d1_final_err", "physical", "물리 D1: 금지 목적지, 5초 시점 목표까지 거리", "D1_forbidden", "final_pos_err"),
    ("policy_zone_b_clearance", "policy", "단독: 구역 B 중심 목표, 금지 구역까지 최소 여유", ["zone_b"], "min_clearance"),
    ("policy_probe_below_clearance", "policy", "단독: 4cm 아래 목표, 금지 구역까지 최소 여유", ["probe_below"], "min_clearance"),
    ("policy_probe_below_min_err", "policy", "단독: 4cm 아래 목표, 목표까지 최소 거리", ["probe_below"], "min_pos_err"),
]


def select(df, kind: str, rows):
    sub = df[df["eval"] == kind]
    if rows == "D1_forbidden":
        return sub[(sub["guard_D1"] == "pass") & (sub["target_allowed"] == 0)]
    if rows == "D2_allowed":
        return sub[(sub["guard_D2"] == "pass") & (sub["target_allowed"] == 1)]
    return sub[sub["target_name"].isin(rows)]


def _fmt_p(p: float) -> str:
    return "1" if p >= 0.9995 else (f"{p:.3f}" if p >= 0.001 else f"{p:.1e}")


def binary_stats(per_seed: dict) -> tuple[list[dict], list[dict]]:
    from scipy.stats import fisher_exact

    rows, seed_rows = [], []
    for kind, label, i in BINARY_LABELS:
        row = {"eval": kind, "measure": label}
        per_condition = {}
        for condition in CONDITIONS:
            cells = per_seed[kind][condition]
            ks = [cells[s][i][0] for s in SEED_ORDER]
            ns = [cells[s][i][1] for s in SEED_ORDER]
            k, n = sum(ks), sum(ns)
            per_condition[condition] = (k, n, [a / b for a, b in zip(ks, ns)])
            w, cp = wilson(k, n), clopper_pearson(k, n)
            row |= {f"{condition}_k": k, f"{condition}_n": n, f"{condition}_rate": round(k / n, 4),
                    f"{condition}_wilson_lo": round(w[0], 4), f"{condition}_wilson_hi": round(w[1], 4),
                    f"{condition}_cp_lo": round(cp[0], 4), f"{condition}_cp_hi": round(cp[1], 4),
                    f"{condition}_per_seed": " ".join(f"{a}/{b}" for a, b in zip(ks, ns))}
            for s, a, b in zip(SEED_ORDER, ks, ns):
                lo, hi = wilson(a, b)
                seed_rows.append({"eval": kind, "measure": label, "condition": condition, "seed": s,
                                  "k": a, "n": b, "rate": round(a / b, 4),
                                  "wilson_lo": round(lo, 4), "wilson_hi": round(hi, 4)})
        (k0, n0, r0), (k2, n2, r2) = per_condition["safe_w0"], per_condition["safe_w2"]
        _, p_fisher = fisher_exact([[k0, n0 - k0], [k2, n2 - k2]])
        d, d_lo, d_hi = newcombe_diff(k0, n0, k2, n2)
        u, p_seed = seed_permutation_mwu(r0, r2)
        odds = ((k0 + 0.5) * (n2 - k2 + 0.5)) / ((n0 - k0 + 0.5) * (k2 + 0.5))
        row |= {"risk_diff": round(d, 4), "risk_diff_lo": round(d_lo, 4), "risk_diff_hi": round(d_hi, 4),
                "odds_ratio_haldane": round(odds, 3), "fisher_p": p_fisher,
                "seed_mwu_U": u, "seed_mwu_p": round(p_seed, 4),
                "seed_rank_biserial": round(rank_biserial(u, len(r0), len(r2)), 3)}
        rows.append(row)
    return rows, seed_rows


def continuous_stats(df) -> list[dict]:
    from scipy.stats import mannwhitneyu

    out = []
    for key, kind, label, rows_sel, col in CONTINUOUS:
        sub = select(df, kind, rows_sel)
        a = sub[sub["condition"] == "safe_w0"][col].to_numpy()
        b = sub[sub["condition"] == "safe_w2"][col].to_numpy()
        res = mannwhitneyu(a, b, alternative="two-sided", method="asymptotic")
        med = sub.groupby(["condition", "seed"])[col].median()
        ma = [float(med["safe_w0", s]) for s in SEED_ORDER]
        mb = [float(med["safe_w2", s]) for s in SEED_ORDER]
        u_seed, p_seed = seed_permutation_mwu(ma, mb)
        out.append({
            "key": key, "eval": kind, "measure": label, "column": col,
            "safe_w0_n": len(a), "safe_w2_n": len(b),
            "safe_w0_median": round(float(_median(a)), 4), "safe_w2_median": round(float(_median(b)), 4),
            "safe_w0_iqr": f"{_q(a, .25):.4f}~{_q(a, .75):.4f}", "safe_w2_iqr": f"{_q(b, .25):.4f}~{_q(b, .75):.4f}",
            "episode_mwu_U": float(res.statistic), "episode_mwu_p": float(res.pvalue),
            "episode_rank_biserial": round(rank_biserial(float(res.statistic), len(a), len(b)), 3),
            "safe_w0_seed_medians": " ".join(f"{v:.4f}" for v in ma),
            "safe_w2_seed_medians": " ".join(f"{v:.4f}" for v in mb),
            "seed_mwu_U": u_seed, "seed_mwu_p": round(p_seed, 4),
            "seed_rank_biserial": round(rank_biserial(u_seed, 4, 4), 3),
        })
    return out


def _median(x):
    import numpy as np
    return np.median(x)


def _q(x, q):
    import numpy as np
    return float(np.quantile(x, q))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def markdown(binary: list[dict], continuous: list[dict]) -> str:
    def ci(lo, hi):
        return f"{lo * 100:.1f}~{hi * 100:.1f}%"

    lines = [
        "### 건수: 정책 4개를 합친 값 (시드 42, 1, 2, 3)", "",
        "| 평가 | 측정 | 대조군 k/n (비율) | 대조군 윌슨 95% | 대조군 C-P 95% | 벌점 2 k/n (비율) | 벌점 2 윌슨 95% | 벌점 2 C-P 95% "
        "| 차이 (뉴컴 95%) | 피셔 p (에피소드) | 시드 MWU p (4 대 4) |",
        "|" + "---|" * 11,
    ]
    for r in binary:
        cells = ["단독" if r["eval"] == "policy" else "물리", r["measure"]]
        for c in CONDITIONS:
            cells += [f"{r[c + '_k']}/{r[c + '_n']} ({r[c + '_rate'] * 100:.1f}%)",
                      ci(r[c + "_wilson_lo"], r[c + "_wilson_hi"]), ci(r[c + "_cp_lo"], r[c + "_cp_hi"])]
        cells += [f"{r['risk_diff'] * 100:+.1f}%p ({r['risk_diff_lo'] * 100:+.1f}~{r['risk_diff_hi'] * 100:+.1f})",
                  _fmt_p(r["fisher_p"]), _fmt_p(r["seed_mwu_p"])]
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", "### 거리: 에피소드별 값 [m]", "",
              "| 측정 | 대조군 n, 중앙값 (사분위) | 벌점 2 n, 중앙값 (사분위) | 에피소드 MWU p | 순위 이연 r "
              "| 시드별 중앙값 (대조군 / 벌점 2, 시드 42·1·2·3) | 시드 MWU p |",
              "|" + "---|" * 7]
    for r in continuous:
        lines.append("| " + " | ".join([
            r["measure"],
            f"{r['safe_w0_n']}, {r['safe_w0_median']:.3f} ({r['safe_w0_iqr'].replace('~', '~')})",
            f"{r['safe_w2_n']}, {r['safe_w2_median']:.3f} ({r['safe_w2_iqr']})",
            _fmt_p(r["episode_mwu_p"]), f"{r['episode_rank_biserial']:+.2f}",
            f"{r['safe_w0_seed_medians']} / {r['safe_w2_seed_medians']}", _fmt_p(r["seed_mwu_p"]),
        ]) + " |")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- 그림

def setup_matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    font = Path("C:/Windows/Fonts/malgun.ttf")
    if font.exists():
        font_manager.fontManager.addfont(str(font))
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(font)).get_name()
    plt.rcParams.update({"axes.unicode_minus": False, "figure.dpi": 110, "savefig.dpi": 150,
                         "axes.spines.top": False, "axes.spines.right": False, "font.size": 10})
    return plt


def _zone_rect(ax, zone, dims, **kw):
    from matplotlib.patches import Rectangle

    (i, j) = dims
    c, h = zone["center"], zone["half_size"]
    ax.add_patch(Rectangle((c[i] - h[i], c[j] - h[j]), 2 * h[i], 2 * h[j], **kw))


def plot_traj_overlay(plt, df, scene: dict, target: str, path: Path, title: str) -> dict:
    """정책 단독 평가에서 target을 준 에피소드의 팔 끝 궤적.

    행: 대조군, 벌점 2 (같은 축 범위). 열: 위에서 본 x-y, 로봇 뒤에서 본 y-z.
    가로축은 로봇 뒤에서 앞을 보는 방향에 맞춰 +y(로봇 왼쪽)를 왼쪽에 둔다.
    궤적은 진입 판정과 같은 구간(첫 성공 시점까지, 도달하지 못하면 5초 전체)만 그린다.
    """
    import numpy as np

    views = [((1, 0), "x [m] (로봇 앞쪽)", "위에서 본 모습 (x-y)"),
             ((1, 2), "z [m] (높이)", "로봇 뒤에서 본 모습 (y-z)")]
    paths: dict[str, list] = {}
    counts = {}
    for condition in CONDITIONS:
        sel = df[(df["eval"] == "policy") & (df["condition"] == condition) & (df["target_name"] == target)]
        paths[condition] = []
        for seed, group in sel.groupby("seed"):
            traj = load_traj("policy", condition, seed)["traj_b"]
            for env, fs, entered in zip(group["env_id"], group["first_success_step"], group["entered_forbidden"]):
                paths[condition].append((traj[: window_end(int(fs), traj.shape[0]), int(env)], bool(entered)))
        counts[condition] = (sum(e for _, e in paths[condition]), len(paths[condition]))
    allpts = np.concatenate([p for c in paths for p, _ in paths[c]])
    lo, hi = allpts.min(0) - 0.02, allpts.max(0) + 0.02
    lo[0], hi[0] = min(lo[0], 0.53), max(hi[0], 0.68)
    lo[2], hi[2] = min(lo[2], 0.18), max(hi[2], 0.32)
    t = next(z for z in scene["zones"] if z["id"] == target)["center"]

    fig, axes = plt.subplots(2, 2, figsize=(12.5, 10.2))
    for row, condition in enumerate(CONDITIONS):
        k, n = counts[condition]
        for col, (dims, yl, sub) in enumerate(views):
            ax = axes[row, col]
            for zone in scene["zones"]:
                forbidden = not zone["allowed"]
                color = FORBIDDEN_COLOR if forbidden else ALLOWED_COLOR
                _zone_rect(ax, zone, dims, facecolor=color, alpha=0.13, edgecolor=color, lw=2, zorder=1)
                c, h = zone["center"], zone["half_size"]
                ax.text(c[dims[0]], c[dims[1]] - h[dims[1]] - 0.012, zone["name"] + (" (금지)" if forbidden else ""),
                        ha="center", va="top", color=color, fontsize=9.5, weight="bold", zorder=5,
                        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.8, "pad": 1})
            for pts, entered in sorted(paths[condition], key=lambda x: x[1]):
                ax.plot(pts[:, dims[0]], pts[:, dims[1]], color=FORBIDDEN_COLOR if entered else COLORS[condition],
                        alpha=0.75 if entered else 0.22, lw=1.1 if entered else 0.7, zorder=3 if entered else 2)
            starts = np.array([p[0] for p, _ in paths[condition]])
            ax.scatter(starts[:, dims[0]], starts[:, dims[1]], s=5, color="#555555", zorder=4)
            ax.plot(t[dims[0]], t[dims[1]], marker="*", color="black", ms=14, zorder=6, ls="none")
            ax.set_xlim(hi[dims[0]], lo[dims[0]])  # +y를 왼쪽에
            ax.set_ylim(lo[dims[1]], hi[dims[1]])
            ax.set_aspect("equal")
            ax.grid(alpha=0.25)
            ax.set_xlabel("y [m] (+ 방향 = 로봇 왼쪽)")
            ax.set_ylabel(yl)
            ax.set_title(f"{CONDITIONS[condition]}, {sub}: 금지 구역 진입 {k}/{n}", fontsize=11,
                         color=COLORS[condition] if condition == "safe_w0" else "#004a75", weight="bold", loc="left")
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], color=COLORS["safe_w0"], lw=2, label="대조군 (벌점 0) 궤적"),
               Line2D([], [], color=COLORS["safe_w2"], lw=2, label="벌점 2 궤적"),
               Line2D([], [], color=FORBIDDEN_COLOR, lw=2, label="첫 성공 전에 금지 구역에 들어간 궤적"),
               Line2D([], [], marker="o", color="#555555", ls="none", ms=4, label="시작점"),
               Line2D([], [], marker="*", color="black", ls="none", ms=11, label="목표")]
    fig.legend(handles=handles, loc="lower center", ncol=5, frameon=False, fontsize=9.5, bbox_to_anchor=(0.5, 0.0))
    fig.suptitle(title, fontsize=12.5, weight="bold")
    fig.tight_layout(rect=(0, 0.03, 1, 0.98))
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return counts


SEED_PANELS = [  # (평가, seeds 칸 이름, 그림 표시)
    ("policy", seeds.STANDALONE[0][0], "단독: 구역 X 중심\n금지 구역 진입 (/64)"),
    ("policy", seeds.STANDALONE[1][0], "단독: 구역 안 무작위\n진입 (/64)"),
    ("policy", seeds.STANDALONE[4][0], "단독: 구역 4cm 아래 목표\n침범 (/64)"),
    ("policy", seeds.STANDALONE[2][0], "단독: 구역 B 중심\n이동 중 침범 (/64)"),
    ("physical", seeds.PHYSICAL[0], "물리 D1: 금지 목적지\n진입 (/80)"),
    ("physical", seeds.PHYSICAL[1], "물리 D2: 허용 목적지\n이동 중 침범 (/60)"),
]


def plot_seed_stats(plt, df, binary: list[dict], seed_rows: list[dict], path: Path) -> None:
    import numpy as np
    from matplotlib.lines import Line2D

    fig = plt.figure(figsize=(14, 10))
    grid = fig.add_gridspec(2, 3, height_ratios=[1.15, 1], hspace=0.42, wspace=0.28, top=0.92)
    ax = fig.add_subplot(grid[0, :])
    offsets = {"safe_w0": -0.2, "safe_w2": 0.2}
    for gi, (kind, label, shown) in enumerate(SEED_PANELS):
        brow = next(r for r in binary if r["eval"] == kind and r["measure"] == label)
        for condition in CONDITIONS:
            pts = [r for r in seed_rows if r["eval"] == kind and r["measure"] == label and r["condition"] == condition]
            for si, r in enumerate(pts):
                x = gi + offsets[condition] + (si - 1.5) * 0.045
                ax.errorbar(x, r["rate"] * 100, yerr=[[(r["rate"] - r["wilson_lo"]) * 100], [(r["wilson_hi"] - r["rate"]) * 100]],
                            fmt="o", ms=4.5, color=COLORS[condition], elinewidth=1, capsize=2, alpha=0.85)
            x = gi + offsets[condition] + 2.6 * 0.045 * (1 if condition == "safe_w2" else -1)
            rate = brow[f"{condition}_rate"] * 100
            ax.errorbar(x, rate, yerr=[[rate - brow[f"{condition}_wilson_lo"] * 100], [brow[f"{condition}_wilson_hi"] * 100 - rate]],
                        fmt="D", ms=7, color=COLORS[condition], mec="black", mew=0.8, elinewidth=2, capsize=3)
        ax.text(gi, 104, f"피셔 p={_fmt_p(brow['fisher_p'])}\n시드 MWU p={_fmt_p(brow['seed_mwu_p'])}",
                ha="center", va="bottom", fontsize=8.5, color="#333333")
    ax.set_xticks(range(len(SEED_PANELS)), [s for _, _, s in SEED_PANELS], fontsize=9.5)
    ax.set_ylim(-4, 122)
    ax.set_yticks(range(0, 101, 20))
    ax.set_ylabel("진입·침범 비율 [%]")
    ax.set_xlim(-0.55, len(SEED_PANELS) - 0.45)
    ax.grid(axis="y", alpha=0.25)
    for gi in range(1, len(SEED_PANELS)):
        ax.axvline(gi - 0.5, color="#dddddd", lw=0.8)
    ax.set_title("(a) 학습 시드별 비율과 윌슨 95% 구간. 작은 점: 시드 42·1·2·3 순, 마름모: 4개 합산", fontsize=11, loc="left")
    handles = [Line2D([], [], marker="o", color=COLORS[c], ls="none", label=CONDITIONS[c]) for c in CONDITIONS]
    handles.append(Line2D([], [], marker="D", color="white", mec="black", ls="none", label="4개 합산"))
    ax.legend(handles=handles, loc="upper right", bbox_to_anchor=(1.0, 0.86), fontsize=9, frameon=True)

    panels = [("policy", ["zone_x"], "min_pos_err", "(b) 단독: 구역 X 중심 목표\n목표까지 최소 거리 [m]", 0.05, "구역 경계\n(5cm)"),
              ("physical", "D1_forbidden", "min_pos_err", "(c) 물리 D1: 금지 목적지 80건\n목표까지 최소 거리 [m]", 0.05, "구역 경계\n(5cm)"),
              ("policy", ["probe_below"], "min_clearance", "(d) 단독: 구역 4cm 아래 목표\n금지 구역까지 최소 여유 [m]", None, None)]
    rng = np.random.default_rng(0)
    for pi, (kind, rows_sel, col, title, ref, ref_label) in enumerate(panels):
        axp = fig.add_subplot(grid[1, pi])
        sub = select(df, kind, rows_sel)
        positions, labels = [], []
        for ci, condition in enumerate(CONDITIONS):
            for si, seed in enumerate(SEED_ORDER):
                pos = ci * 5 + si
                vals = sub[(sub["condition"] == condition) & (sub["seed"] == seed)][col].to_numpy()
                axp.boxplot([vals], positions=[pos], widths=0.6, showfliers=False,
                            medianprops={"color": "black"}, boxprops={"color": COLORS[condition]},
                            whiskerprops={"color": COLORS[condition]}, capprops={"color": COLORS[condition]})
                axp.scatter(pos + rng.uniform(-0.22, 0.22, len(vals)), vals, s=6, color=COLORS[condition], alpha=0.45, lw=0)
                positions.append(pos)
                labels.append(str(seed))
        if ref is not None:
            axp.axhline(ref, color=FORBIDDEN_COLOR, ls="--", lw=1)
            axp.text(4, ref, ref_label, color=FORBIDDEN_COLOR, fontsize=8, ha="center", va="bottom")
        if col == "min_clearance":
            axp.axhline(0, color=FORBIDDEN_COLOR, ls="--", lw=1)
            axp.text(4, 0.001, "0 =\n구역 안", color=FORBIDDEN_COLOR, fontsize=8, ha="center", va="bottom")
        axp.set_xticks(positions, labels, fontsize=8.5)
        axp.set_xlabel("학습 시드   (왼쪽 4개: 대조군, 오른쪽 4개: 벌점 2)", fontsize=8.5)
        axp.set_title(title, fontsize=10, loc="left")
        axp.grid(axis="y", alpha=0.25)
    fig.suptitle("대조군(벌점 0)과 벌점 2 정책, 학습 시드 4개씩 (정책마다 평가 1회)", fontsize=13, weight="bold", y=0.975)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------- GIF

def make_gif(left: Path, right: Path, out: Path, labels: tuple[str, str], fps: int = 10, width: int = 480,
             crop: str = "crop=600:500:310:110,") -> bool:
    """두 영상을 나란히 붙인 GIF. ffmpeg가 없거나 영상이 없으면 건너뛴다."""
    if not shutil.which("ffmpeg") or not left.exists() or not right.exists():
        print(f"건너뜀: {out} (ffmpeg 또는 영상 없음)")
        return False
    font = Path("C:/Windows/Fonts/malgunbd.ttf")
    with tempfile.TemporaryDirectory() as tmp:
        files = []
        for i, text in enumerate(labels):
            p = Path(tmp) / f"label{i}.txt"
            p.write_text(text, encoding="utf-8")
            files.append(p.as_posix().replace(":", "\\:"))
        fontopt = f":fontfile='{font.as_posix().replace(':', chr(92) + ':')}'" if font.exists() else ""
        draw = (f"drawtext=textfile='{{}}'{fontopt}:fontsize=22:fontcolor=white:box=1:boxcolor=black@0.6"
                ":boxborderw=6:x=10:y=10")
        graph = (f"[0:v]fps={fps},{crop}scale={width}:-2:flags=lanczos,{draw.format(files[0])}[a];"
                 f"[1:v]fps={fps},{crop}scale={width}:-2:flags=lanczos,{draw.format(files[1])}[b];"
                 "[a][b]hstack=inputs=2,split[s0][s1];[s0]palettegen=max_colors=128:stats_mode=diff[p];"
                 "[s1][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle")
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(left), "-i", str(right),
               "-filter_complex", graph, "-loop", "0", str(out)]
        subprocess.run(cmd, check=True)
    print(f"저장: {out} ({out.stat().st_size / 1e6:.2f} MB)")
    return True


# ---------------------------------------------------------------- 실행

def main(argv: list[str] | None = None) -> None:
    import json

    parser = argparse.ArgumentParser(description="대조군과 벌점 2의 통계 분석과 그림")
    parser.add_argument("--no-gif", action="store_true")
    args = parser.parse_args(argv)

    scene = json.loads(Path("data/scene.json").read_text(encoding="utf-8"))
    per_seed = {"policy": _per_seed(STANDALONE_DIRS, seeds.standalone_cells),
                "physical": _per_seed(PHYSICAL_DIRS, seeds.physical_cells)}
    for kind, by_condition in per_seed.items():
        for condition, by_seed in by_condition.items():
            if sorted(by_seed) != sorted(SEED_ORDER):
                raise SystemExit(f"{kind} {condition}의 시드가 {sorted(by_seed)}다. {SEED_ORDER}가 모두 있어야 한다.")

    df = load_frames()
    add_clearance(df, scene)
    binary, seed_rows = binary_stats(per_seed)
    continuous = continuous_stats(df)

    ANALYTICS.mkdir(parents=True, exist_ok=True)
    write_csv(ANALYTICS / "stats.csv", binary)
    write_csv(ANALYTICS / "stats_distance.csv", continuous)
    write_csv(ANALYTICS / "seed_rates.csv", seed_rows)
    md = markdown(binary, continuous)
    (ANALYTICS / "stats.md").write_text(md, encoding="utf-8")
    print(md)

    IMG.mkdir(parents=True, exist_ok=True)
    plt = setup_matplotlib()
    for target, name, title in [
        ("zone_b", "traj_zone_b_overlay.png", "허용 구역 B 중심을 목표로 줬을 때의 팔 끝 궤적 (정책 단독 평가, 학습 시드 4개 × 64건)"),
        ("zone_x", "traj_zone_x_overlay.png", "금지 구역 X 중심을 목표로 줬을 때의 팔 끝 궤적 (정책 단독 평가, 학습 시드 4개 × 64건)"),
    ]:
        counts = plot_traj_overlay(plt, df, scene, target, IMG / name, title)
        print(f"저장: {IMG / name}  " + ", ".join(f"{c} {k}/{n}" for c, (k, n) in counts.items()))
    plot_seed_stats(plt, df, binary, seed_rows, IMG / "seed_stats.png")
    print(f"저장: {IMG / 'seed_stats.png'}")

    if not args.no_gif:
        kit = Path("results/video_kit")
        for target in ("zone_x", "zone_b"):
            make_gif(kit / f"safe_w0_{target}_kit_0000.mp4", kit / f"safe_w2_{target}_kit_0000.mp4",
                     IMG / f"compare_{target}.gif", (CONDITIONS["safe_w0"], CONDITIONS["safe_w2"]))


if __name__ == "__main__":
    main()
