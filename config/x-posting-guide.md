# X posting guide for @FilingFlows

For any AI that writes, picks, schedules or reviews posts for the site's X account, @FilingFlows: the models in
pipeline/tweet.py and pipeline/engage.py, the local fallback model, and any outside assistant or agent. The short,
per-post rules are in config/tweet-guide.md (earnings posts) and config/engage-guide.md (discussion posts); this file is
the why behind them and the rules for planning.

Last checked: 2026-11-04, against X's published ranking code (github.com/xai-org/x-algorithm, synced daily) and X's
own policies. The code's numbers change often: read them as directions, never hard-code them.

## 1. The account

- @FilingFlows: about 340 followers, X Premium, joined October 2026. Every post comes from SEC filings: earnings
  Sankeys, 13F, insider (Form 4), officials' trades, 8-K events.
- In its first month it published about 1,600 posts (threads counted part by part); most got 3–20 views. Volume did
  not buy reach. Each post now has to earn its place.
- Posts reach X through Buffer (free plan: 1,000 API requests per 30 days) or the X API (pay per post: about $0.015,
  $0.20 with a link). Both limits are reasons to post less, not more.

## 2. What X rewards and what it punishes

How the For You feed ranks a post (from the code; the weights multiply the model's predicted chance of each action,
they are not counts):

- Most valuable: a share by copied link (weight 20), a reply, a quote or a share by DM (5 each), a follow (4), a
  share (2), a repost (1). A like is worth 0.66; a click, dwell or photo expand almost nothing on its own.
- Heavily negative: report (−234), mute (−59), "not interested" (−52), block (−31). One annoyed reader cancels many
  likes. Repetitive, templated, bot-like posting is exactly what makes people mute.
- **New-author window.** An original post (not a reply, not a repost) from an account under 50,000 followers, less
  than 2 hours old and with fewer than 200 home impressions can be lifted into slot 15–16 of someone's feed, at most
  one such post per feed load. The pick favours posts whose early viewers liked them (likes ÷ views). This is the
  account's main road to strangers: post when the news is fresh, and make the first 200 views count.
- **Author repeat discount.** Within one feed load, a second post from the same author is scored ×0.625, a third
  ×0.44, down to ×0.25. Posts in quick succession compete with each other.
- **Strangers do not see your replies** in their For You feeds (replies and reposts from accounts the viewer does
  not follow are filtered out). A reply is seen inside that conversation only. Quote posts count as original posts.
- Posts older than 48 hours are not ranked at all. Out-of-network posts are discounted (×0.75).
- No hashtag bonus and no link penalty exist in the published code. X's own staff: "Please stop using hashtags"
  (Musk, Dec 2024); "you do not need to put the links in replies anymore" (Bier, July 2026). Link posts still get less
  engagement on average (Buffer, NiemanLab), so a link is a choice, not a free extra.
- Premium: no Premium multiplier in the For You scorers. Premium accounts do get more reach on average (Buffer's
  data, a correlation), and verification is one of the inputs that rank the replies under a post.

## 3. Rules for every post

1. **One point, first.** Start with the cashtag and the one thing the filing says, as a sentence a reader can agree
   or argue with. Never open with a list of figures. pipeline/xcard.py picks a point by fixed rules; use it or a
   sharper one the filing supports.
2. **Every number from the data.** Only figures given in the inputs (the chart data, the filing). No estimates, no
   new ratios beyond "about N¢ of every revenue dollar". Units on every number. Quarter labels as given ("Q3 FY26").
3. **No advice.** Never buy / sell / bullish / bearish / undervalued / price targets of our own. A view about the
   quarter is welcome; a view about the stock is not.
4. **Plain words.** No hype words, no exclamation marks, no ALL-CAPS words. At most one emoji (👇 pointing at the
   card). "BREAKING:" only for a material 8-K filed today (a deal, a CEO change, a restatement, a bankruptcy) — never
   on routine earnings.
