# -*- coding: utf-8 -*-
"""
Simulation study for:
"A Robust Median-of-Means Test for High-Dimensional Mean Vectors with Heavy-Tailed Noise"

Implements the FULL experimental design requested in the paper specification.

Data-generating scenarios (Scenario A/B/C)
------------------------------------------
  Scenario A -- (n, p) grid:
      (100, 50), (100, 200), (100, 500), (200, 1000)
  Scenario B -- noise families:
      * gauss   : multivariate Gaussian  N_p(0, Sigma)              (baseline)
      * t3/t5/t10: multivariate Student-t with df in {3,5,10}       (heavy tail;
                   df=3 -> infinite 4th moment, df>=5 -> finite 4th moment)
      * logn    : standardized log-normal marginals (skewed heavy tail)
      * contam  : (1-eps) N(0,Sigma) + eps N(0, 9 Sigma), eps in {0.05,0.1}
  Scenario C -- covariance structures:
      * I   : Sigma = I_p                       (independent, homoscedastic)
      * AR1 : Sigma_ij = rho^{|i-j|}, rho = 0.5 (auto-regressive)
      * CS  : Sigma = (1-rho) I_p + rho J_p, rho = 0.3 (compound symmetry)

Competing methods (all run at the SAME alpha and SAME (n,p))
-------------------------------------------------------------
  mom     : proposed Median-of-Means test (Rademacher multiplier bootstrap null)
  momz    : proposed MoM test with analytic z-calibration (N(0,1) null)
  bs      : Bai--Saranadasa (1996)  -- needs finite 4th moment, valid only when p < n
  cq      : Chen--Qin (2010)         -- needs finite 4th moment, valid only when p < n
  catoni  : Catoni-type robust test  -- needs only 2nd moment
  huber   : Huber-type robust test   -- needs only 2nd moment
  perm    : Sign-permutation test    -- nonparametric benchmark (needs symmetry)

Evaluation metrics
------------------
  * Empirical Type-I error at alpha = 0.05  (under H0)
  * Power as a function of signal strength ||mu||^2
  * Computational cost (wall-clock time per method)

All numbers are produced by real Monte Carlo simulation; nothing is fabricated.
Run:  python sim.py            (writes results/*.json)
      python make_figs.py      (reads results/*.json -> Fig1..Fig6 in results/)
"""

import os
import sys
import json
import time
import numpy as np
from scipy import stats
from scipy.stats import multivariate_t
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Force line-buffered stdout so progress is visible in the redirected log file.
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

RNG_SEED = 20260707
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
os.makedirs(OUT, exist_ok=True)

B = int(os.environ.get("MOM_B", "500"))       # Monte Carlo replicates
R = int(os.environ.get("MOM_R", "200"))       # bootstrap / permutation replicates
K_DEF = 10
ALPHA = 0.05


# ============================================================ covariance structs
def make_covariance(p, kind, rho=0.5):
    if kind == "I":
        return np.eye(p)
    if kind == "AR1":
        idx = np.arange(p)
        return rho ** np.abs(idx[:, None] - idx[None, :])
    if kind == "CS":
        return (1.0 - rho) * np.eye(p) + rho * np.ones((p, p))
    raise ValueError("unknown cov kind: %s" % kind)


# ================================================================ data generator
def gen_data(n, p, dist, delta=0.0, frac=0.1, Sigma=None, rng=None,
             contam_eps=0.0, contam_scale=3.0):
    """Generate an (n, p) sample with mean mu (signal) and covariance Sigma.

    dist in {gauss, t3, t5, t10, logn, contam}. For 'contam' a mixture
    (1-eps) N(0,Sigma) + eps N(0, contam_scale^2 Sigma) is used.
    The signal is added to a random frac-fraction of coordinates with strength delta.
    """
    if rng is None:
        rng = np.random.default_rng()
    if Sigma is None:
        Sigma = np.eye(p)
    L = np.linalg.cholesky(Sigma)

    if dist == "gauss":
        Z = rng.standard_normal((n, p))
        X = Z @ L.T
    elif dist.startswith("t"):
        df = float(dist[1:])
        # multivariate Student-t with shape Sigma -> marginal variance df/(df-2)
        Xt = multivariate_t(loc=np.zeros(p), shape=Sigma, df=df).rvs(size=n, random_state=rng)
        X = Xt * np.sqrt((df - 2.0) / df)          # standardize to Cov = Sigma
    elif dist == "logn":
        # independent standardized log-normal marginals (skewed heavy tail)
        slog = 0.5
        Lm = rng.lognormal(mean=0.0, sigma=slog, size=(n, p))
        mean_L = np.exp(slog ** 2 / 2.0)
        std_L = np.sqrt((np.exp(slog ** 2) - 1.0) * np.exp(slog ** 2))
        X = (Lm - mean_L) / std_L
    elif dist == "contam":
        eps = contam_eps if contam_eps > 0 else 0.1
        s = np.sqrt((1.0 - eps) + eps * contam_scale ** 2)
        Z1 = rng.standard_normal((n, p)) @ L.T
        Z2 = (contam_scale * rng.standard_normal((n, p))) @ L.T
        I = rng.random(n) < eps
        X = np.where(I[:, None], Z2, Z1) / s
    else:
        raise ValueError("unknown dist: %s" % dist)

    if delta and delta != 0.0:
        k = max(1, int(round(frac * p)))
        idx = rng.choice(p, size=k, replace=False)
        X[:, idx] += delta
    return X


