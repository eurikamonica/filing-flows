# Local fallback model

Base: `Qwen/Qwen3-0.6B` + LoRA (`adapter/`), trained by `.github/workflows/train-local-model.yml` on posts built from the site's data (`pipeline/corpus.py`); used by the posting workflows only after every API model failed (`pipeline/local_model.py`).

- Production adapter: **100%** of held-out posts publishable (promoted 2026-11-07T13:52 UTC)
- Last run 2026-11-07T13:52 UTC: 377 examples, loss 0.0144 → 0.0413, work adapter 100% vs production 99% → promoted
- Corpus: 30000 examples all_agree 17, base_rate_growth 148, buyback 108, ceo_pay 48, clone13f 132, committee_trade 24, crowded 66, dilution 132, disclosure_week 41, distress_watch 56, drawdown 240, earn_breadth 20, earn_dist 44, earn_moves 6, earn_nongaap 36, earn_pead 22, earn_preview 168, earn_readthrough 44, earn_scorecard 14, earn_squeeze 36, earn_three_way 104, earn_vrp 48, event8k 5425, fair_value_range 172, form144 1572, gov_trades 48, highs52 48, holdings_race 36, insider 4614, insider_context 166, liquidity 12, lockups 10, lows52 42, manager_sectors 90, market_map 14, maturity_wall 12, mc_odds 31, merger_arb 52, money_flow 14, near_lows 58, news 1320, official 46, pe_band 84, polymarket 120, post 3348, post_holders 2338, preview13f 2, pt_upside 417, pvgo_growth 188, qtd_flows 9, quality_altman 60, quality_beneish 52, quality_cheap 62, quality_factors 12, quality_leverage 62, quality_piotroski 80, quality_sbc 60, quality_yield 66, records 24, red_flag 112, reddit_hot 162, reddit_list 264, reddit_question 222, sensitivity_driver 114, setup 837, short 3170, smart_buys 42, smart_record 2, stage_river 76, stake 2036, street_base_rate 112, valuation_gauge 21, versus 456, wacc_gap 12, who_traded 42
- Held-out: companies whose CIK hash ends in a fixed tenth are never trained on.

Every run: `reports.jsonl`.
