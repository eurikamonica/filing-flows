'use strict';
const assert = require('node:assert/strict');
global.document = {
  currentScript: {src: 'https://filing-flows.com/flo-earnings-alerts.js'},
  readyState: 'loading',
  addEventListener() {}
};
global.location = {href: 'https://filing-flows.com/', origin: 'https://filing-flows.com/'};
require('./flo-earnings-alerts.js');
const {verifiedRows, decide} = global.FFEarningsAlerts;
const now = Date.parse('2026-10-25T23:00:00Z');
const row = {id:'ir:META:2026-10-21', ticker:'META', date:'2026-10-21',
  verified_at:'2026-10-25T21:00:00Z',
  ir_url:'https://investor.atmeta.com/investor/events/verified-transcript',
  kind:'official_ir_transcript', transcript_status:'verified_official_link'};
const candidate = {...row, id:'ir_candidate:META:123', kind:'official_ir_candidate',
  transcript_status:'discovered_not_verified'};
const sec = {...row, id:'sec:123',kind:'sec_earnings_evidence',transcript_status:'not_verified'};
assert.deepEqual(verifiedRows({rows:[candidate,sec,row]}),[row]);
assert.deepEqual(decide([row],null,now),[],'first visit must create a baseline');
assert.deepEqual(decide([row],[row.id],now),[],'no replay for same ID');
assert.deepEqual(decide([row],[],now),[row],'new validated recent call triggers');
assert.deepEqual(decide([{...row,verified_at:'2026-09-01T00:00:00Z'}],[],now),[],
  'backfilled old verification does not send fresh alert');
console.log('Flo earnings-call alert decision tests: passed');