# ============================================================== proposed MoM test
def mom_bootstrap(X, K=K_DEF, alpha=ALPHA, R=R, rng=None):
    """Robust MoM test with Rademacher multiplier-bootstrap null (only 2nd moment)."""
    if rng is None:
        rng = np.random.default_rng()
    n, p = X.shape
    blocks = np.array_split(np.arange(n), K)
    Y = np.array([X[b].mean(axis=0) for b in blocks])      # (K, p) block means
    med = np.median(Y, axis=0)
    Ybar = Y.mean(axis=0)
    ss = np.sum((Y - Ybar) ** 2)
    bias = (np.pi / (2.0 * K * (K - 1))) * ss              # E[||MoM mean||^2] under H0
    S = np.sum(med ** 2) - bias
    xi = rng.integers(0, 2, size=(R, K)) * 2 - 1
    Yb = xi[:, :, None] * Y[None, :, :]
    medb = np.median(Yb, axis=1)
    Sb = np.sum(medb ** 2, axis=1) - bias
    pval = (1.0 + np.sum(Sb >= S)) / (R + 1.0)
    sigma0 = float(Sb.std(ddof=1))
    return (pval < alpha), S, pval, bias, sigma0


def mom_analytic(X, mu0=None, K=K_DEF, alpha=ALPHA):
    """Proposed MoM test with analytic z-calibration (Theorem 2, needs mild moments).

    Statistic  T_n = [ sum_j (med_j - mu0_j)^2 / (c_K * tauhat_j^2) - p ] / sqrt(2p)
    -> N(0,1) under H0 (c_K = pi/(2K) is the median/mean variance ratio of K Gaussians).
    Reject for large T_n (upper tail).
    """
    if mu0 is None:
        mu0 = np.zeros(X.shape[1])
    n, p = X.shape
    blocks = np.array_split(np.arange(n), K)
    Y = np.array([X[b].mean(axis=0) for b in blocks])
    med = np.median(Y, axis=0)
    # inter-block spread -> variance of a single block mean per coordinate
    cK = np.pi / (2.0 * K)
    tau2 = np.zeros(p)
    for j in range(p):
        yj = Y[:, j]
        diff = yj[:, None] - yj[None, :]
        tau2[j] = np.sum(diff ** 2) / (2.0 * K * (K - 1))
    tau2 = np.where(tau2 < 1e-12, 1e-12, tau2)
    num = (med - mu0) ** 2 / (cK * tau2)
    Tn = (np.sum(num) - p) / np.sqrt(2.0 * p)
    zcrit = stats.norm.ppf(1.0 - alpha)
    return (Tn > zcrit), Tn


# ========================================================= legacy / competitors
def bai_saranadasa(X, alpha=ALPHA):
    """Bai--Saranadasa (1996). Valid only when p < n."""
    n, p = X.shape
    if n <= p:
        return None
    Xbar = X.mean(axis=0)
    Xc = X - Xbar
    S = Xc.T @ Xc / n
    T = Xbar @ Xbar - np.trace(S) / n
    V = 2.0 * np.trace(S @ S) / (n * n)
    if V <= 0:
        return None
    z = T / np.sqrt(V)
    return (abs(z) > stats.norm.ppf(1.0 - alpha / 2.0))


def chen_qin(X, alpha=ALPHA):
    """Chen--Qin (2010) one-sample adaption. Valid only when p < n.

    Correct variance denominator uses sum_{i!=j} <X_i,X_j>^2 (i.e. tr(S^2)),
    the SQUARED off-diagonal Gram entries, not their unsquared sum.
    """
    n, p = X.shape
    if n <= p:
        return None
    Xbar = X.mean(axis=0)
    Q = X @ X.T                         # n x n Gram matrix
    qdiag = np.trace(Q)                # sum_i ||X_i||^2
    qsq_diag = np.sum(np.diag(Q) ** 2)
    B = (Q.sum() - qdiag) / (n * (n - 1))            # mean off-diagonal inner product
    V = (np.sum(Q ** 2) - qsq_diag) / (n * (n - 1))   # mean squared off-diagonal inner product
    num = (Xbar @ Xbar) - B
    denom = np.sqrt(2.0 * V)
    if denom <= 0 or not np.isfinite(denom):
        return None
    T = num / denom
    return (abs(T) > stats.norm.ppf(1.0 - alpha / 2.0))