5. **One or two cashtags; zero or one hashtag.** Cashtags already open X's price card and topic feed. Many cashtags or
   hashtags in one post look like spam (X's platform-manipulation policy names "excessive, unrelated hashtags").
   Exception: a list post of the day's filers, which names its companies.
6. **The picture is the X card** (pipeline/xcard.py): the point in big type, two key numbers, a simplified Sankey,
   one credit line. The site's full chart is for the site. One picture per post: two or more are shown as small tiles.
7. **Short.** 140–220 characters is the target, 270 the limit.
8. **Credit and status.** The card names the filing and its date. Say "(preliminary)" for figures from an 8-K
   earnings release.
9. **No engagement bait.** No "repost if you agree", "like for part 2", "follow for more". X detects it. A genuine
   question with two or three concrete options is fine; at most one in four posts.
10. **Never the same post twice.** No near-identical posts across companies on the same day: vary the point, not just
    the ticker. X's automation rules forbid duplicative or substantially similar posts.

## 4. Openings that work (fill only with real figures)

Each maps to a pattern pipeline/xcard.py can detect (in brackets) or to fields in the inputs.

- `$TICK: sold more but kept less — revenue +5%, operating profit −18%.` [squeeze]
- `$TICK: operating profit grew faster than sales, +77% vs +65%.` [leverage]
- `$TICK: about 31¢ of every revenue dollar is operating profit, up from 27¢ a year ago.` [cents]
- `$TICK: revenue growth sped up to +65% from +55% the quarter before.` [accel] / `slowed to … from …` [decel]
- `$TICK: Communications Solutions delivered 81% of the $4.0B revenue gain.` [segment]
- `$TICK: cash came in ahead of profit — operating cash flow $6.6B, 129% of net earnings.` [cash]
- `$TICK: only 45% of net earnings came in as operating cash flow.` [cash]
- `$TICK: the net loss narrowed to $40M from $95M a year ago.` / `swung to a loss` [loss]
- `$TICK: revenue fell 12% from a year ago.` [decline]
- `Every $1 of $TICK revenue → 48¢ gross profit → 31¢ operating profit → 27¢ net earnings.` (from the chart's shares)
- `$TICK vs $PEER, same quarter: 31% vs 22% operating margin.` (two companies' figures)
- `$TICK spent more on buybacks ($X) than it earned ($Y).` (cash-flow figures, when given)
- `{Fund} added N $TICK shares (≈$V), now its #k holding. As of {quarter end}, filed {date}.` (13F)
- `{Title} at $TICK bought $V of stock on {date} at ${price} (Form 4).` (insider; say "sold" for a sale and imply
  nothing)
- `BREAKING: $TICK 8-K filed today — {the event in plain words}.` (material 8-K only)

## 5. Formats

- **Default: one original post + the X card.** It is eligible for the new-author window; nothing else is.
- **Quote post** of a big account's earnings headline, adding the one point our chart shows: original post, so it
  can reach strangers. Written and sent by a person (see section 7).
- **Replies under big posts** (a person, by hand): a short point plus the card, under accounts posting about the same
  company. They are seen in that conversation only; they bring views, rarely follows. A few good ones a day.
- **Threads:** rarely. The opener carries the point; the replies add the breakdown and the source. Followers seldom
  come from threads.
- **Weekly recap** (Saturday): the week's biggest movers in margin or growth, one line each. Evergreen posts like this
  are what large accounts repost.

## 6. Timing and volume

- **Fast or not at all.** Attention to a company peaks right after its release: after the close for after-close
  reporters, before the open for pre-market ones. The new-author window lasts 2 hours. Post the earnings release
  (8-K, "preliminary") within the hour, from the earnings fast lane. Do not post the same quarter again when the
  10-Q arrives a week later: by then it is old news.
- **Largest first.** S&P 500 and Nasdaq-100 companies, then the day's biggest surprises. Skip small companies unless
  the point is remarkable.
- **5–10 posts a day at most**, at least 45 minutes apart, weekdays. Fewer, better posts: one strong post beats ten
  ordinary ones (in one creator's 1,789-post log, 2 posts brought 28% of all follows).
- **One subject.** SEC filings, every day. X's former head of product: post daily on one subject, one surprising
  insight each time, under five sentences.

## 7. Never automate (X automation rules)

- Replies, mentions or quote posts aimed at other accounts. Automated replies need the other person to ask for them;
  since Feb 2026 API replies only work when the original author mentions or quotes us. Replies and quotes are a
  person's job.
- Likes, follows, reposts.
- Posts about X's trending topics or hashtags.
- Duplicate or substantially similar posts.
- The account should show X's "automated" label, linked to the person who runs it (X's rules require it; it is not
  known to change reach).

## 8. Measure, then keep or drop

For each post, after 2 hours and after 48: impressions, likes ÷ impressions (the new-author pick uses it; a
baseline is about 1.5%), replies, bookmarks, copy-link and DM shares, profile visits, follows. Each week, compare the
point types (section 4): keep the ones above the account's median, drop the ones below after about ten posts each.
Check mutes and "not interested" through follower losses on heavy posting days. X's "Under the Hood" export shows
whether visibility labels were put on the account.

## 9. Before posting: checklist

- [ ] Opens with the cashtag and one point, not a list of figures
- [ ] Every number appears in the inputs, with its unit; "(preliminary)" for an 8-K
- [ ] No advice words, no hype, at most one emoji, "BREAKING" only for a material 8-K
- [ ] One or two cashtags, zero or one hashtag
- [ ] The X card attached, one picture
- [ ] Under 220 characters if possible, 270 at most
- [ ] Not a near-copy of a post made in the last week
- [ ] Filed within the last few hours (earnings) or today (8-K events); otherwise skip it
- [ ] At least 45 minutes since our last post

## 10. Evidence

Solid (code and X's written policy):
- Ranking weights, new-author window, author repeat discount, reply filter, 48-hour cutoff:
  https://github.com/xai-org/x-algorithm (home-mixer/params/param.rs, home-mixer/scorers/author_cold_start.rs,
  xai-value-model/scoring.rs, home-mixer/filters/oon_retweet_reply_filter.rs)
- Automation rules: https://help.x.com/en/rules-and-policies/x-automation
- Platform manipulation and spam: https://help.x.com/en/rules-and-policies/platform-manipulation
- Automated account labels: https://help.x.com/en/using-x/automated-account-labels

Statements by X staff:
- Links (Bier, Musk, July 2026): https://ppc.land/x-drops-year-old-link-penalty-musk-tells-zuckerberg-on-platform/
- Hashtags (Musk, Dec 2024): https://usa.inquirer.net/162874/elon-musk-says-hashtags-look-ugly-no-need-to-use-them-on-x
- One subject, daily, one insight (Bier, Sept 2025): https://survivores.com/nikita-bier-shares-simple-way-to-get-rich-on-x/
- API replies limited (Feb 2026): https://roboin.io/article/en/2026/02/24/x-limits-api-based-automated-replies-to-combat-engagement-farming/

Moderate (large but correlational data):
- Premium reach and formats (Buffer): https://buffer.com/resources/x-premium-review/ ·
  https://buffer.com/resources/links-on-x/
- Links and engagement (NiemanLab, Apr 2026): https://www.niemanlab.org/2026/04/do-links-hurt-news-publishers-on-twitter-our-analysis-suggests-yes/
- Attention around earnings releases: https://arxiv.org/abs/1611.02090

Anecdotal (self-reported growth stories):
- Replies bring views, not follows; a few posts bring most follows:
  https://therender.beehiiv.com/p/what-1-789-posts-taught-me-about-what-actually-converts ·
  https://www.indiehackers.com/post/how-i-got-560k-impressions-on-x-in-10-days-with-zero-followers-and-zero-ad-spend-33c1e4d720
- A large account's repost as the turning point: https://www.acquired.fm/acq2-episodes/10-k-diver-building-a-top-fintwit-account-and-teaching-finance-principles-to-everyone-pseudonymously
- Sankey fatigue (readers block accounts that post only Sankeys; they ask for the why, such as segment margins):
  a Reddit discussion of an Apple FY25 Sankey

No data found for: hashtags helping or hurting in 2025–26, the best number of posts a day, whether the automated
label changes reach.
