import requests
import time
import pandas as pd

# ============================================================
# FAERS v5: 按 v4 单药口径"全量"取回报告 (不抽样), 并保存每份报告的完整药物列表
# 口径与 v4 完全一致:
#   总体 = 银屑病/PsA适应症 + 报告级主要怀疑药物 + 2004-01-01~2026-07-01
#   单药 = 报告中任何角色下都不列其余4个目标生物制剂
# 预期取回条数 (应与v4的 a_single 一致):
#   ADA: Impaired healing 704, Wound infection 444, DVT 45
#   SEC: Impaired healing 339, Wound infection 314, DVT 60
#   UST: Impaired healing 36,  Wound infection 130, DVT 1
# 预计 约27页, 每页约20秒, 总耗时约10-20分钟
# ============================================================

API_KEY = "在此粘贴你的openFDA密钥"   # 请自己粘贴, 不要发到聊天里
BASE = "https://api.fda.gov/drug/event.json"
TIMEOUT = 90
PAGE_SIZE = 100

DATE_CLAUSE = "receivedate:[20040101+TO+20260701]"
ROLE_CLAUSE = 'patient.drug.drugcharacterization:"1"'
INDIC_CLAUSE = '(patient.drug.drugindication:"Psoriasis"+OR+patient.drug.drugindication:"Psoriatic+arthropathy")'
BASE_FILTER = f"{INDIC_CLAUSE}+AND+{ROLE_CLAUSE}+AND+{DATE_CLAUSE}"

DRUGS = {
    "阿达木单抗": ["ADALIMUMAB", "HUMIRA"],
    "司库奇尤单抗": ["SECUKINUMAB", "COSENTYX"],
    "依奇珠单抗": ["IXEKIZUMAB", "TALTZ"],
    "乌司奴单抗": ["USTEKINUMAB", "STELARA"],
    "古塞奇尤单抗": ["GUSELKUMAB", "TREMFYA"],
}
ALL_ALIASES = [a for v in DRUGS.values() for a in v]

# (药物, 术语, 预期条数)
COMBOS = [
    ("阿达木单抗", "Impaired healing", 704),
    ("阿达木单抗", "Wound infection", 444),
    ("阿达木单抗", "Deep vein thrombosis postoperative", 45),
    ("司库奇尤单抗", "Impaired healing", 339),
    ("司库奇尤单抗", "Wound infection", 314),
    ("司库奇尤单抗", "Deep vein thrombosis postoperative", 60),
    ("乌司奴单抗", "Impaired healing", 36),
    ("乌司奴单抗", "Wound infection", 130),
    ("乌司奴单抗", "Deep vein thrombosis postoperative", 1),
]


def or_clause(names):
    return "(" + "+OR+".join(f'patient.drug.medicinalproduct:"{n}"' for n in names) + ")"


def pt_clause(term):
    return 'patient.reaction.reactionmeddrapt:"%s"' % term.replace(" ", "+")


def fetch_page(url, retries=5):
    for attempt in range(retries):
        t0 = time.time()
        try:
            r = requests.get(url, timeout=TIMEOUT)
            elapsed = round(time.time() - t0, 1)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return {"results": []}
            wait = 2 ** attempt
            print(f"        HTTP {r.status_code}(耗时{elapsed}秒), 第{attempt+1}次重试, 等待{wait}秒...")
            time.sleep(wait)
        except Exception as e:
            wait = 2 ** attempt
            print(f"        异常: {e}, 第{attempt+1}次重试, 等待{wait}秒...")
            time.sleep(wait)
    print("        彻底失败")
    return None


def fetch_all(search, expected):
    records, skip = [], 0
    while True:
        url = (f"{BASE}?search={search}&sort=receivedate:asc&limit={PAGE_SIZE}"
               f"&skip={skip}&api_key={API_KEY}")
        data = fetch_page(url)
        if data is None:
            print("        该页失败, 已取回部分记录, 继续下一个组合")
            break
        batch = data.get("results", [])
        if not batch:
            break
        records.extend(batch)
        print(f"        已取回 {len(records)} / 预期 {expected}")
        if len(batch) < PAGE_SIZE:
            break
        skip += PAGE_SIZE
        time.sleep(0.5)
    return records