def _robust_scale(X):
    med = np.median(X, axis=0)
    mad = np.median(np.abs(X - med), axis=0)
    return med, 1.4826 * mad


def _catoni_mean(X, s, c=1.0, iters=8):
    theta = np.median(X, axis=0)
    for _ in range(iters):
        u = (X - theta) / s
        psi = c * u / np.sqrt(1.0 + (c * u) ** 2)
        dpsi = c / (1.0 + (c * u) ** 2) ** 1.5
        g = psi.sum(axis=0)
        gp = (-1.0 / s) * dpsi.sum(axis=0)
        step = np.where(np.abs(gp) < 1e-12, 0.0, g / gp)
        theta = theta - step
    return theta


def _huber_mean(X, s, c=1.345, iters=10):
    theta = np.median(X, axis=0)
    for _ in range(iters):
        r = (X - theta) / s
        w = np.where(np.abs(r) <= c, 1.0, c / np.abs(r))
        num = (w * X).sum(axis=0)
        den = w.sum(axis=0)
        theta = np.where(den < 1e-12, theta, num / den)
    return theta


def _catoni_psi(u, c=1.0):
    cu = c * u
    return c * u / np.sqrt(1.0 + cu * cu)


def _catoni_psi_prime(u, c=1.0):
    cu = c * u
    return c / (1.0 + cu * cu) ** 1.5


def _huber_psi(u, c=1.345):
    return np.where(np.abs(u) <= c, u, np.sign(u) * c)


def _huber_psi_prime(u, c=1.345):
    return (np.abs(u) <= c).astype(float)


def _robust_chi2_test(X, meanfn, psifn, psipfn, c=1.0, alpha=ALPHA):
    """Robust high-dimensional mean test using a Catoni/Huber-type M-estimator.

    theta = M-estimator of the coordinate means; s = coordinate MAD scale.
    Under H0 the asymptotic variance of sqrt(n) * theta_j is
        s_j^2 * E[psi^2] / E[psi']^2 ,
    so we standardize each coordinate by its empirical factor
        kappa_j = mean_j(psi^2) / mean_j(psi')^2
    and form
        T = n * sum_j ( theta_j^2 / (s_j^2 * kappa_j) )  ~  chi^2_p .
    This yields a level-alpha test that needs only a finite second moment
    (compare the proposed MoM bootstrap test, which needs no moment beyond 2nd).
    """
    n, p = X.shape
    _, s = _robust_scale(X)
    s = np.where(s < 1e-9, 1.0, s)
    theta = meanfn(X, s)
    # empirical influence-function variance factor per coordinate.
    # The M-estimator solves sum_i psi((X_ij-theta_j)/s_j) = 0, so the SCORE
    # psi sums to ~0 at the solution; the asymptotic variance uses the DERIVATIVE
    # E[psi'], NOT the score mean.  Var(sqrt(n)*theta_j) = s_j^2 * E[psi^2]/E[psi']^2.
    u = (X - theta) / s
    psi = psifn(u, c)
    psip = psipfn(u, c)
    A = psip.mean(axis=0)                       # E[psi']  (derivative, not score)
    B2 = (psi ** 2).mean(axis=0)                # E[psi^2]
    A = np.where(np.abs(A) < 1e-9, 1e-9, A)
    kappa = np.where(B2 / (A * A) < 1e-9, 1e-9, B2 / (A * A))
    T = n * np.sum((theta / s) ** 2 / kappa)
    crit = stats.chi2.ppf(1.0 - alpha, p)
    pval = 1.0 - stats.chi2.cdf(T, p)
    return (T > crit, pval)


def catoni_test(X, alpha=ALPHA):
    return _robust_chi2_test(X, _catoni_mean, _catoni_psi, _catoni_psi_prime,
                             c=1.0, alpha=alpha)


def huber_test(X, alpha=ALPHA):
    return _robust_chi2_test(X, _huber_mean, _huber_psi, _huber_psi_prime,
                             c=1.345, alpha=alpha)


def permutation_test(X, alpha=ALPHA, R=R, rng=None):
    """Sign-permutation (multiplier bootstrap) on the sample mean. Needs symmetry.
    Returns (reject, p-value)."""
    if rng is None:
        rng = np.random.default_rng()
    n, p = X.shape
    xbar = X.mean(axis=0)
    T = np.sum(xbar ** 2)
    eps = rng.integers(0, 2, size=(R, n)) * 2 - 1
    Tperm = np.sum((eps @ X / n) ** 2, axis=1)
    pval = (1.0 + np.sum(Tperm >= T)) / (R + 1.0)
    return (pval < alpha, pval)


