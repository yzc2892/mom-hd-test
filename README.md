# A Robust Median-of-Means Test for High-Dimensional Mean Vectors with Heavy-Tailed Noise

Code and supplementary materials for the paper accepted in *Communications in Mathematics and Statistics* (Springer, CM&S).

## Repository structure

| File | Description |
|------|-------------|
| manuscript.tex | **Final LaTeX source** for Springer CM&S submission (sn-mathphys-num style) |
| efs.bib | BibTeX database with 29 cited references |
| sn-jnl.cls | Springer Nature journal class file (required for compilation) |
| sn-mathphys-num.bst | Math & Physics numbered bibliography style file |
| ESM_1.pdf | Electronic Supplementary Material (9 pages: proofs, lemmas, additional simulations) |
| supplementary.tex | LaTeX source for the supplementary material |
| sim.py | Full simulation framework — implements MoM test, competitors, all experimental designs |
| make_figs.py | Reads simulation JSON outputs and generates figures and LaTeX tables |
| make_docx.py | Generates Word document versions of figures and tables |
| equirements.txt | Python dependencies (numpy, scipy, matplotlib) with pinned versions |
| Fig1.png–Fig6.png | Publication figures as submitted |
| LICENSE | MIT License |

## Compile the manuscript

`ash
pdflatex manuscript
bibtex   manuscript
pdflatex manuscript
pdflatex manuscript
`

The class file sn-jnl.cls and bibliography style sn-mathphys-num.bst must be in the same directory.

## Run the simulations

`ash
pip install -r requirements.txt
python sim.py            # writes results/*.json  (40-70 min for full run)
python make_figs.py      # reads results/*.json -> Fig*.png, Fig*.pdf, results_table.tex
`

### Configuration

Environment variables MOM_B (Monte Carlo reps, default 500) and MOM_R (bootstrap reps, default 100) control the computational cost.

### Experimental design

- **(n, p) grid**: (100,50), (100,200), (100,500), (200,1000)
- **Noise families**: Gaussian, multivariate t_3/t_5/t_10, standardized log-normal, contaminated mixture
- **Covariance structures**: I_p, AR(1) rho=0.5, compound symmetry rho=0.3
- **Competitors**: MoM (bootstrap), MoM-z (analytic), Bai–Saranadasa, Chen–Qin, Catoni, Huber, permutation

## Theoretical highlights

- **Theorem 1** — coordinate-wise concentration requiring only finite 2nd moment
- **Theorem 2** — asymptotic normality and bootstrap validity
- **Theorem 3** — power consistency under the detection boundary
- **Theorem 4** — ARE = 1 vs moment-based tests under light tails; moment-based tests collapse under infinite 4th moment

## Citation

If you use this code or find the paper useful, please cite:

`
Yang, Z. (2026). A Robust Median-of-Means Test for High-Dimensional Mean Vectors
with Heavy-Tailed Noise. Communications in Mathematics and Statistics.
`

## Data availability

- Simulation code and generated results: this repository
- Real data: Golub et al. (1999) leukemia gene-expression data (publicly available)
- Funding: None
- Competing interests: None
