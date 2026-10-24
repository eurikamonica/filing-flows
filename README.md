# Local fallback model

Base: `Qwen/Qwen3-0.6B` + LoRA (`adapter/`), trained by `.github/workflows/train-local-model.yml` on posts built from the site's data (`pipeline/corpus.py`); used by the posting workflows only after every API model failed (`pipeline/local_model.py`).

- Production adapter: **100%** of held-out posts publishable (promoted 2026-10-23T13:44 UTC)
- Last run 2026-10-24T13:37 UTC: 345 examples, loss 0.0495 → 0.0184, work adapter 89% vs production 100%
- Corpus: 30000 examples all_agree 25, base_rate_growth 68, buyback 90, ceo_pay 42, clone13f 90, committee_trade 15, crowded 50, dilution 74, disclosure_week 50, distress_watch 60, drawdown 186, earn_breadth 18, earn_dist 36, earn_moves 20, earn_nongaap 30, earn_pead 44, earn_preview 126, earn_readthrough 38, earn_scorecard 10, earn_squeeze 30, earn_three_way 72, earn_vrp 48, event8k 3594, fair_value_range 116, form144 4370, gov_trades 42, highs52 44, holdings_race 30, insider_context 113, liquidity 10, lows52 30, manager_sectors 75, market_map 10, maturity_wall 10, mc_odds 32, merger_arb 30, money_flow 10, near_lows 50, news 925, official 5880, pe_band 30, polymarket 200, post 912, post_holders 92, pt_upside 315, pvgo_growth 162, qtd_flows 6, quality_altman 44, quality_beneish 24, quality_cheap 30, quality_factors 6, quality_leverage 34, quality_piotroski 50, quality_sbc 52, quality_yield 44, records 20, red_flag 82, reddit_hot 109, reddit_list 264, reddit_question 165, sensitivity_driver 48, setup 690, short 6374, smart_buys 17, smart_record 10, sp500_candidates 30, stage_river 40, stake 3112, street_base_rate 56, valuation_gauge 15, versus 355, wacc_gap 10, who_traded 9
- Held-out: companies whose CIK hash ends in a fixed tenth are never trained on.

Every run: `reports.jsonl`.