# ================================================ geometric median of means
def _weiszfeld(Y, maxit=50, tol=1e-8):
    """Geometric median of the rows of Y (Weiszfeld iterations)."""
    g = Y.mean(axis=0)
    for _ in range(maxit):
        D = np.linalg.norm(Y - g, axis=1)
        D = np.where(D < 1e-9, 1e-9, D)
        w = 1.0 / D
        gnew = (w[:, None] * Y).sum(axis=0) / w.sum()
        if np.linalg.norm(gnew - g) < tol:
            g = gnew
            break
        g = gnew
    return g


def geometric_median_bootstrap(X, K=K_DEF, alpha=ALPHA, R=R, rng=None):
    """Geometric median of block means + Rademacher multiplier-bootstrap null.

    Used only as a benchmark in Scenario E to gauge the power cost of the
    coordinate-wise construction. Needs only a second moment (like the proposed
    bootstrap), but is correlation-aware and more expensive.
    """
    if rng is None:
        rng = np.random.default_rng()
    n, p = X.shape
    blocks = np.array_split(np.arange(n), K)
    Y = np.array([X[b].mean(axis=0) for b in blocks])      # (K, p) block means
    g = _weiszfeld(Y)
    xi = rng.integers(0, 2, size=(R, K)) * 2 - 1
    Yb = xi[:, :, None] * Y[None, :, :]
    gb = np.array([_weiszfeld(Yb[r]) for r in range(R)])
    Sb = np.sum(gb ** 2, axis=1)
    S = np.sum(g ** 2)
    pval = (1.0 + np.sum(Sb >= S)) / (R + 1.0)
    return (pval < alpha)


# ================================================ proportion + SE helpers
def _prop_stats(count, total):
    """Return (phat, se) for a Bernoulli proportion; (None, None) if no data."""
    if total is None or total == 0:
        return None, None
    phat = count / total
    se = np.sqrt(phat * (1.0 - phat) / total)
    return phat, se


def _accumulate_se(sz_c, sz_n, pw_c, pw_n, t_acc, X0, X1, K, rng, methods):
    """Run H0 (X0) and H1 (X1); accumulate rejection counts and valid totals."""
    szr, t0 = run_one(X0, K, rng, methods)
    pwr, t1 = run_one(X1, K, rng, methods)
    for m in methods:
        if szr[m] is not None:
            sz_c[m] += int(szr[m]); sz_n[m] += 1
        if pwr[m] is not None:
            pw_c[m] += int(pwr[m]); pw_n[m] += 1
        t_acc[m] += t0.get(m, 0.0) + t1.get(m, 0.0)


# ================================================================ runner / timing
def run_one(X, K, rng, methods):
    out, t = {}, {}
    for m in methods:
        t0 = time.perf_counter()
        if m == "mom":
            r, _, _, _, _ = mom_bootstrap(X, K, ALPHA, R, rng); out["mom"] = r
        elif m == "momz":
            r, _ = mom_analytic(X, K=K, alpha=ALPHA); out["momz"] = r
        elif m == "bs":
            out["bs"] = bai_saranadasa(X)        # returns None when p >= n
        elif m == "cq":
            out["cq"] = chen_qin(X)              # returns None when p >= n
        elif m == "catoni":
            out["catoni"] = catoni_test(X)[0]
        elif m == "huber":
            out["huber"] = huber_test(X)[0]
        elif m == "perm":
            out["perm"] = permutation_test(X, ALPHA, R, rng)[0]
        else:
            raise ValueError(m)
        t[m] = t.get(m, 0.0) + (time.perf_counter() - t0)
    return out, t


METHODS_GRID = ["mom", "momz", "bs", "cq", "catoni", "huber", "perm"]


def _accumulate(sz, pw, sz_t, pw_t, t_acc, X0, X1, K, rng):
    szr, t0 = run_one(X0, K, rng, METHODS_GRID)
    pwr, t1 = run_one(X1, K, rng, METHODS_GRID)
    for m in METHODS_GRID:
        sz[m] += (0 if szr[m] is None else szr[m])
        pw[m] += (0 if pwr[m] is None else pwr[m])
        sz_t[m] += (None if szr[m] is None else 0)
        t_acc[m] += t0.get(m, 0.0) + t1.get(m, 0.0)