def parse_record(rec, drug_cn, term, names):
    rid = rec.get("safetyreportid", "")
    ps = rec.get("primarysource", {}) or {}
    drugs = rec.get("patient", {}).get("drug", []) or []
    entries, target_rows = [], []
    n_other_target = 0
    for d in drugs:
        nm = (d.get("medicinalproduct") or "").upper()
        role = str(d.get("drugcharacterization", ""))
        entries.append({
            "药物": drug_cn, "术语": term, "safetyreportid": rid,
            "medicinalproduct": nm, "role": role,
            "drugstartdate": d.get("drugstartdate", ""),
            "drugenddate": d.get("drugenddate", ""),
            "drugindication": d.get("drugindication", ""),
            "是否目标药": any(a in nm for a in ALL_ALIASES),
        })
        if any(a in nm for a in names):
            target_rows.append(d)
        elif any(a in nm for a in ALL_ALIASES):
            n_other_target += 1   # 应为0: 若不为0说明单药过滤有漏网(例如拼写变体)
    # 药物级精确绑定: 目标药条目本身角色为主要怀疑
    bound = [d for d in target_rows if str(d.get("drugcharacterization")) == "1"]
    first = bound[0] if bound else (target_rows[0] if target_rows else {})
    report = {
        "药物": drug_cn, "术语": term, "safetyreportid": rid,
        "receivedate": rec.get("receivedate", ""),
        "reporttype": rec.get("reporttype", ""),
        "safetyreportversion": rec.get("safetyreportversion", ""),
        "duplicate": rec.get("duplicate", ""),
        "serious": rec.get("serious", ""),
        "primarysource_qualification": ps.get("qualification", ""),
        "primarysourcecountry": rec.get("primarysourcecountry", ""),
        "n_drug_entries": len(drugs),
        "n_target_entries": len(target_rows),
        "n_other_target_entries": n_other_target,
        "药物级角色精确绑定": len(bound) > 0,
        "drugstartdate": first.get("drugstartdate", ""),
        "drugenddate": first.get("drugenddate", ""),
        "drugindication": first.get("drugindication", ""),
    }
    return report, entries


# ---------- 主流程 ----------
all_reports, all_entries, check = [], [], []
print("=== v5 单药口径全量取回 ===")
for drug_cn, term, expected in COMBOS:
    names = DRUGS[drug_cn]
    others = [a for d, v in DRUGS.items() if d != drug_cn for a in v]
    search = (BASE_FILTER + "+AND+" + or_clause(names) + "+AND+NOT+" + or_clause(others)
              + "+AND+" + pt_clause(term))
    print(f"\n抓取: {drug_cn} × {term} (预期 {expected})")
    recs = fetch_all(search, expected)
    for rec in recs:
        rep, ents = parse_record(rec, drug_cn, term, names)
        all_reports.append(rep)
        all_entries.extend(ents)
    check.append({"药物": drug_cn, "术语": term, "预期": expected, "取回": len(recs)})
    # 增量保存, 防止中途断线丢失
    pd.DataFrame(all_reports).to_csv("faers_v5_single_records.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(all_entries).to_csv("faers_v5_all_drug_entries.csv", index=False, encoding="utf-8-sig")
    time.sleep(0.5)

chk = pd.DataFrame(check)
chk["一致"] = chk["预期"] == chk["取回"]
chk.to_csv("faers_v5_retrieval_check.csv", index=False, encoding="utf-8-sig")

rep_df = pd.DataFrame(all_reports)
print("\n=== 自检 ===")
print(chk.to_string(index=False))
if len(rep_df):
    print("\n单药过滤漏网(应全为0):", int((rep_df.n_other_target_entries > 0).sum()), "份报告含其他目标药条目")
    print("药物级角色精确绑定比例(%):")
    print((100 * rep_df.groupby(["药物", "术语"]).药物级角色精确绑定.mean()).round(1).to_string())
    full = rep_df.drugstartdate.astype(str).str.len() == 8
    print("\n8位完整drugstartdate比例(%):")
    print((100 * full.groupby([rep_df.药物, rep_df.术语]).mean()).round(1).to_string())
print("\n已生成: faers_v5_single_records.csv, faers_v5_all_drug_entries.csv, faers_v5_retrieval_check.csv")
print("请下载这三个文件发给Claude")
