"""Comments the archive publishes late, and comments whose post comes later still.

Arctic Shift does not make comments visible in the order they were posted:
on r/FoodNYC the p99 is 8.8 hours after newer ones, and a post can appear up
to ~20 hours after its comments. A poll that stops at what the previous poll
saw steps over the late ones, and a comment whose post is missing cannot be
stored at all. The replay below models both against an in-memory archive and
database, with a clock, and runs the real poll, orphan and re-sweep code.
No network, no database.
"""

import io
import random
import types
import unittest
from contextlib import redirect_stdout
from unittest import mock

import fakes  # noqa: F401  (puts the repo root on sys.path)

import arctic
import poller

SUB = "FoodNYC"
HOUR = 3600
DAY = 24 * HOUR
T0 = 1_700_000_000


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def check_after(after):
    """Arctic answers HTTP 400 to an `after` that is not a plausible date
    (checked live: -1, 0 and 1 fail, 1000000000 works)."""
    if after is not None and after < 1_000_000_000:
        raise AssertionError(f"Arctic answers 400 for after={after}")


class Archive:
    """Arctic Shift as seen at clock(): only what is visible by then."""

    def __init__(self, clock, comments, posts):
        self.clock, self.comments, self.posts = clock, comments, posts
        self.requests = 0

    def _visible(self):
        return [c for c in self.comments if c["visible_at"] <= self.clock()]

    def newest_comments(self, subreddit, limit=arctic.PAGE, before=None):
        self.requests += 1
        rows = [c for c in self._visible() if before is None or c["created_utc"] < before]
        return sorted(rows, key=lambda c: (-c["created_utc"], c["id"]))[:limit]

    def search_page(self, kind, subreddit, after=None, before=None, limit=arctic.PAGE):
        assert kind == "comments"
        check_after(after)
        self.requests += 1
        rows = [c for c in self._visible() if after is None or c["created_utc"] > after]
        return sorted(rows, key=lambda c: (c["created_utc"], c["id"]))[:limit]

    def posts_by_id(self, bare_ids):
        self.requests += 1
        return [p for p in self.posts.values()
                if p["id"] in set(bare_ids) and p["visible_at"] <= self.clock()]

    def get(self, path, params):
        """arctic._get, for the one call left unpatched: a thread's comments,
        so the real arctic.all_thread_comments and its paging run."""
        assert path == "comments/search" and "link_id" in params, (path, params)
        after = params.get("after")
        check_after(after)
        self.requests += 1
        rows = [c for c in self._visible() if c["link_id"] == "t3_" + params["link_id"]
                and (after is None or c["created_utc"] > after)]
        return sorted(rows, key=lambda c: (c["created_utc"], c["id"]))[:params["limit"]]


class Store:
    """threads + comments, with the real foreign key enforced."""

    def __init__(self):
        self.threads, self.comments = set(), {}

    def newest_stored_utc(self, conn, subreddit):
        return max((c["created_utc"] for c in self.comments.values()), default=None)

    def oldest_stored_utc(self, conn, subreddit):
        return min((c["created_utc"] for c in self.comments.values()), default=None)

    def existing_thread_ids(self, conn, ids):
        return {i for i in ids if i in self.threads}

    def missing_thread_ids(self, conn, ids):
        return set(ids) - self.threads

    def insert_threads(self, conn, posts):
        new = {"t3_" + p["id"] for p in posts} - self.threads
        self.threads |= new
        return len(new)

    def insert_comments(self, conn, comments):
        for c in comments:
            assert c["link_id"] in self.threads, "foreign key violation"
        new = [c for c in comments if c["id"] not in self.comments]
        for c in new:
            self.comments[c["id"]] = c
        return len(new)

    def fill_tree(self, conn, ids):
        return 0