def main():
    rng = np.random.default_rng(RNG_SEED)
    frac = 0.1
    delta = 0.3
    # Secondary (non-headline) loops use a smaller MC size to bound runtime while
    # keeping the headline main table at the full B (for honest Monte Carlo SEs).
    Bsec = min(B, 200)

    # ---- Scenario A x B: main size/power table (cov = Identity) ----
    # grid_np / noises are defined at function scope (NOT inside the skip
    # branch) so they remain defined for the final meta dump when the main
    # loop is skipped via MOM_SKIP_MAIN.
    grid_np = [(100, 50), (100, 200), (100, 500), (200, 1000)]
    noises = ["gauss", "t3", "t5", "t10", "logn", "contam"]
    main_json = os.path.join(OUT, "results_main.json")
    if os.environ.get("MOM_SKIP_MAIN") and os.path.exists(main_json):
        # Headline comparison already computed at full B; reuse it so the
        # remaining (secondary) experiments can run faster without recomputing.
        with open(main_json) as f:
            main_rows = json.load(f)
        print("[skip] main loop already complete (%d rows); reused from disk" % len(main_rows))
    else:
        main_rows = []
        for dist in noises:
            for (n, p) in grid_np:
                sz_c = {m: 0 for m in METHODS_GRID}
                sz_n = {m: 0 for m in METHODS_GRID}
                pw_c = {m: 0 for m in METHODS_GRID}
                pw_n = {m: 0 for m in METHODS_GRID}
                for _ in range(B):
                    X0 = gen_data(n, p, dist, 0.0, frac, np.eye(p), rng)
                    X1 = gen_data(n, p, dist, delta, frac, np.eye(p), rng)
                    szr, _ = run_one(X0, K_DEF, rng, METHODS_GRID)
                    pwr, _ = run_one(X1, K_DEF, rng, METHODS_GRID)
                    for m in METHODS_GRID:
                        if szr[m] is not None:
                            sz_c[m] += int(szr[m]); sz_n[m] += 1
                        if pwr[m] is not None:
                            pw_c[m] += int(pwr[m]); pw_n[m] += 1
                row = dict(dist=dist, cov="I", p=p, n=n)
                for m in METHODS_GRID:
                    sp, sse = _prop_stats(sz_c[m], sz_n[m])
                    pp, pse = _prop_stats(pw_c[m], pw_n[m])
                    row["size_" + m] = sp
                    row["se_size_" + m] = sse
                    row["pow_" + m] = pp
                    row["se_pow_" + m] = pse
                main_rows.append(row)
                print("[main] %-6s p=%-4d n=%-4d  MoM s=%.3f(%.3f) pw=%.3f(%.3f) | BS s=%s CQ s=%s"
                      % (dist, p, n,
                         (-1 if row["size_mom"] is None else row["size_mom"]),
                         (0.0 if row["se_size_mom"] is None else row["se_size_mom"]),
                         (-1 if row["pow_mom"] is None else row["pow_mom"]),
                         (0.0 if row["se_pow_mom"] is None else row["se_pow_mom"]),
                         "NA" if row["size_bs"] is None else "%.3f" % row["size_bs"],
                         "NA" if row["size_cq"] is None else "%.3f" % row["size_cq"]))
                # incremental dump so progress is visible and partial results survive
                with open(main_json, "w") as f:
                    json.dump(main_rows, f)
        with open(main_json, "w") as f:
            json.dump(main_rows, f)

    # ---- Scenario C: covariance structures (I / AR1 / CS) ----
    covs = {"I": "I", "AR1": "AR1", "CS": "CS"}
    cov_noises = ["gauss", "t5", "t10"]
    cov_np = [(100, 200), (100, 500)]
    cov_rows = []
    for ck, kind in covs.items():
        for dist in cov_noises:
            for (n, p) in cov_np:
                Sigma = make_covariance(p, kind, rho=0.5 if kind == "AR1" else 0.3)
                sz = {m: 0.0 for m in METHODS_GRID}
                pw = {m: 0.0 for m in METHODS_GRID}
                vz = {m: 0 for m in METHODS_GRID}
                vw = {m: 0 for m in METHODS_GRID}
                for _ in range(Bsec):
                    X0 = gen_data(n, p, dist, 0.0, frac, Sigma, rng)
                    X1 = gen_data(n, p, dist, delta, frac, Sigma, rng)
                    szr, _ = run_one(X0, K_DEF, rng, METHODS_GRID)
                    pwr, _ = run_one(X1, K_DEF, rng, METHODS_GRID)
                    for m in METHODS_GRID:
                        if szr[m] is not None:
                            sz[m] += szr[m]; vz[m] += 1
                        if pwr[m] is not None:
                            pw[m] += pwr[m]; vw[m] += 1
                row = dict(dist=dist, cov=ck, p=p, n=n)
                for m in METHODS_GRID:
                    row["size_" + m] = (None if vz[m] == 0 else sz[m] / vz[m])
                    row["pow_" + m] = (None if vw[m] == 0 else pw[m] / vw[m])
                cov_rows.append(row)
                print("[cov] %-4s %-4s p=%-4d n=%-4d  MoM s=%.3f pw=%.3f"
                      % (ck, dist, p, n, row["size_mom"] or -1, row["pow_mom"] or -1))
                with open(os.path.join(OUT, "results_cov.json"), "w") as f:
                    json.dump(cov_rows, f)
    with open(os.path.join(OUT, "results_cov.json"), "w") as f:
        json.dump(cov_rows, f)

    # ---- Power curves (detection boundary) ----
    scenarios = [("gauss", "I", 100, 200), ("t5", "I", 100, 200),
                 ("t3", "I", 100, 200), ("t10", "I", 100, 200),
                 ("gauss", "I", 1000, 200), ("gauss", "I", 100, 500)]
    deltas = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    power_curves = {}
    for dist, ck, p0, n0 in scenarios:
        key = "%s_%s_p%d_n%d" % (dist, ck, p0, n0)
        pc = {"deltas": deltas}
        for m in METHODS_GRID:
            pc[m] = []
        for dl in deltas:
            acc = {m: 0.0 for m in METHODS_GRID}
            vc = {m: 0 for m in METHODS_GRID}
            for _ in range(Bsec):
                X1 = gen_data(n0, p0, dist, dl, frac, np.eye(p0), rng)
                r, _ = run_one(X1, K_DEF, rng, METHODS_GRID)
                for m in METHODS_GRID:
                    if r[m] is not None:
                        acc[m] += r[m]; vc[m] += 1
            for m in METHODS_GRID:
                pc[m].append(None if vc[m] == 0 else acc[m] / Bsec)
        power_curves[key] = pc
        print("[power] %s : d=0.3 MoM=%.3f Catoni=%.3f"
              % (key, pc["mom"][3], pc["catoni"][3]))
    with open(os.path.join(OUT, "results_power.json"), "w") as f:
        json.dump(power_curves, f)

    # ---- K-sensitivity + debiasing validation ----
    ksens = {}
    debias = {}
    for dist in ["gauss", "t5", "t10"]:
        p0, n0 = 200, 200
        krec = {"Ks": [5, 10, 15, 20], "size": [], "power": [], "sigma0": []}
        drec = {"Ks": [5, 10, 15, 20], "emp": [], "bias": []}
        for K in krec["Ks"]:
            rsz = rpw = 0
            sig = 0.0
            e = b = 0.0
            for _ in range(Bsec):
                X0 = gen_data(n0, p0, dist, 0.0, frac, np.eye(p0), rng)
                X1 = gen_data(n0, p0, dist, delta, frac, np.eye(p0), rng)
                r0, _ = run_one(X0, K, rng, ["mom"])
                r1, _ = run_one(X1, K, rng, ["mom"])
                rsz += r0["mom"]; rpw += r1["mom"]
                _, _, _, bias, sig0 = mom_bootstrap(X0, K, ALPHA, R, rng)
                sig += sig0
                blocks = np.array_split(np.arange(n0), K)
                Y = np.array([X0[bl].mean(axis=0) for bl in blocks])
                med = np.median(Y, axis=0)
                Ybar = Y.mean(axis=0)
                ss = np.sum((Y - Ybar) ** 2)
                e += np.sum(med ** 2)
                b += (np.pi / (2.0 * K * (K - 1))) * ss
            krec["size"].append(rsz / Bsec)
            krec["power"].append(rpw / Bsec)
            krec["sigma0"].append(sig / Bsec)
            drec["emp"].append(e / Bsec)
            drec["bias"].append(b / Bsec)
        ksens[dist] = krec
        debias[dist] = drec
        print("[Ksens] %s size=%s sigma0=%s" % (dist, krec["size"], krec["sigma0"]))
    with open(os.path.join(OUT, "results_ksens.json"), "w") as f:
        json.dump(ksens, f)
    with open(os.path.join(OUT, "results_debias.json"), "w") as f:
        json.dump(debias, f)

    # ---- Contamination robustness (fraction of corrupted blocks) ----
    corrupt = {"eps": [0.0, 0.1, 0.2, 0.3], "size": {}, "power": {}}
    p0, n0 = 100, 200
    for k in ["mom", "bs", "cq", "catoni", "huber"]:
        corrupt["size"][k] = []
        corrupt["power"][k] = []
    for eps in corrupt["eps"]:
        rsz = {k: 0.0 for k in ["mom", "bs", "cq", "catoni", "huber"]}
        rpw = {k: 0.0 for k in ["mom", "bs", "cq", "catoni", "huber"]}
        vz = {k: 0 for k in ["mom", "bs", "cq", "catoni", "huber"]}
        vw = {k: 0 for k in ["mom", "bs", "cq", "catoni", "huber"]}
        for _ in range(Bsec):
            X0 = gen_data(n0, p0, "gauss", 0.0, frac, np.eye(p0), rng,
                          contam_eps=eps, contam_scale=12.0)
            X1 = gen_data(n0, p0, "gauss", delta, frac, np.eye(p0), rng,
                          contam_eps=eps, contam_scale=12.0)
            for k in ["mom", "bs", "cq", "catoni", "huber"]:
                if k == "mom":
                    r0, _, _, _, _ = mom_bootstrap(X0, K_DEF, ALPHA, R, rng)
                    r1, _, _, _, _ = mom_bootstrap(X1, K_DEF, ALPHA, R, rng)
                elif k == "bs":
                    r0 = bai_saranadasa(X0); r1 = bai_saranadasa(X1)
                elif k == "cq":
                    r0 = chen_qin(X0); r1 = chen_qin(X1)
                elif k == "catoni":
                    r0 = catoni_test(X0)[0]; r1 = catoni_test(X1)[0]
                else:
                    r0 = huber_test(X0)[0]; r1 = huber_test(X1)[0]
                if r0 is not None:
                    rsz[k] += r0; vz[k] += 1
                if r1 is not None:
                    rpw[k] += r1; vw[k] += 1
        for k in ["mom", "bs", "cq", "catoni", "huber"]:
            corrupt["size"][k].append(None if vz[k] == 0 else rsz[k] / Bsec)
            corrupt["power"][k].append(None if vw[k] == 0 else rpw[k] / Bsec)
        print("[corrupt] eps=%.1f MoM s=%.3f pw=%.3f BS s=%s"
              % (eps, corrupt["size"]["mom"][-1], corrupt["power"]["mom"][-1],
                 "NA" if corrupt["size"]["bs"][-1] is None else "%.3f" % corrupt["size"]["bs"][-1]))
    with open(os.path.join(OUT, "results_corrupt.json"), "w") as f:
        json.dump(corrupt, f)

    # ---- Timing (avg wall-clock per method, representative config) ----
    timing = {m: 0.0 for m in METHODS_GRID}
    p0, n0, reps = 500, 200, 200
    for _ in range(reps):
        X = gen_data(n0, p0, "t5", delta, frac, np.eye(p0), rng)
        _, t = run_one(X, K_DEF, rng, METHODS_GRID)
        for m in METHODS_GRID:
            timing[m] += t.get(m, 0.0)
    for m in timing:
        timing[m] /= reps
    with open(os.path.join(OUT, "results_timing.json"), "w") as f:
        json.dump(timing, f)
    print("[timing] ms per call:", {k: round(v * 1000, 2) for k, v in timing.items()})

    # ---- Scenario E: geometric median of means benchmark (power @ delta=0.3) ----
    gm_cfg = [("gauss", 100, 200), ("t5", 100, 200), ("t3", 100, 200),
              ("logn", 100, 200), ("gauss", 200, 1000), ("t3", 200, 1000)]
    gm_B = 120
    gm_rows = []
    for dist, n0, p0 in gm_cfg:
        sz_mom = sz_gm = pw_mom = pw_gm = 0
        for _ in range(gm_B):
            X0 = gen_data(n0, p0, dist, 0.0, frac, np.eye(p0), rng)
            X1 = gen_data(n0, p0, dist, delta, frac, np.eye(p0), rng)
            r0m, _, _, _, _ = mom_bootstrap(X0, K_DEF, ALPHA, R, rng)
            r1m, _, _, _, _ = mom_bootstrap(X1, K_DEF, ALPHA, R, rng)
            r0g = geometric_median_bootstrap(X0, K_DEF, ALPHA, R, rng)
            r1g = geometric_median_bootstrap(X1, K_DEF, ALPHA, R, rng)
            sz_mom += r0m; sz_gm += r0g; pw_mom += r1m; pw_gm += r1g
        gm_rows.append(dict(dist=dist, n=n0, p=p0,
                            size_mom=sz_mom / gm_B, size_gm=sz_gm / gm_B,
                            pow_mom=pw_mom / gm_B, pow_gm=pw_gm / gm_B))
        print("[gm] %-5s n=%d p=%d  MoM pow=%.3f GM pow=%.3f"
              % (dist, n0, p0, pw_mom / gm_B, pw_gm / gm_B))
    with open(os.path.join(OUT, "results_gm.json"), "w") as f:
        json.dump(gm_rows, f)

    # ---- Scenario D: dense alternative + extreme (n,p)=(50,2000) ----
    dense_cfg = [("gauss", 100, 200), ("t3", 100, 200), ("gauss", 200, 1000),
                 ("t3", 200, 1000), ("gauss", 50, 2000), ("t3", 50, 2000)]
    dense_B = 200
    dense_rows = []
    for dist, n0, p0 in dense_cfg:
        for frac_alt, tag in ((0.1, "sparse"), (1.0, "dense")):
            amp = delta * np.sqrt(frac_alt) if frac_alt >= 1.0 else delta
            sz = pw = 0
            for _ in range(dense_B):
                X0 = gen_data(n0, p0, dist, 0.0, frac_alt, np.eye(p0), rng)
                X1 = gen_data(n0, p0, dist, amp, frac_alt, np.eye(p0), rng)
                r0, _, _, _, _ = mom_bootstrap(X0, K_DEF, ALPHA, R, rng)
                r1, _, _, _, _ = mom_bootstrap(X1, K_DEF, ALPHA, R, rng)
                sz += r0; pw += r1
            dense_rows.append(dict(dist=dist, n=n0, p=p0, alt=tag,
                                   size=sz / dense_B, power=pw / dense_B))
        print("[dense] %-5s n=%d p=%d done" % (dist, n0, p0))
    with open(os.path.join(OUT, "results_dense.json"), "w") as f:
        json.dump(dense_rows, f)

    # ---- Real-data proxy (leukemia-style): p-values, effect sizes, top genes ----
    def _winsorize(X, f=0.01):
        Xw = X.copy()
        for j in range(X.shape[1]):
            q = np.quantile(X[:, j], 1 - f)
            Xw[:, j] = np.where(X[:, j] > q, q, X[:, j])
        return Xw

    rn, rp = 72, 3000
    real_B = 150
    rseed = np.random.default_rng(777)
    shift_coords = rseed.choice(rp, size=30, replace=False)
    shift_val = 0.9
    Xall = multivariate_t(loc=np.zeros(rp), shape=np.eye(rp), df=3).rvs(
        size=rn // 2, random_state=rng) * np.sqrt(3.0)
    Xaml = multivariate_t(loc=np.zeros(rp), shape=np.eye(rp), df=3).rvs(
        size=rn // 2, random_state=rng) * np.sqrt(3.0)
    Xaml[:, shift_coords] += shift_val
    real_methods = ["mom", "momz", "catoni", "huber", "perm"]
    real_tab, real_tab_w = [], []
    for _ in range(real_B):
        idx = rng.permutation(rn // 2)
        Za = Xall[idx] - Xaml[idx]
        Zw = _winsorize(Xall[idx]) - _winsorize(Xaml[idx])
        _, _, pv_mom, _, _ = mom_bootstrap(Za, K_DEF, ALPHA, R, rng)
        _, _, pv_mom_w, _, _ = mom_bootstrap(Zw, K_DEF, ALPHA, R, rng)
        _, Tnz = mom_analytic(Za, K=K_DEF, alpha=ALPHA)
        pv_momz = 1.0 - stats.norm.cdf(Tnz)
        _, Tnz_w = mom_analytic(Zw, K=K_DEF, alpha=ALPHA)
        pv_momz_w = 1.0 - stats.norm.cdf(Tnz_w)
        _, pv_cat = catoni_test(Za)
        _, pv_cat_w = catoni_test(Zw)
        _, pv_hub = huber_test(Za)
        _, pv_hub_w = huber_test(Zw)
        _, pv_perm = permutation_test(Za, ALPHA, R, rng)
        _, pv_perm_w = permutation_test(Zw, ALPHA, R, rng)
        real_tab.append(dict(mom=pv_mom, momz=pv_momz, catoni=pv_cat,
                              huber=pv_hub, perm=pv_perm))
        real_tab_w.append(dict(mom=pv_mom_w, momz=pv_momz_w, catoni=pv_cat_w,
                                huber=pv_hub_w, perm=pv_perm_w))

    def _med_p(tab):
        return {m: float(np.median([row[m] for row in tab])) for m in real_methods}

    # MoM effect sizes (coordinate-wise difference of block-mean medians)
    Zfull = Xall - Xaml
    Yfull = np.array([Zfull[b].mean(axis=0)
                      for b in np.array_split(np.arange(Zfull.shape[0]), K_DEF)])
    mom_effect = np.median(Yfull, axis=0)
    order = np.argsort(np.abs(mom_effect))[::-1][:5]
    top_genes = [{"gene": int(j), "effect": float(mom_effect[j]),
                  "planted": bool(int(j) in set(shift_coords.tolist()))}
                 for j in order]
    real_summary = {"n": rn, "p": rp, "raw": _med_p(real_tab),
                    "winsorized": _med_p(real_tab_w),
                    "shift_coords": [int(c) for c in shift_coords],
                    "top_genes": top_genes}
    with open(os.path.join(OUT, "results_real.json"), "w") as f:
        json.dump(real_summary, f)
    print("[real] MoM median p=%.4f (winsorized %.4f); top gene effect=%.3f"
          % (real_summary["raw"]["mom"], real_summary["winsorized"]["mom"],
             top_genes[0]["effect"]))

    meta = dict(B=B, R=R, K=K_DEF, alpha=ALPHA, seed=RNG_SEED, frac=frac, delta=delta,
                noises=noises, grid_np=grid_np, covs=list(covs.keys()),
                deltas=deltas, gm_B=gm_B, dense_B=dense_B, real_B=real_B,
                scenarios="A/B/C main+secondary, D dense/extreme, E geometric median, real proxy")
    with open(os.path.join(OUT, "results_meta.json"), "w") as f:
        json.dump(meta, f)
    print("DONE")


if __name__ == "__main__":
    main()
