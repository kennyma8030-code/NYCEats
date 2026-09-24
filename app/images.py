"""Restaurant imagery, resolved lazily and cached in Postgres.

Why Wikimedia and not Google Places: Google's terms forbid caching a photo
reference (it expires, and clause 3.2.3(b) says no), so every render costs a
Details call plus a Photo call and the bytes can never be stored. Commons
images are CC-licensed and genuinely cacheable, and their coverage is
concentrated in exactly the places that top a mention-volume board -- Katz's,
Luger, Di Fara. Coverage of an ordinary slice shop is nil, which is what the
monogram fallback is for.

Deliberately NOT a generic stock food photo. Showing a stranger's bowl of
ramen under a real restaurant's name is a false claim about that restaurant,
and worse than showing nothing.

The provider list is ordered and pluggable: add a Google or Foursquare
resolver to PROVIDERS and the endpoint, the table and the cache all keep
working unchanged.
"""

import hashlib
import json
import re
import urllib.parse
import urllib.request

UA = {"User-Agent": "foodnyc-tracker/0.1 (personal project)"}
TIMEOUT = 8

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
FILEPATH = "https://commons.wikimedia.org/wiki/Special:FilePath/"

# A Wikidata search for "emily" returns a given name, a hurricane and a film
# long before it returns the Brooklyn pizzeria, so a hit has to be verified
# before its photo is trusted.
#
# The verification runs on CLAIMS, not on the description blurb. Descriptions
# are free prose and wildly inconsistent -- Katz's is "kosher style
# delicatessen on the Lower East Side of New York City" but Russ & Daughters
# is just "Fine Food Purveyor", which names neither a city nor a cuisine. A
# rule that reads those strings rejects the second one, which is a real
# restaurant with a real photo. P131 (located in the administrative territorial
# entity) says the same thing structurally and says it the same way every time.
NYC_QIDS = {
    "Q60",      # New York City
    "Q11299",   # Manhattan
    "Q18419",   # Brooklyn
    "Q18424",   # Queens
    "Q18426",   # The Bronx
    "Q18432",   # Staten Island
}
HUMAN_QID = "Q5"      # "Peter Luger" the restaurateur is not "Peter Luger" the steakhouse

IMAGE_WIDTH = 800


def _get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def _search_ids(name, limit=10):
    """Candidate QIDs for a name, in Wikidata's own relevance order."""
    url = WIKIDATA_API + "?" + urllib.parse.urlencode({
        "action": "wbsearchentities", "search": name, "language": "en",
        "uselang": "en", "format": "json", "limit": limit, "type": "item",
    })
    return [h["id"] for h in (_get_json(url).get("search") or []) if h.get("id")]


def _claim_values(claims, prop):
    """The values of one property, as QID strings or plain values."""
    out = []
    for claim in claims.get(prop) or []:
        value = (((claim.get("mainsnak") or {}).get("datavalue") or {})
                 .get("value"))
        if isinstance(value, dict) and "id" in value:
            out.append(value["id"])
        elif isinstance(value, str) and value.strip():
            out.append(value)
    return out


def _get_claims(qids):
    """Claims for up to 50 entities in ONE request.

    wbgetentities takes a batched id list, so verifying ten candidates costs
    the same round trip as verifying one.
    """
    if not qids:
        return {}
    url = WIKIDATA_API + "?" + urllib.parse.urlencode({
        "action": "wbgetentities", "ids": "|".join(qids[:50]),
        "props": "claims", "format": "json",
    })
    entities = _get_json(url).get("entities") or {}
    return {q: (e.get("claims") or {}) for q, e in entities.items()}


def _wikidata_match(name):
    """First candidate that is a photographed place in New York City.

    Returns (qid, commons_filename) or None. Two conditions, both required:
    it has a P18 image, and P131 puts it in one of the five boroughs. A
    candidate whose P131 points at a neighbourhood rather than a borough gets
    one level of indirection -- "Lower East Side" resolves to Manhattan.

    Strict on purpose. A wrong photo is worse than no photo: it makes a false
    claim about a real business, and nobody looking at it can tell.
    """
    qids = _search_ids(name)
    claims = _get_claims(qids)

    photographed, indirect = [], {}
    for qid in qids:                       # search order = relevance order
        c = claims.get(qid) or {}
        if HUMAN_QID in _claim_values(c, "P31"):
            continue
        images_ = _claim_values(c, "P18")
        if not images_:
            continue
        located = _claim_values(c, "P131")
        if NYC_QIDS.intersection(located):
            return qid, images_[0]
        photographed.append((qid, images_[0]))
        indirect[qid] = located

    # Nothing sat directly in a borough. Resolve the places they DO sit in and
    # look one level up, in a single batched call.
    parents = [p for qid, _ in photographed for p in indirect.get(qid, [])]
    parent_claims = _get_claims(list(dict.fromkeys(parents)))
    for qid, filename in photographed:
        for parent in indirect.get(qid, []):
            if NYC_QIDS.intersection(
                    _claim_values(parent_claims.get(parent) or {}, "P131")):
                return qid, filename
    return None


def _commons_credit(filename):
    """Author and licence for a Commons file.

    CC images are free to use and NOT free of obligations -- most require
    credit. Fetching it here means the UI is always able to render one.
    """
    url = COMMONS_API + "?" + urllib.parse.urlencode({
        "action": "query", "titles": "File:" + filename, "prop": "imageinfo",
        "iiprop": "extmetadata", "format": "json",
    })
    pages = ((_get_json(url).get("query") or {}).get("pages") or {})
    for page in pages.values():
        for info in page.get("imageinfo") or []:
            meta = info.get("extmetadata") or {}
            artist = (meta.get("Artist") or {}).get("value") or ""
            licence = (meta.get("LicenseShortName") or {}).get("value") or ""
            # extmetadata hands back HTML (the artist is usually a link).
            artist = re.sub(r"<[^>]+>", "", artist).strip()
            return artist or None, licence or None
    return None, None


