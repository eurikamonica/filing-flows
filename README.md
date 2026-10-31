# Local fallback model

Base: `Qwen/Qwen3-0.6B` + LoRA (`adapter/`), trained by `.github/workflows/train-local-model.yml` on posts built from the site's data (`pipeline/corpus.py`); used by the posting workflows only after every API model failed (`pipeline/local_model.py`).

- Production adapter: **100%** of held-out posts publishable (promoted 2026-10-31T17:51 UTC)
- Last run 2026-10-31T17:51 UTC: 276 examples, loss 0.0109 → 0.0255, work adapter 100% vs production 99% → promoted
- Corpus: 30000 examples all_agree 33, base_rate_growth 174, buyback 142, ceo_pay 56, clone13f 132, committee_trade 24, crowded 70, dilution 128, disclosure_week 77, distress_watch 68, drawdown 333, earn_breadth 28, earn_dist 62, earn_moves 38, earn_nongaap 42, earn_pead 58, earn_preview 180, earn_readthrough 54, earn_scorecard 16, earn_squeeze 44, earn_three_way 116, earn_vrp 58, event8k 4660, fair_value_range 186, form144 744, gov_trades 58, highs52 62, holdings_race 42, insider 2835, insider_context 207, liquidity 14, lows52 46, manager_sectors 105, market_map 14, maturity_wall 14, mc_odds 41, merger_arb 76, money_flow 14, near_lows 76, news 1401, official 90, pe_band 78, polymarket 234, post 1306, post_holders 3672, preview13f 1, pt_upside 534, pvgo_growth 229, qtd_flows 10, quality_altman 94, quality_beneish 60, quality_cheap 70, quality_factors 14, quality_leverage 78, quality_piotroski 104, quality_sbc 94, quality_yield 86, records 32, red_flag 128, reddit_hot 192, reddit_list 405, reddit_question 249, sensitivity_driver 116, setup 993, short 5774, smart_buys 40, smart_record 9, sp500_candidates 28, stage_river 104, stake 1788, street_base_rate 128, valuation_gauge 24, versus 670, wacc_gap 14, who_traded 24
- Held-out: companies whose CIK hash ends in a fixed tenth are never trained on.

Every run: `reports.jsonl`.
