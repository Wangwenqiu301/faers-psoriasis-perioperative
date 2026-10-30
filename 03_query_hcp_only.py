import requests
import time
import pandas as pd

# ============================================================
# FAERS v6: HCP-only 敏感性分析 (仅医务人员报告)
# 在 v4 对称口径基础上追加 primarysource.qualification ∈ {1,2,3}
#   1=医生, 2=药师, 3=其他医务人员 (排除 4=律师, 5=消费者, 空)
# 整个总体 (P, N0, 各药单药总数, 以及a/b/c/d) 都在 HCP 限定下重算,
# 保证四格同一总体, 与 v4 可直接对比。
# 共84条查询。
# ============================================================

API_KEY = "在此粘贴你的openFDA密钥"   # 请自己粘贴, 不要发到聊天里
BASE = "https://api.fda.gov/drug/event.json"
TIMEOUT = 60

DATE_CLAUSE = "receivedate:[20040101+TO+20260701]"
ROLE_CLAUSE = 'patient.drug.drugcharacterization:"1"'
INDIC_CLAUSE = '(patient.drug.drugindication:"Psoriasis"+OR+patient.drug.drugindication:"Psoriatic+arthropathy")'
HCP_CLAUSE = ('(primarysource.qualification:"1"'
              '+OR+primarysource.qualification:"2"'
              '+OR+primarysource.qualification:"3")')
BASE_FILTER = f"{INDIC_CLAUSE}+AND+{ROLE_CLAUSE}+AND+{DATE_CLAUSE}+AND+{HCP_CLAUSE}"

DRUGS = {
    "阿达木单抗": ["ADALIMUMAB", "HUMIRA"],
    "司库奇尤单抗": ["SECUKINUMAB", "COSENTYX"],
    "依奇珠单抗": ["IXEKIZUMAB", "TALTZ"],
    "乌司奴单抗": ["USTEKINUMAB", "STELARA"],
    "古塞奇尤单抗": ["GUSELKUMAB", "TREMFYA"],
}
TERMS = [
    "Impaired healing", "Wound infection", "Postoperative wound infection",
    "Deep vein thrombosis postoperative", "Surgery", "Wound dehiscence",
    "Post procedural complication", "Device related infection",
    "Soft tissue infection", "Skin infection", "Spinal fusion surgery",
    "Post procedural infection",
]
ALL_ALIASES = [a for v in DRUGS.values() for a in v]


def or_clause(names):
    return "(" + "+OR+".join(f'patient.drug.medicinalproduct:"{n}"' for n in names) + ")"


def pt_clause(term):
    return 'patient.reaction.reactionmeddrapt:"%s"' % term.replace(" ", "+")


def get_total(search, retries=4):
    url = f"{BASE}?search={search}&limit=1&api_key={API_KEY}"
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.json()["meta"]["results"]["total"]
            if r.status_code == 404:
                return 0
            wait = 2 ** attempt
            print(f"      HTTP {r.status_code}, 第{attempt+1}次重试, 等待{wait}秒...")
            time.sleep(wait)
        except Exception as e:
            wait = 2 ** attempt
            print(f"      异常: {e}, 第{attempt+1}次重试, 等待{wait}秒...")
            time.sleep(wait)
    print("      彻底失败, 记为None:", search[:120])
    return None


# ---------- 1. 总体与"无目标药"部分 (HCP限定) ----------
print("=== 1. HCP限定: 总体 P 与 N0 ===")
universe = []
P_total = get_total(BASE_FILTER)
print(f"P_HCP = {P_total}")
universe.append({"项目": "P_total", "术语": "", "数量": P_total})
time.sleep(0.5)

not_all = "+AND+NOT+" + or_clause(ALL_ALIASES)
N0 = get_total(BASE_FILTER + not_all)
print(f"N0_HCP = {N0}")
universe.append({"项目": "N0_total", "术语": "", "数量": N0})
time.sleep(0.5)

for t in TERMS:
    v = get_total(BASE_FILTER + not_all + "+AND+" + pt_clause(t))
    print(f"N0 × {t}: {v}")
    universe.append({"项目": "N0_term", "术语": t, "数量": v})
    time.sleep(0.5)

# ---------- 2. 各药 (HCP限定) ----------
print("\n=== 2. HCP限定: 各药总数 / 单药总数 / 单药×术语 ===")
rows = []
for drug, names in DRUGS.items():
    others = [a for d, v in DRUGS.items() if d != drug for a in v]
    drug_filter = BASE_FILTER + "+AND+" + or_clause(names)
    single_filter = drug_filter + "+AND+NOT+" + or_clause(others)

    n_total = get_total(drug_filter)
    time.sleep(0.5)
    n_single = get_total(single_filter)
    print(f"\n{drug}: 总报告 {n_total} | 单药报告 {n_single}")
    time.sleep(0.5)

    for t in TERMS:
        a_single = get_total(single_filter + "+AND+" + pt_clause(t))
        print(f"  {drug} × {t}: 单药a = {a_single}")
        rows.append({"药物": drug, "术语": t,
                     "n_total_drug": n_total, "n_single_drug": n_single,
                     "a_single": a_single})
        time.sleep(0.5)

df = pd.DataFrame(rows)
uni = pd.DataFrame(universe)
df.to_csv("faers_v6_hcp_single_biologic.csv", index=False, encoding="utf-8-sig")
uni.to_csv("faers_v6_hcp_universe.csv", index=False, encoding="utf-8-sig")

# ---------- 3. 自检 ----------
sum_single = df.drop_duplicates("药物")["n_single_drug"].sum()
print("\n=== 自检摘要 (HCP限定) ===")
print(f"P_HCP = {P_total}; N0 + 各药单药总数 = {N0} + {sum_single} = {N0 + sum_single}")
print(f"被剔除的多药报告数 = {P_total - (N0 + sum_single)}")
print("各药单药占比:")
print((df.drop_duplicates('药物').assign(
    单药占比=lambda x: (100 * x.n_single_drug / x.n_total_drug).round(1)
)[["药物", "n_total_drug", "n_single_drug", "单药占比"]]).to_string(index=False))
print("\n已生成 faers_v6_hcp_single_biologic.csv 和 faers_v6_hcp_universe.csv, 请下载发给Claude")
