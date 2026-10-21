"""Loopback security and response-contract tests. Created by ChatGPT (OpenAI)."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from local8b_service import Companion, validate_answer, validate_request


class FakeModel:
    reply = '{"answer":null,"source_ids":[],"insufficient_evidence":true,"quotations":[]}'

    def generate(self, messages, max_new_tokens):
        text = self.reply if messages[0]['content'].startswith('You are a financial evidence') else self.polish_reply
        return {'text': text, 'seconds': 0.01, 'input_tokens': 10, 'output_tokens': 20, 'output_tokens_per_second': 2000}
    polish_reply = '{"post": "$CRWV $63.40 (+1.9%) on Oct 19, 2.3x its usual daily swing. On the numbers it leans cheap: 62% of our DCF scenarios land above the price. What are you watching?"}'


class Tests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.server = Companion(('127.0.0.1', 0), FakeModel(), 'test-secret', Path(self.directory.name))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.directory.cleanup()

    def request(self, method='GET', path='/health', headers=None, body=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        data = response.read()
        result = (response.status, dict(response.getheaders()), data)
        connection.close()
        return result

    def test_token_and_origin_and_host(self):
        self.assertEqual(self.request()[0], 401)
        auth = {'Authorization': 'Bearer test-secret', 'Origin': 'https://filing-flows.com'}
        self.assertEqual(self.request(headers=auth)[0], 200)
        self.assertEqual(self.request(headers={**auth, 'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.request(headers={**auth, 'Host': 'evil.example'})[0], 403)
        self.assertNotIn(b'test-secret', self.request(headers=auth)[2])

    def test_extra_origin(self):
        server = Companion(('127.0.0.1', 0), FakeModel(), 'k', Path(self.directory.name), origins={'https://x.github.io'})
        try:
            self.assertEqual(server.origins, {'https://x.github.io'})
        finally:
            server.server_close()

    def test_preflight(self):
        response = self.request('OPTIONS', '/ask', {'Origin': 'https://filing-flows.com',
                                'Access-Control-Request-Method': 'POST',
                                'Access-Control-Request-Headers': 'authorization, content-type'})
        self.assertEqual(response[0], 204)
        self.assertEqual(response[1]['Access-Control-Allow-Origin'], 'https://filing-flows.com')
        self.assertEqual(self.request('OPTIONS', '/ask', {'Origin': 'null'})[0], 403)

    def test_input_and_busy(self):
        headers = {'Authorization': 'Bearer test-secret', 'Content-Type': 'application/json'}
        body = json.dumps({'question': 'What reserve?', 'evidence': [{'id': 'S1', 'text': 'Revenue 100'}]})
        self.assertEqual(self.request('POST', '/ask', headers, body)[0], 200)
        self.server.job_lock.acquire()
        try:
            self.assertEqual(self.request('POST', '/ask', headers, body)[0], 429)
        finally:
            self.server.job_lock.release()
        self.assertEqual(self.request('POST', '/ask', headers, '{"question":NaN}')[0], 400)
        self.assertEqual(self.request('POST', '/ask', headers, 'x' * 32769)[0], 400)

    def test_polish_keeps_numbers_cashtags_and_refuses_advice(self):
        from local8b_service import validate_polish, validate_polish_request
        draft = '$CRWV $63.40 (+1.9%) — Oct 19. 2.3× its normal daily swing. On the numbers $CRWV leans cheap: 62% of our DCF scenarios land above $63.40.'
        headers = {'Authorization': 'Bearer test-secret', 'Content-Type': 'application/json'}
        status, _, data = self.request('POST', '/polish', headers, json.dumps({'draft': draft, 'cashtags': ['CRWV'], 'facts': 'Reports Oct 23.'}))
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(data)['post'].startswith('$CRWV $63.40 (+1.9%)'))
        ok = validate_polish(json.dumps({'post': 'A test about $CRWV at $63.40, +1.9%, 62% of scenarios above. Thoughts?'}), draft, '', ['CRWV'], 280)
        self.assertIn('$CRWV', ok)
        for bad, why in [('{"post": "$CRWV at $63.40, up 1.9%, and 71% of scenarios above. Thoughts?"}', 'numbers not in the draft'),
                         ('{"post": "At $63.40 this one leans cheap. Thoughts?"}', 'cashtag missing'),
                         ('{"post": "$CRWV at $63.40 is a buy. Thoughts?"}', 'advice'),
                         ('{"post": "$CRWV at $63.40 looks great!"}', 'exclamation'),
                         ('{"post": "$CRWV at $63.40 and then"}', 'mid-sentence'),
                         ('{"post": "' + 'x' * 300 + ' $CRWV."}', 'too long')]:
            with self.assertRaises(ValueError, msg=why):
                validate_polish(bad, draft, '', ['CRWV'], 280)
        with self.assertRaises(ValueError):
            validate_polish_request({'draft': 'short', 'cashtags': ['CRWV']})
        with self.assertRaises(ValueError):
            validate_polish_request({'draft': draft, 'evidence': []})
        self.assertEqual(self.request('POST', '/polish', headers, json.dumps({'draft': 'too short'}))[0], 400)
        self.server.model.polish_reply = '{"post": "$CRWV is a strong buy at $63.40. Thoughts?"}'
        status, _, data = self.request('POST', '/polish', headers, json.dumps({'draft': draft, 'cashtags': ['CRWV']}))
        self.assertEqual(status, 422)
        self.assertIn('Advice', json.loads(data)['error'])

    def test_literal_quote_cannot_be_fabricated(self):
        evidence = [{'id': 'S1', 'text': 'Revenue was USD 100 million.'}]
        output = {'answer': 'USD 100 million', 'source_ids': ['S1'], 'insufficient_evidence': False,
                  'quotations': [{'source_id': 'S1', 'quote': 'Revenue was USD 100 million.'}]}
        self.assertEqual(validate_answer(json.dumps(output), evidence), output)
        output['quotations'][0]['quote'] = 'Reserve was USD 100 million.'
        with self.assertRaises(ValueError):
            validate_answer(json.dumps(output), evidence)
        with self.assertRaises(ValueError):
            validate_answer('```json\n{}\n```', evidence)
        with self.assertRaises(ValueError):
            validate_request({'question': 'x', 'evidence': evidence * 2})


if __name__ == '__main__':
    unittest.main()
