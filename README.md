# Local fallback model

Base: `Qwen/Qwen3-0.6B` + LoRA (`adapter/`), trained by `.github/workflows/train-local-model.yml` on posts built from the site's data (`pipeline/corpus.py`); used by the posting workflows only after every API model failed (`pipeline/local_model.py`).

- Production adapter: **99%** of held-out posts publishable (promoted 2026-11-12T20:48 UTC)
- Last run 2026-11-14T23:05 UTC: 269 examples, loss 0.024 → 0.0122, work adapter 99% vs production 100%
- Corpus: 30000 examples all_agree 21, base_rate_growth 198, buyback 130, ceo_pay 64, clone13f 147, committee_trade 27, crowded 80, dilution 152, disclosure_week 41, distress_watch 78, drawdown 267, earn_dist 44, earn_moves 10, earn_nongaap 64, earn_pead 52, earn_preview 279, earn_readthrough 88, earn_scorecard 18, earn_squeeze 56, earn_three_way 80, earn_vrp 72, event8k 5296, fair_value_range 184, form144 1530, gov_trades 76, highs52 64, holdings_race 50, insider 5812, insider_context 222, liquidity 16, lockups 16, lows52 52, manager_sectors 123, market_map 22, maturity_wall 16, mc_odds 47, merger_arb 70, money_flow 18, near_lows 86, news 1286, official 160, pe_band 144, polymarket 52, post 1838, post_holders 591, pt_upside 465, pvgo_growth 233, qtd_flows 10, quality_altman 102, quality_beneish 64, quality_cheap 82, quality_factors 16, quality_leverage 84, quality_piotroski 106, quality_sbc 88, quality_yield 104, records 28, red_flag 148, reddit_hot 174, reddit_list 246, reddit_question 258, sensitivity_driver 118, setup 1143, short 2700, smart_buys 39, smart_record 6, stage_river 104, stake 3240, street_base_rate 136, valuation_gauge 27, versus 452, wacc_gap 16, who_traded 72
- Held-out: companies whose CIK hash ends in a fixed tenth are never trained on.

Every run: `reports.jsonl`.
