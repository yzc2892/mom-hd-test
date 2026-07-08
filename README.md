# A Robust Median-of-Means Test for High-Dimensional Mean Vectors with Heavy-Tailed Noise

Complete submission package for *Communications in Mathematics and Statistics*
(Springer, CM&S; 中科院二区). Research Article.

## Package contents

| File | Description |
|------|-------------|
| `manuscript.tex` | **Main LaTeX source** (single file): title, structured abstract, 7 sections (Introduction, Model, Methodology, Theory, Simulations, Real Data, Discussion), Theorem 1–4 + Corollary 1, figures, tables, declarations, references. |
| `refs.bib` | BibTeX database, 50+ entries (foundational + ≥30% from 2020+). |
| `supplementary.tex` | Supplementary Material: detailed proofs of Theorems 1–4 & Corollary 1, technical lemmas (MoM Bernstein-type inequality, high-dim CLT), adaptive block-number selector, extra simulation notes. |
| `sim.py` | Simulation framework (NumPy/SciPy). Implements the MoM test (bootstrap + analytic), competitors (Bai–Saranadasa, Chen–Qin, Catoni, Huber, permutation), and the **full design**: (n,p) grid, noise families (Gaussian, multivariate t₃/t₅/t₁₀, log-normal, contaminated), covariance structures (I, AR(1), compound symmetry). Writes `results/*.json`. |
| `make_figs.py` | Reads `results/*.json`; produces `Fig1.png/.pdf … Fig6.png/.pdf` and the LaTeX tables `results_table.tex`, `timing_table.tex`. |
| `results/` | Generated JSON, figures, and generated `.tex` tables. `results.csv` (legacy) also present. |

## Compile the LaTeX

```bash
# Main manuscript
pdflatex manuscript
bibtex   manuscript
pdflatex manuscript
pdflatex manuscript

# Supplementary material
pdflatex supplementary
bibtex   supplementary
pdflatex supplementary
pdflatex supplementary
```

Notes:
- The source uses `natbib` + `plainnat` so it compiles in any standard LaTeX
  install. **For the actual CM&S submission**, change
  `\bibliographystyle{plainnat}` to `\bibliographystyle{spbasic}` (Springer
  numeric style) and use the journal's `svjour3` class if required.
- Figures are pulled from `results/` via `\graphicspath{{results/}}`; run
  `sim.py` and `make_figs.py` first so `Fig1..Fig6` and the `.tex` tables exist.
- The `results_table.tex` / `timing_table.tex` files are **generated from the
  real Monte-Carlo output** — the numbers in the paper are not hand-filled.

## Run the simulations

```bash
python sim.py            # writes results/*.json
python make_figs.py      # fast; writes Fig1..Fig6 + the .tex tables
```

Runtime scales with the Monte-Carlo and bootstrap sizes. At the default
`MOM_B=500`, `MOM_R=100` a full pass takes roughly **40–70 minutes** (the
`p=1000` / multivariate-`t` configurations dominate). For a quick preview use
`MOM_B=300 MOM_R=50`.

Environment variables:
`MOM_B` (Monte Carlo reps, default 500), `MOM_R` (bootstrap reps, default 100).

Requirements: `numpy`, `scipy` (incl. `scipy.stats.multivariate_t`),
`matplotlib`.

## Design at a glance

- **Scenario A** `(n,p)`: `(100,50)`, `(100,200)`, `(100,500)`, `(200,1000)`.
- **Scenario B** noise: Gaussian; multivariate `t_ν`, `ν∈{3,5,10}`; standardized
  log-normal; contaminated mixture `(1−ε)N+εN(0,9Σ)`, `ε∈{0.05,0.1}`.
- **Scenario C** covariance: `I_p`; AR(1) `ρ=0.5`; compound symmetry `ρ=0.3`.
- **Competitors** (all at α=0.05, same (n,p)): MoM (proposed, bootstrap),
  MoM-z (proposed, analytic), Bai–Saranadasa, Chen–Qin, Catoni, Huber,
  permutation.
- **Metrics**: empirical Type-I error, power vs signal strength, compute time.

## Theoretical highlights

- **Theorem 1** — coordinate-wise concentration
  `‖μ̂_MoM − μ‖_∞ = O_P(√(log p/n))` using only a finite 2nd moment.
- **Theorem 2** — asymptotic null `T_n → N(0,1)` (analytic) / bootstrap-valid
  calibration needing only 2nd moment.
- **Theorem 3** — power → 1 when `SNR_n → ∞` (detection boundary
  `‖μ−μ₀‖²√(n/p) → ∞` under identity covariance).
- **Theorem 4** — ARE = 1 vs moment-based tests under light tails; moment-based
  tests collapse under infinite 4th moment.
- **Corollary 1** — explicit rates for multivariate `t_ν` (ν>2), log-normal, and
  contamination.

## Data availability & declarations

- Simulation code and generated results: public repository
  `https://github.com/[username]/mom-hd-test` (placeholder — set before submission).
- Real data: Golub et al. (1999) leukemia gene-expression data (public).
- Funding: none. Competing interests: none. Author contributions follow CRediT.
