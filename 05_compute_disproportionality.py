"""
05_compute_disproportionality.py

Compute symmetric disproportionality statistics (ROR, PRR, IC/IC025) from the
single-biologic analytic universe produced by scripts 01 and 03.

Inputs  (data/universe/):
    faers_v4_universe.csv            P_total, N0_total, N0_term counts (main analysis)
    faers_v4_single_biologic.csv     per drug-PT single-biologic counts (main analysis)
    faers_v6_hcp_universe.csv        same, healthcare-professional-only sensitivity analysis
    faers_v6_hcp_single_biologic.csv

Outputs (data/results/):
    RESULT_table2_v4_main.csv        full 60-combination main results
    faers_v6_hcp_results.csv         full 60-combination HCP-only results

Method (same population for all four 2x2 cells):
    U' = N0 + sum_i n_single(i)                     (analytic universe)
    a  = single-biologic reports for drug i with PT t
    b  = n_single(i) - a
    c  = [N0_term(t) + sum_j a_single(j,t)] - a     (PT count in U' minus a)
    d  = (U' - n_single(i)) - c
    ROR, PRR: 0.5 continuity correction, 95% CI from log-SE
    IC  = log2((a+0.5)/(E+0.5)), E = (a+b)(a+c)/U'
    IC025 = IC - 3.3*(a+0.5)^-0.5 - 2*(a+0.5)^-1.5   (Noren 2006 approximation)
    Signal = ROR & PRR 95% CI lower bound > 1  AND  a >= 3  AND  IC025 > 0

Software: Python 3.13, pandas, numpy. No network access required.
"""
import os
from math import log, sqrt, exp
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
UNI = os.path.join(HERE, "..", "data", "universe")
OUT = os.path.join(HERE, "..", "data", "results")

CN = {"阿达木单抗": "ADA", "司库奇尤单抗": "SEC", "依奇珠单抗": "IXE",
      "乌司奴单抗": "UST", "古塞奇尤单抗": "GUS"}
MECH = {"ADA": "TNF-α inhibitor", "SEC": "IL-17A inhibitor", "IXE": "IL-17A inhibitor",
        "UST": "IL-12/23 inhibitor", "GUS": "IL-23p19 inhibitor"}


def compute(universe_csv, single_csv):
    uni = pd.read_csv(universe_csv)
    df = pd.read_csv(single_csv)
    P = int(uni.loc[uni["项目"] == "P_total", "数量"].iloc[0])
    N0 = int(uni.loc[uni["项目"] == "N0_total", "数量"].iloc[0])
    n0t = uni.loc[uni["项目"] == "N0_term"].set_index("术语")["数量"].to_dict()
    ns = df.drop_duplicates("药物").set_index("药物")
    U = N0 + int(ns["n_single_drug"].sum())
    asum = df.groupby("术语")["a_single"].sum().to_dict()
    rows = []
    for _, r in df.iterrows():
        a = int(r["a_single"]); n = int(r["n_single_drug"]); t = r["术语"]
        PT = n0t[t] + asum[t]
        b = n - a
        c = PT - a
        d = (U - n) - c
        assert min(b, c, d) >= 0, (r["药物"], t, a, b, c, d)
        A, B, C, D = (a + 0.5, b + 0.5, c + 0.5, d + 0.5)
        ror = A * D / (B * C)
        se = sqrt(1/A + 1/B + 1/C + 1/D)
        lo, hi = exp(log(ror) - 1.96*se), exp(log(ror) + 1.96*se)
        prr = (A / (A + B)) / (C / (C + D))
        sep = sqrt(1/A - 1/(A+B) + 1/C - 1/(C+D))
        plo, phi = exp(log(prr) - 1.96*sep), exp(log(prr) + 1.96*sep)
        E = (a + b) * (a + c) / U
        ic = log((a + 0.5) / (E + 0.5), 2)
        ic025 = ic - 3.3 * (a + 0.5) ** -0.5 - 2 * (a + 0.5) ** -1.5
        sig = (lo > 1) and (plo > 1) and (a >= 3) and (ic025 > 0)
        drug = CN[r["药物"]]
        rows.append(dict(Drug=drug, Mechanism=MECH[drug], PT=t, a=a, b=b, c=c, d=d,
                         ROR=round(ror, 2), ROR_low=round(lo, 2), ROR_high=round(hi, 2),
                         PRR=round(prr, 2), PRR_low=round(plo, 2), PRR_high=round(phi, 2),
                         IC=round(ic, 2), IC025=round(ic025, 2), Signal=sig))
    out = pd.DataFrame(rows)
    meta = dict(P=P, N0=N0, U=U, excluded_multi=P - U)
    return out, meta


if __name__ == "__main__":
    main, m_main = compute(os.path.join(UNI, "faers_v4_universe.csv"),
                           os.path.join(UNI, "faers_v4_single_biologic.csv"))
    hcp, m_hcp = compute(os.path.join(UNI, "faers_v6_hcp_universe.csv"),
                         os.path.join(UNI, "faers_v6_hcp_single_biologic.csv"))
    main.to_csv(os.path.join(OUT, "RESULT_table2_v4_main.csv"), index=False, encoding="utf-8-sig")
    hcp.to_csv(os.path.join(OUT, "faers_v6_hcp_results.csv"), index=False, encoding="utf-8-sig")
    print("Main analysis:", m_main, "| signals:", int(main.Signal.sum()))
    print("HCP-only     :", m_hcp, "| signals:", int(hcp.Signal.sum()))
