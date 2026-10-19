"""A local stand-in for Anthropic's Messages and Message Batches endpoints, so no test spends money.

The real SDK client is pointed at it (anthropic_v6.client(key, base_url=...)),
so tests see exactly the JSON the SDK puts on the wire and parse exactly what
it parses. Every request body is kept in `requests` / `batch_requests`.

`answer(params) -> (status, body)` decides each answer. The default reads
the comment out of the user message and returns one mention per word
starting with "Place" (so "PlaceAlpha and PlaceBeta" gives two), with usage
in the shape Haiku 5.5 reports. Helpers build the other outcomes.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
        self.submit_status = None   # (status, body) to fail the next batch create
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
                    return self._send(*fake.answer(body))
                self._send(404, {"type": "error", "error": {"type": "not_found_error", "message": self.path}})

            def do_GET(self):
                parts = self.path.split("?")[0].strip("/").split("/")
                # v1/messages/batches/<id>[/results]
                bid = parts[3]
                if len(parts) == 5 and parts[4] == "results":
                    return self._send(200, fake._results(bid), "application/binary")
                return self._send(200, fake._batch(bid, poll=True))

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
            self.batches[bid] = {"results": out, "polls": 0, "n": len(body["requests"])}
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
                "created_at": "2026-10-19T00:00:00Z", "expires_at": "2026-10-20T00:00:00Z",
                "ended_at": "2026-10-19T00:10:00Z" if ended else None,
                "cancel_initiated_at": None, "archived_at": None,
                "results_url": f"{self.base_url}/v1/messages/batches/{bid}/results" if ended else None}

    def _results(self, bid):
        lines = [json.dumps({"custom_id": cid, "result": res})
                 for cid, res in self.batches[bid]["results"].items()]
        return ("\n".join(lines) + "\n").encode()