def corpus(seed=7, days=3):
    """~2,000 comments over `days`, one thread per hour.

    Visibility: 90% after 20 s, 8% one to eight hours late, 2% nine to thirty
    hours late (past the poll's lag). One thread in ten has its post appear
    twenty hours after it was made, so its first comments arrive orphaned.
    """
    rng = random.Random(seed)
    posts, comments = {}, []
    for h in range(days * 24):
        pid = f"p{h:04d}"
        made = T0 + h * HOUR
        late = rng.random() < 0.1
        posts[pid] = {"id": pid, "subreddit": SUB, "title": "t", "created_utc": made,
                      "visible_at": made + (20 * HOUR if late else 20)}
    for i in range(days * 24 * 28):
        made = T0 + int(i * DAY / 28 / 24) + 1
        r = rng.random()
        delay = 20 if r < 0.90 else rng.randint(1 * HOUR, 8 * HOUR) if r < 0.98 \
            else rng.randint(9 * HOUR, 30 * HOUR)
        pid = f"p{(made - T0) // HOUR:04d}"
        comments.append({"id": f"c{i:05d}", "subreddit": SUB, "link_id": "t3_" + pid,
                         "parent_id": "t3_" + pid, "created_utc": made,
                         "visible_at": made + delay, "body": "b"})
    return comments, posts


class Replay(unittest.TestCase):
    def replay(self, lag, retry_orphans=True, resweep=True, days=3, settle_days=2):
        comments, posts = corpus(days=days)
        clock = Clock(T0)
        archive, store = Archive(clock, comments, posts), Store()
        seen, orphans = {}, {}
        patches = [
            mock.patch.multiple(arctic, newest_comments=archive.newest_comments,
                                search_page=archive.search_page,
                                posts_by_id=archive.posts_by_id, _get=archive.get),
            mock.patch.multiple("db", newest_stored_utc=store.newest_stored_utc,
                                oldest_stored_utc=store.oldest_stored_utc,
                                existing_thread_ids=store.existing_thread_ids,
                                missing_thread_ids=store.missing_thread_ids,
                                insert_threads=store.insert_threads,
                                insert_comments=store.insert_comments,
                                fill_tree=store.fill_tree),
            mock.patch("time.time", clock), mock.patch("time.sleep"),
            mock.patch.object(poller, "LAG", lag),
        ]
        if not retry_orphans:
            patches.append(mock.patch.object(poller, "retry_orphans", lambda *a, **k: 0))
        swept = 0
        for p in patches:
            p.start()
        try:
            with redirect_stdout(io.StringIO()):
                end = T0 + (days + settle_days) * DAY
                last_sweep = T0
                while clock.t < end:
                    poller.poll_once(None, SUB, seen, orphans)
                    if resweep and clock.t - last_sweep >= poller.RESWEEP_EVERY:
                        swept += poller.resweep_once(None, SUB, poller.RESWEEP_HOURS,
                                                     orphans.setdefault(SUB, {}))
                        last_sweep = clock.t
                    clock.t += 15 * 60          # a poll every 15 minutes
        finally:
            for p in reversed(patches):
                p.stop()
        missing = {c["id"] for c in comments} - set(store.comments)
        return missing, swept, archive.requests

    def test_the_old_poll_loses_comments(self):
        # No lag, no second look at orphans, no re-sweep: what main did.
        missing, _, _ = self.replay(lag=0, retry_orphans=False, resweep=False)
        self.assertGreater(len(missing), 20)

    def test_lag_and_orphan_retries_alone_leave_only_the_very_late(self):
        missing, _, _ = self.replay(lag=8 * HOUR, resweep=False)
        comments, _ = corpus()
        delay = {c["id"]: c["visible_at"] - c["created_utc"] for c in comments}
        self.assertTrue(missing, "the fixture should have comments later than the lag")
        self.assertTrue(all(delay[i] > 8 * HOUR for i in missing),
                        "a comment inside the lag was lost")

    def test_with_the_resweep_nothing_is_lost(self):
        missing, swept, requests = self.replay(lag=8 * HOUR)
        self.assertEqual(missing, set())
        self.assertGreater(swept, 0, "the re-sweep should have found the very late ones")
        # Five days of 15-minute polls is 480 polls; the lag and the sweeps
        # cost a few requests each, not dozens.
        self.assertLess(requests, 480 * 6)


