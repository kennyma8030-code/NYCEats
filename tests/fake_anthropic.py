"""A local stand-in for Anthropic's Messages and Message Batches endpoints, so no test spends money.

The real SDK client is pointed at it (anthropic_v6.client(key, base_url=...)),
so tests see exactly the JSON the SDK puts on the wire and parse exactly what
it parses. Every request body is kept in `requests` / `batch_requests`. A
direct request with "stream": true (thread mode) gets the same answer as
server-sent events, which the SDK assembles back into the message.

`answer(params) -> (status, body)` decides each answer. The default reads
the comment out of the user message and returns one mention per word
starting with "Place" (so "PlaceAlpha and PlaceBeta" gives two), with usage
in the shape Haiku 5.5 reports. Helpers build the other outcomes.
"""

import datetime as dt
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

MODEL = "claude-haiku-5-5"


def mention(name, **kw):
    m = {"name": name, "named_in": "comment", "kind": "restaurant", "location": None,
         "experience": "firsthand", "dishes": [], "notes": [],
         "aspects": {"taste": "praise", "value": None, "service": None, "atmosphere": None, "wait": None},
         "opinion": "stated", "overall": "praise", "avoid": False, "timeframe": "current",
         "trend": None, "status": None, "price": None, "tags": []}
    m.update(kw)
    return m


USAGE = {"input_tokens": 400, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 12000,
         "output_tokens": 900, "output_tokens_details": {"thinking_tokens": 700}}


def message(text, stop="end_turn", usage=None):
    return {"id": "msg_fake", "type": "message", "role": "assistant", "model": MODEL,
            "content": [{"type": "thinking", "thinking": "", "signature": "sig"},
                        {"type": "text", "text": text}] if text is not None else [],
            "stop_reason": stop, "stop_sequence": None, "usage": dict(usage or USAGE)}


def ok(mentions):
    return 200, message(json.dumps({"mentions": mentions}))


def user_text(params):
    return params["messages"][0]["content"]


def default_answer(params):
    text = user_text(params)
    body = text.split("<comment_to_extract>")[-1] if "<comment_to_extract>" in text else \
        text.replace("<post_title>", "<post_title> ").replace("<post_body>", "<post_body> ")
    names = [w.strip(".,!?<>/") for w in body.replace("\n", " ").split(" ") if w.startswith("Place")]
    return ok([mention(n) for n in dict.fromkeys(names)])


def error(status, kind, msg="nope"):
    return status, {"type": "error", "error": {"type": kind, "message": msg}}


