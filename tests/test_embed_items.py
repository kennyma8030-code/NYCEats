"""embed.embed_items, the per-batch worker, without a database. API stubbed."""

import threading
import time
import unittest
from unittest import mock

from fakes import FakeOpenRouter, FakeResponse, ok_body

import embed
import embedding as E


def items(n):
    return [(f"t1_{i}", f"text {i}", E.input_hash(f"text {i}")) for i in range(n)]


def call(its, guard=None, deadline=None, **kw):
    return embed.embed_items(its, E.Budget(1.0), threading.Event(), guard or embed.RejectGuard(),
                             attempts=1, timeout=5, deadline=deadline, **kw)


class Splitting(unittest.TestCase):
    def test_paid_left_half_is_returned_when_right_half_stops_the_run(self):
        # #1
        def handler(p):
            if len(p["input"]) == 4:
                return FakeResponse(400, None, "bad")
            if "text 0" in p["input"]:
                return FakeResponse(200, ok_body(p))
            return FakeResponse(503, None, "down")
        with FakeOpenRouter(handler):
            results, why = call(items(4))
        self.assertIsInstance(why, E.ServiceError)
        self.assertEqual([r[0] for r in results], ["t1_0", "t1_1"])
        self.assertTrue(all(r[2] is not None for r in results))

    def test_bad_input_isolated_after_canary_passes(self):
        def handler(p):
            if any(t == "text 2" for t in p["input"]):
                return FakeResponse(400, None, "bad")
            return FakeResponse(200, ok_body(p))
        with FakeOpenRouter(handler) as api:
            results, why = call(items(4))
        self.assertIsNone(why)
        self.assertEqual([(r[0], r[2] is None) for r in results],
                         [("t1_0", False), ("t1_1", False), ("t1_2", True), ("t1_3", False)])
        self.assertIn(embed.CANARY, api.inputs)

    def test_request_level_400_is_a_service_error(self):
        # #2: the canary is refused with the same 400, so the request is at fault.
        with FakeOpenRouter(lambda p: FakeResponse(400, None, "unsupported: dimensions")) as api:
            guard = embed.RejectGuard()
            results, why = call(items(8), guard)
            self.assertIsInstance(why, E.ServiceError)
            self.assertIn("canary", str(why))
            self.assertEqual(results, [])
            n = len(api.requests)
            # a second batch in the same run gives up at its first leaf, no new canary
            results, why = call(items(2), guard)
        self.assertIsInstance(why, E.ServiceError)
        self.assertEqual(len(api.requests) - n, 2)       # the pair, then one single

    def test_split_depth_is_capped(self):
        with mock.patch.object(embed, "MAX_SPLIT_DEPTH", 1), \
                FakeOpenRouter(lambda p: FakeResponse(400, None, "bad")) as api:
            results, why = call(items(8))
        self.assertIsInstance(why, E.ServiceError)
        self.assertIn("after 1 splits", str(why))
        self.assertEqual(len(api.requests), 2)            # 8, then the first 4

    def test_deadline_stops_a_batch_before_it_starts(self):
        # #4
        with FakeOpenRouter() as api:
            results, why = call(items(3), deadline=time.monotonic() - 1)
        self.assertIsInstance(why, embed.OutOfTime)
        self.assertEqual((results, api.requests), ([], []))

    def test_page_size_follows_the_run(self):
        # #6
        self.assertEqual(embed.page_size(5, 1), 10)
        self.assertEqual(embed.page_size(128, 2), 512)
        self.assertFalse(hasattr(embed, "PAGE"))


class Shapes(unittest.TestCase):
    """#7: malformed responses are a ServiceError, settled, never a crash."""

    def bad(self, mutate):
        def handler(p):
            body = ok_body(p)
            mutate(body)
            return FakeResponse(200, body)
        b = E.Budget(1.0)
        with FakeOpenRouter(handler):
            with self.assertRaises(E.ServiceError) as cm:
                E.embed_batch(["a", "b"], b, sleep=lambda s: None)
        self.assertGreater(b.spent, 0)
        self.assertEqual(b.reserved, 0)
        return str(cm.exception)

    def test_data_not_a_list(self):
        self.assertIn("malformed", self.bad(lambda b: b.update(data={"0": b["data"][0]})))

    def test_item_without_index(self):
        self.assertIn("malformed", self.bad(lambda b: b["data"][1].pop("index")))

    def test_bool_or_string_index(self):
        self.assertIn("malformed", self.bad(lambda b: b["data"][1].update(index="1")))
        self.assertIn("malformed", self.bad(lambda b: b["data"][1].update(index=True)))

    def test_duplicate_or_out_of_range_index(self):
        self.assertIn("malformed", self.bad(lambda b: b["data"][1].update(index=0)))
        self.assertIn("malformed", self.bad(lambda b: b["data"][1].update(index=5)))

    def test_item_without_embedding(self):
        self.assertIn("malformed", self.bad(lambda b: b["data"][0].pop("embedding")))

    def test_item_not_a_dict(self):
        self.assertIn("malformed", self.bad(lambda b: b["data"].__setitem__(0, "x")))


if __name__ == "__main__":
    unittest.main()