class Orphans(unittest.TestCase):
    def test_bounded_oldest_dropped(self):
        pending = {}
        with mock.patch.object(poller, "ORPHAN_MAX", 3):
            poller.remember_orphans(pending, ["t3_a", "t3_b"], now=1)
            poller.remember_orphans(pending, ["t3_c", "t3_d"], now=2)
        self.assertEqual(set(pending), {"t3_b", "t3_c", "t3_d"})

    def test_first_drop_time_is_kept(self):
        pending = {}
        poller.remember_orphans(pending, ["t3_a"], now=1)
        poller.remember_orphans(pending, ["t3_a"], now=5)
        self.assertEqual(pending, {"t3_a": 1})

    def test_post_that_arrives_pulls_its_thread(self):
        db = mock.Mock()
        db.existing_thread_ids.return_value = set()
        pending = {"t3_late": 100, "t3_gone": 100}
        posts = mock.Mock(return_value=[{"id": "late", "subreddit": SUB}])
        pulled = mock.Mock()
        with mock.patch.object(poller, "db", db), \
                mock.patch.object(poller.arctic, "posts_by_id", posts), \
                mock.patch.object(poller, "pull_threads", pulled), redirect_stdout(io.StringIO()):
            n = poller.retry_orphans(None, pending, now=200)
        self.assertEqual(n, 1)
        posts.assert_called_once_with(["gone", "late"])
        pulled.assert_called_once_with(None, {"late"})
        self.assertEqual(pending, {"t3_gone": 100})

    def test_thread_stored_by_another_route_is_pulled_without_asking(self):
        db = mock.Mock()
        db.existing_thread_ids.return_value = {"t3_x"}
        posts, pulled = mock.Mock(), mock.Mock()
        pending = {"t3_x": 100}
        with mock.patch.object(poller, "db", db), \
                mock.patch.object(poller.arctic, "posts_by_id", posts), \
                mock.patch.object(poller, "pull_threads", pulled), redirect_stdout(io.StringIO()):
            poller.retry_orphans(None, pending, now=200)
        posts.assert_not_called()
        pulled.assert_called_once_with(None, {"x"})
        self.assertEqual(pending, {})

    def test_given_up_after_the_ttl(self):
        db = mock.Mock()
        pending = {"t3_old": 0}
        with mock.patch.object(poller, "db", db), redirect_stdout(io.StringIO()):
            self.assertEqual(poller.retry_orphans(None, pending, now=poller.ORPHAN_TTL + 1), 0)
        self.assertEqual(pending, {})
        db.existing_thread_ids.assert_not_called()


class ResweepSchedule(unittest.TestCase):
    def test_due_once_per_interval(self):
        r = poller.Resweep(["FoodNYC", "chicagofood"], {}, hours=48, every=6 * HOUR)
        self.assertEqual(r.due(now=6 * HOUR), ["FoodNYC", "chicagofood"])
        r.last = {"FoodNYC": 10, "chicagofood": 10}
        self.assertEqual(r.due(now=10 + 6 * HOUR - 1), [])
        self.assertEqual(r.due(now=10 + 6 * HOUR), ["FoodNYC", "chicagofood"])

    def test_run_chores_resweeps_due_cities_and_survives_a_failure(self):
        r = poller.Resweep(["FoodNYC", "chicagofood"], {}, hours=48, every=HOUR)
        r.last = {"FoodNYC": 0, "chicagofood": 0}
        args = types.SimpleNamespace(extract=False, embed=False, resweep=r)
        calls = []

        def resweep_once(conn, name, hours, pending):
            calls.append(name)
            if name == "FoodNYC":
                raise RuntimeError("archive down")
            return 0
        conn = mock.Mock(closed=0)
        with mock.patch.multiple(poller, resweep_once=resweep_once,
                                 settle_once=mock.Mock(), disk_once=mock.Mock()), \
                redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            poller.run_chores(conn, args)
        self.assertEqual(calls, ["FoodNYC", "chicagofood"])
        self.assertEqual(set(r.last), {"FoodNYC", "chicagofood"})
        self.assertEqual(r.due(), [])


if __name__ == "__main__":
    unittest.main()