class FakeAnthropic:
    def __init__(self, answer=default_answer, polls_until_ended=0, batch_results=None):
        self.answer = answer
        self.polls_until_ended = polls_until_ended
        # batch_results(custom_id, params) -> result dict; default: answer() as succeeded/errored
        self.batch_results = batch_results
        self.requests = []          # direct /v1/messages bodies
        self.batch_requests = []    # every request inside every created batch
        self.batches = {}
        self.submit_status = None   # (status, body) to refuse the next batch create
        self.accept_then_fail = None  # (status, body): create the next batch, then answer this
        self.forgotten = set()      # batch ids that answer 404 (past retention, another key)
        self.get_failures = []      # (status, body) answers for the next GETs, one each, then normal
        self.truncate_results = 0   # the next N results downloads stop halfway through the body
        self.no_results_url = 0     # the next N batch reads say ended but carry no results_url
        self.gets = 0               # every GET served
        # What goes wrong in the next streamed answers, one each: "cut" (the
        # connection drops part way) or an error body sent as an error event
        # after the stream has started.
        self.stream_failures = []
        # Seconds between two events of a streamed answer; a plain answer
        # waits as long as its stream would have taken, then comes whole.
        self.event_delay = 0.0
        self._lock = threading.Lock()
        self._n = 0

    # -- server
    def __enter__(self):
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, status, body, ctype="application/json"):
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("content-type", ctype)
                self.send_header("content-length", str(len(data)))
                if status == 429:
                    self.send_header("retry-after", "0")
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["content-length"])))
                if self.path.startswith("/v1/messages/batches"):
                    return self._send(*fake._create_batch(body))
                if self.path.startswith("/v1/messages"):
                    with fake._lock:
                        fake.requests.append(body)
                        fail = fake.stream_failures.pop(0) if body.get("stream") and fake.stream_failures else None
                    status, answer = fake.answer(body)
                    if body.get("stream") and status == 200:
                        return self._stream(answer, fail)
                    if fake.event_delay and status == 200:
                        # The same generation time, all of it before the first byte.
                        threading.Event().wait(fake.event_delay * (4 * len(answer["content"]) + 3))
                    return self._send(status, answer)
                self._send(404, {"type": "error", "error": {"type": "not_found_error", "message": self.path}})

            def _stream(self, msg, fail=None):
                """The answer as the event stream the Messages API sends, cut
                short or ended by an error event when the test asks."""
                start = dict(msg, content=[], stop_reason=None, stop_sequence=None,
                             usage=dict(msg["usage"], output_tokens=1))
                events = [("message_start", {"type": "message_start", "message": start})]
                for i, block in enumerate(msg["content"]):
                    if block["type"] == "thinking":
                        first = {"type": "thinking", "thinking": "", "signature": ""}
                        deltas = [{"type": "thinking_delta", "thinking": block["thinking"]},
                                  {"type": "signature_delta", "signature": block["signature"]}]
                    else:
                        first = {"type": "text", "text": ""}
                        text = block["text"]
                        deltas = [{"type": "text_delta", "text": text[:len(text) // 2]},
                                  {"type": "text_delta", "text": text[len(text) // 2:]}]
                    events.append(("content_block_start", {"type": "content_block_start", "index": i,
                                                           "content_block": first}))
                    events += [("content_block_delta", {"type": "content_block_delta", "index": i, "delta": d})
                               for d in deltas]
                    events.append(("content_block_stop", {"type": "content_block_stop", "index": i}))
                events.append(("message_delta", {"type": "message_delta",
                                                  "delta": {"stop_reason": msg["stop_reason"], "stop_sequence": None},
                                                  "usage": msg["usage"]}))
                events.append(("message_stop", {"type": "message_stop"}))
                if fail is not None:
                    events = events[:3]
                    if fail != "cut":
                        events.append(("error", fail))
                chunks = [f"event: {e}\ndata: {json.dumps(d)}\n\n".encode() for e, d in events]
                size = sum(len(c) for c in chunks)
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                # A cut promises more than it sends, then hangs up: a connection lost mid-answer.
                self.send_header("content-length", str(size + (1000 if fail == "cut" else 0)))
                self.end_headers()
                for c in chunks:
                    if fake.event_delay:
                        threading.Event().wait(fake.event_delay)
                    self.wfile.write(c)
                    self.wfile.flush()
                if fail == "cut":
                    self.close_connection = True

            def do_GET(self):
                with fake._lock:
                    fake.gets += 1
                    fail = fake.get_failures.pop(0) if fake.get_failures else None
                if fail is not None:
                    return self._send(*fail)
                path, _, query = self.path.partition("?")
                parts = path.strip("/").split("/")
                if len(parts) == 3:                    # v1/messages/batches: the list, newest first
                    q = parse_qs(query)
                    ids = sorted(fake.batches, reverse=True)
                    if "after_id" in q:
                        ids = [b for b in ids if b < q["after_id"][0]]
                    limit = int(q.get("limit", ["20"])[0])
                    data = [fake._batch(b) for b in ids[:limit]]
                    return self._send(200, {"data": data, "has_more": len(ids) > limit,
                                            "first_id": data[0]["id"] if data else None,
                                            "last_id": data[-1]["id"] if data else None})
                # v1/messages/batches/<id>[/results]
                bid = parts[3]
                if bid not in fake.batches or bid in fake.forgotten:
                    return self._send(*error(404, "not_found_error", f"no batch {bid}"))
                if len(parts) == 5 and parts[4] == "results":
                    data = fake._results(bid)
                    if fake.truncate_results:
                        fake.truncate_results -= 1
                        # Promise the whole body, send half, hang up: a stream cut mid-download.
                        self.send_response(200)
                        self.send_header("content-type", "application/binary")
                        self.send_header("content-length", str(len(data)))
                        self.end_headers()
                        self.wfile.write(data[:len(data) // 2])
                        self.wfile.flush()
                        self.close_connection = True
                        return
                    return self._send(200, data, "application/binary")
                b = fake._batch(bid, poll=True)
                if fake.no_results_url and b["processing_status"] == "ended":
                    fake.no_results_url -= 1
                    b["results_url"] = None
                return self._send(200, b)

        class Server(ThreadingHTTPServer):
            # The SDK keeps connections alive in its pool; closing the server
            # must not wait for a client that will never hang up.
            daemon_threads = True
            block_on_close = False

        self.server = Server(("127.0.0.1", 0), H)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

    # -- batches
    def _create_batch(self, body):
        if self.submit_status is not None:
            st, self.submit_status = self.submit_status, None
            return st
        with self._lock:
            self._n += 1
            bid = f"msgbatch_fake{self._n:03d}"
            out = {}
            for r in body["requests"]:
                self.batch_requests.append(r)
                if self.batch_results:
                    out[r["custom_id"]] = self.batch_results(r["custom_id"], r["params"])
                else:
                    st, msg = self.answer(r["params"])
                    out[r["custom_id"]] = ({"type": "succeeded", "message": msg} if st == 200 else
                                           {"type": "errored", "error": msg})
            self.batches[bid] = {"results": out, "polls": 0, "n": len(body["requests"]),
                                 "created": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")}
        if self.accept_then_fail is not None:
            st, self.accept_then_fail = self.accept_then_fail, None
            return st
        return 200, self._batch(bid)

    def _batch(self, bid, poll=False):
        b = self.batches[bid]
        if poll:
            b["polls"] += 1
        ended = b["polls"] > self.polls_until_ended
        n = b["n"]
        return {"id": bid, "type": "message_batch",
                "processing_status": "ended" if ended else "in_progress",
                "request_counts": {"processing": 0 if ended else n, "succeeded": n if ended else 0,
                                   "errored": 0, "canceled": 0, "expired": 0},
                "created_at": b["created"], "expires_at": "2099-01-01T00:00:00Z",
                "ended_at": "2026-10-19T00:10:00Z" if ended else None,
                "cancel_initiated_at": None, "archived_at": None,
                "results_url": f"{self.base_url}/v1/messages/batches/{bid}/results" if ended else None}

    def _results(self, bid):
        lines = [json.dumps({"custom_id": cid, "result": res})
                 for cid, res in self.batches[bid]["results"].items()]
        return ("\n".join(lines) + "\n").encode()
