import requests
import time
import pandas as pd

# ============================================================
# Table 1: 五个生物制剂"单药报告"队列的特征描述
# 口径与 v4/v5 完全一致 (银屑病/PsA + 主要怀疑 + 2004-2026.7 + 排除其余4个目标药)
# 用 openFDA 的 count= 端点一次取回某字段的完整分布, 速度快
# 另有少量 get_total 用于适应症拆分和报告年代分箱
# 预计约 70 条查询, 多为 count 查询, 总耗时约 5-10 分钟
# ============================================================

API_KEY = "在此粘贴你的openFDA密钥"   # 请自己粘贴, 不要发到聊天里
BASE = "https://api.fda.gov/drug/event.json"
TIMEOUT = 60

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

# count 字段: (字段名, 是否加.exact)
COUNT_FIELDS = [
    ("patient.patientsex", False),            # 0=未知 1=男 2=女
    ("primarysource.qualification", False),   # 1医生 2药师 3其他HCP 4律师 5消费者
    ("serious", False),                       # 1严重 2非严重
    ("reporttype", False),                    # 1自发 2其他 3研究 4非研究
    ("primarysourcecountry", True),           # 国家代码, 之后聚合US vs 非US
    ("occurcountry", True),
]
ERA_BINS = [("20040101", "20081231"), ("20090101", "20131231"),
            ("20140101", "20171231"), ("20180101", "20211231"),
            ("20220101", "20260701")]


def or_clause(names):
    return "(" + "+OR+".join(f'patient.drug.medicinalproduct:"{n}"' for n in names) + ")"


def _req(url, retries=4):
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return {"results": []}
            wait = 2 ** attempt
            print(f"      HTTP {r.status_code}, 第{attempt+1}次重试, 等待{wait}秒...")
            time.sleep(wait)
        except Exception as e:
            wait = 2 ** attempt
            print(f"      异常: {e}, 第{attempt+1}次重试, 等待{wait}秒...")
            time.sleep(wait)
    print("      彻底失败:", url[:120])
    return None


def get_total(search):
    data = _req(f"{BASE}?search={search}&limit=1&api_key={API_KEY}")
    if data is None:
        return None
    try:
        return data["meta"]["results"]["total"]
    except (KeyError, TypeError):
        return 0


def get_count(search, field, exact):
    f = field + (".exact" if exact else "")
    data = _req(f"{BASE}?search={search}&count={f}&limit=1000&api_key={API_KEY}")
    if data is None:
        return []
    return [(str(x["term"]), x["count"]) for x in data.get("results", [])]


def single_filter(drug):
    names = DRUGS[drug]
    others = [a for d, v in DRUGS.items() if d != drug for a in v]
    return BASE_FILTER + "+AND+" + or_clause(names) + "+AND+NOT+" + or_clause(others)


rows = []
for drug in DRUGS:
    sf = single_filter(drug)
    print(f"\n=== {drug} ===")
    total = get_total(sf)
    print(f"  单药报告总数: {total}")
    rows.append({"药物": drug, "字段": "total", "类别": "single_biologic_reports", "数量": total})
    time.sleep(0.3)

    # count 分布字段
    for field, exact in COUNT_FIELDS:
        dist = get_count(sf, field, exact)
        for term, cnt in dist:
            rows.append({"药物": drug, "字段": field, "类别": term, "数量": cnt})
        print(f"  {field}: {len(dist)} 个取值")
        time.sleep(0.3)

    # 适应症拆分 (两项可能重叠, 仅供构成参考)
    for ind in ["Psoriasis", "Psoriatic+arthropathy"]:
        v = get_total(sf + "+AND+" + f'patient.drug.drugindication:"{ind}"')
        rows.append({"药物": drug, "字段": "indication", "类别": ind, "数量": v})
        print(f"  适应症 {ind}: {v}")
        time.sleep(0.3)

    # 报告年代分箱
    for s, e in ERA_BINS:
        v = get_total(sf + "+AND+" + f"receivedate:[{s}+TO+{e}]")
        rows.append({"药物": drug, "字段": "era", "类别": f"{s[:4]}-{e[:4]}", "数量": v})
        time.sleep(0.3)
    print(f"  年代分箱完成")

    # 年龄 (仅限以"岁"为单位记录的报告, 801=年)
    age = get_count(sf + "+AND+" + 'patient.patientonsetageunit:"801"',
                    "patient.patientonsetage", False)
    for term, cnt in age:
        rows.append({"药物": drug, "字段": "age_years", "类别": term, "数量": cnt})
    print(f"  年龄(岁)取值: {len(age)} 个")
    time.sleep(0.3)

df = pd.DataFrame(rows)
df.to_csv("faers_table1_raw.csv", index=False, encoding="utf-8-sig")
print("\n=== 原始分布已保存: faers_table1_raw.csv ===")

# ---------- 现场汇总一个可读版本 ----------
def pick(drug, field):
    d = df[(df.药物 == drug) & (df.字段 == field)]
    return dict(zip(d.类别, d.数量))

summary = []
for drug in DRUGS:
    tot = pick(drug, "total").get("single_biologic_reports", 0) or 0
    sex = pick(drug, "patient.patientsex")
    qual = pick(drug, "primarysource.qualification")
    ser = pick(drug, "serious")
    ctry = pick(drug, "primarysourcecountry")
    us = ctry.get("US", 0); nonus = sum(v for k, v in ctry.items() if k != "US")
    hcp = sum(qual.get(k, 0) for k in ["1", "2", "3"])
    cons = qual.get("5", 0); law = qual.get("4", 0)
    age = pick(drug, "age_years")
    ages = []
    for k, v in age.items():
        try:
            ages += [float(k)] * int(v)
        except ValueError:
            pass
    med_age = (pd.Series(ages).median() if ages else None)
    def pct(x): return f"{x} ({round(100*x/tot,1)}%)" if tot else str(x)
    summary.append({
        "Drug": {"阿达木单抗":"ADA","司库奇尤单抗":"SEC","依奇珠单抗":"IXE","乌司奴单抗":"UST","古塞奇尤单抗":"GUS"}[drug],
        "Single-biologic reports": tot,
        "Female": pct(sex.get("2", 0)), "Male": pct(sex.get("1", 0)),
        "Median age (yr, recorded)": round(med_age, 0) if med_age is not None else "NA",
        "HCP report": pct(hcp), "Consumer": pct(cons), "Lawyer": pct(law),
        "US": pct(us), "Non-US": pct(nonus),
        "Serious": pct(ser.get("1", 0)),
    })
sm = pd.DataFrame(summary)
sm.to_csv("faers_table1_summary.csv", index=False, encoding="utf-8-sig")
print(sm.to_string(index=False))
print("\n已生成 faers_table1_raw.csv 和 faers_table1_summary.csv, 请下载这两个文件发给Claude")
