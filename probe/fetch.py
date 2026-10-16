"""Temporary: fetch SEC company facts for a few companies, keep only the concepts the earnings-quality section reads."""
import gzip, json, os, re, time, urllib.request
CIKS = [104169, 909832, 2488, 1018724, 21344, 1467373, 320193, 1318605, 37996, 1467858, 315189, 19617, 72971, 927628, 50863, 1326801, 47217, 858877, 106640,
        1657573, 789019, 12927, 18230, 1571996, 1375365, 1045810, 1652044, 66740, 773840, 1800]
KEEP = re.compile(r"^(Assets|NetIncomeLoss|ProfitLoss|NetCashProvidedByUsedInOperatingActivities.*|Revenues|"
                  r"RevenueFromContractWithCustomer.*|CostOf.*|OperatingIncomeLoss|IncomeTaxExpenseBenefit|"
                  r"IncomeLossFromContinuingOperationsBefore.*|IncreaseDecrease.*|Depreciation.*|Amortization.*|"
                  r"ShareBasedCompensation|AllocatedShareBasedCompensationExpense|Deferred.*Tax.*|.*Impairment.*|"
                  r"GainLoss.*|AccountsReceivable.*|Receivables.*|Inventory.*|AccountsPayable.*|"
                  r"LongTermDebt.*|DebtCurrent|ShortTermBorrowings|CommercialPaper|.*LeaseLiability.*|"
                  r"CashAndCashEquivalents.*|Cash|ShortTermInvestments|MarketableSecurities.*|AvailableForSaleSecurities.*Current|"
                  r"WeightedAverageNumber.*|CommonStockSharesOutstanding|MinorityInterest|PreferredStockValue|"
                  r"PaymentsToAcquirePropertyPlantAndEquipment|OtherNoncash.*|.*Warranty.*|ProvisionForDoubtfulAccounts|"
                  r"StockholdersEquity|Liabilities|LiabilitiesCurrent|AssetsCurrent)$")
os.makedirs("probe/facts2", exist_ok=True)
for cik in CIKS:
    req = urllib.request.Request(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
                                 headers={"User-Agent": "Filing Flows probe huruizhe625@gmail.com", "Accept-Encoding": "gzip"})
    try:
        raw = urllib.request.urlopen(req, timeout=60).read()
        d = json.loads(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)
    except Exception as e:
        print(cik, "failed", e); continue
    out = {"cik": d.get("cik"), "entityName": d.get("entityName"), "facts": {}}
    for tax in ("us-gaap",):
        out["facts"][tax] = {k: v for k, v in d.get("facts", {}).get(tax, {}).items() if KEEP.match(k)}
    out["facts"]["dei"] = {k: v for k, v in d.get("facts", {}).get("dei", {}).items() if k == "EntityCommonStockSharesOutstanding"}
    json.dump(out, gzip.open(f"probe/facts2/{cik}.json.gz", "wt"))
    print(cik, d.get("entityName"), len(out["facts"]["us-gaap"]))
    time.sleep(0.3)
