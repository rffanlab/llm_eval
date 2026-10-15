import unittest
from metrics.native_speed import aggregate_turns, summarize_rounds


class NativeSpeedTest(unittest.TestCase):
    def test_token_time_sums_exclude_cached_input(self):
        turns = [dict(timings=dict(prompt_n=100, prompt_ms=1000, cache_n=9000,
                                   predicted_n=200, predicted_ms=2000)),
                 dict(timings=dict(prompt_n=1000, prompt_ms=20000, cache_n=1000,
                                   predicted_n=500, predicted_ms=5000))]
        r = aggregate_turns(turns)
        self.assertAlmostEqual(r['prefill_tokens_s'], 1100/21)
        self.assertNotAlmostEqual(r['prefill_tokens_s'], 75)
        self.assertEqual(r['decode_tokens_s'], 100)
        self.assertEqual(r['cached_tokens'], 10000)

    def test_missing_turn_does_not_look_like_complete_speed(self):
        r = aggregate_turns([dict(timings=dict(prompt_n=100, prompt_ms=1000)), dict(timings=None)])
        self.assertIsNone(r['prefill_tokens_s'])
        self.assertEqual(r['prefill_calls_measured'], 1)

    def test_zero_duration_is_unknown(self):
        r = aggregate_turns([dict(timings=dict(prompt_n=0, prompt_ms=0,
                                              predicted_n=0, predicted_ms=0, cache_n=100))])
        self.assertIsNone(r['prefill_tokens_s'])
        self.assertIsNone(r['decode_tokens_s'])

    def test_median_is_of_complete_work_rounds(self):
        rows = [dict(native_speed=dict(prefill_tokens_s=10, decode_tokens_s=20)),
                dict(native_speed=dict(prefill_tokens_s=30, decode_tokens_s=40))]
        self.assertEqual(summarize_rounds(rows)['prefill_median_tokens_s'], 20)
        rows[1]['native_speed']['prefill_tokens_s'] = None
        self.assertIsNone(summarize_rounds(rows)['prefill_median_tokens_s'])


if __name__ == '__main__':
    unittest.main()