def resolve_wikimedia(entity_key, display_name):
    """Provider: Wikidata -> Commons. Returns a row dict, or None to pass.

    Tries the city's official name first and the typed key second. They differ
    more often than you would think: the licence says "PETER LUGER STEAK HOUSE"
    and
    Wikidata files the restaurant under that, while a bare "peter luger" search
    returns a medieval magistrate, a chemist and a restaurateur before it
    returns the steakhouse.
    """
    names = [n for n in (display_name, entity_key) if n and n.strip()]
    for name in dict.fromkeys(names):          # dedupe, keep order
        match = _wikidata_match(name)
        if not match:
            continue
        qid, filename = match
        artist, licence = _commons_credit(filename)
        quoted = urllib.parse.quote(filename.replace(" ", "_"))
        return {
            "status": "found",
            "source": "wikimedia",
            "source_ref": qid,
            "url": f"{FILEPATH}{quoted}?width={IMAGE_WIDTH}",
            "attribution": artist,
            "license": licence,
            "source_url": f"https://www.wikidata.org/wiki/{qid}",
        }
    return None


# Ordered. The first provider to return a row wins; add Google or Foursquare
# here and nothing else in the module or the API has to change.
PROVIDERS = (resolve_wikimedia,)

MISS = {"status": "none", "source": None, "source_ref": None, "url": None,
        "attribution": None, "license": None, "source_url": None}


def resolve(entity_key, display_name):
    """Run the provider chain. Returns (row, cacheable). Never raises.

    The two kinds of failure are NOT the same and must not be stored the same
    way:

      a provider returned nothing  -> there is no picture. Cache it, so a place
                                      without one costs a single lookup ever
                                      rather than one per page load.
      a provider raised            -> we do not know. A timeout or a rate limit
                                      is not evidence, and writing 'none' here
                                      would make one bad minute permanent for
                                      that restaurant.

    Only the first is cacheable. This was a live bug: hammering Wikidata in a
    loop tripped its rate limit, and every place resolved during it would have
    been recorded as having no image, forever.
    """
    errored = False
    for provider in PROVIDERS:
        try:
            found = provider(entity_key, display_name)
        except Exception:
            errored = True    # network, rate limit, shape change -- try the next
            continue
        if found:
            return found, True
    if errored:
        return dict(MISS, status="error"), False
    return dict(MISS), True


# ---------------------------------------------------------------------------
# Fallback. No network, no dependency, always available.
# ---------------------------------------------------------------------------

# Fixed hues, sampled around the wheel, picked by hash so a given restaurant
# always gets the same tile. Mid lightness so white text sits legibly on all
# of them in either theme.
_HUES = (210, 12, 145, 275, 32, 190, 330, 95)


def monogram_svg(entity_key, display_name=None):
    """A deterministic initials tile for a place with no photo.

    Honest by construction: it says "no picture" without pretending otherwise,
    and it is stable, so the same restaurant never changes colour between
    loads or between uvicorn workers.
    """
    name = (display_name or entity_key or "?").strip()
    words = [w for w in re.split(r"\s+", name) if w]
    initials = "".join(w[0] for w in words[:2]).upper() or "?"

    digest = hashlib.sha256((entity_key or "").encode("utf-8")).digest()
    hue = _HUES[digest[0] % len(_HUES)]

    # XML-escaped: a restaurant name is user-ish data and must not be able to
    # close a tag.
    safe = initials.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" '
        f'width="400" height="400" role="img" '
        f'aria-label="{safe}">'
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="hsl({hue} 46% 46%)"/>'
        f'<stop offset="1" stop-color="hsl({hue} 46% 34%)"/>'
        f'</linearGradient></defs>'
        f'<rect width="400" height="400" fill="url(#g)"/>'
        f'<text x="200" y="200" fill="rgba(255,255,255,.92)" '
        f'font-family="system-ui,-apple-system,Segoe UI,Helvetica,Arial,sans-serif" '
        f'font-size="150" font-weight="600" text-anchor="middle" '
        f'dominant-baseline="central">{safe}</text></svg>'
    )


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

COLUMNS = ("entity_key, status, source, source_ref, url, attribution, "
           "license, source_url, locked, fetched_at")


def get_cached(conn, entity_key, fetch_one):
    return fetch_one(conn, f"select {COLUMNS} from restaurant_images "
                           f"where entity_key = %s", (entity_key,))


def store(conn, entity_key, row, fetch_one):
    """Write a resolution result. `locked` rows are never overwritten."""
    return fetch_one(conn, f"""
        insert into restaurant_images
          (entity_key, status, source, source_ref, url, attribution,
           license, source_url, fetched_at)
        values (%s, %s, %s, %s, %s, %s, %s, %s, now())
        on conflict (entity_key) do update set
          status      = excluded.status,
          source      = excluded.source,
          source_ref  = excluded.source_ref,
          url         = excluded.url,
          attribution = excluded.attribution,
          license     = excluded.license,
          source_url  = excluded.source_url,
          fetched_at  = now()
        where not restaurant_images.locked
        returning {COLUMNS}
    """, (entity_key, row["status"], row["source"], row["source_ref"],
          row["url"], row["attribution"], row["license"], row["source_url"]))
