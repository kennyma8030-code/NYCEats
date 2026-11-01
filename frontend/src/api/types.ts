export type AspectKey = "food" | "value" | "service" | "atmosphere" | "wait";
export type Category = "trending" | "top" | "gems";
export type WindowDays = 7 | 14 | 30 | 90 | 180 | 365;
export type Need = "value" | "atmosphere" | "service" | "wait";
/** An aspect a place does badly on: the bottom tenth of scored places. */
export type Flaw = AspectKey;
/** A row of /api/names: [key, name|null, cuisine, borough, mentions, aliases|null, flags].
 *  name is null when it is just the key in title case; flags: 1 chain, 2 closed. */
export type NameRow = [string, string | null, string | null, string | null, number, string[] | null, number];
/** The API's mention orderings: score is Reddit upvotes, the others are post time. */
export type CommentSort = "score" | "recent" | "oldest";
/** Which scoring ranks the ledger: v1 is the original, v2 the new one
 *  (recent people, bad experiences count double, standout-complaint flag). */
export type Algo = "v1" | "v2";

// null means nobody rated it, which is not the same as a middling score.
export type Aspects = Record<AspectKey, number | null>;

export interface LedgerItem {
  entity_key: string;
  name: string;
  cuisine: string | null;
  borough: string | null;
  boroughs: string[] | null;
  neighborhood: string | null;
  current: number;
  previous: number;
  change_pct: number | null;
  series: number[];
  previous_series: number[];
  total_mentions: number;
  distinct_authors: number | null;
  aspects: Aspects;
  sentiment: number | null;
  // New ranking only; null under the original.
  people: number | null;
  flagged: boolean | null;
  strong_neg_people: number | null;
  strong_neg_share: number | null;
}

export interface LedgerResponse {
  category: Category;
  window_days: WindowDays;
  bucket_days: 1 | 7;
  // Every filter the rows were ranked under, echoed so a stale list can be
  // told from a current one (lib/fresh.ts).
  algo: Algo;
  topic: string | null;
  cuisine: string | null;
  borough: string | null;
  needs: Need[];
  flaws: Flaw[];
  total: number;
  items: LedgerItem[];
}

export interface FacetValue {
  name: string;
  n: number;
}

export interface Facets {
  cuisines: FacetValue[];
  boroughs: FacetValue[];
  statuses: FacetValue[];
  descriptors: FacetValue[];
}

export interface AspectDetail {
  aspect: string;
  n_obs: number;
  aspect_score: number | null;
  raw_mean: number | null;
  city_mean: number | null;
}

export interface RestaurantSummary {
  entity_key: string;
  official_name: string | null;
  cuisine: string | null;
  boroughs: string[] | null;
  raw_mentions: number | null;
  distinct_authors: number | null;
  food: number | null;
  value: number | null;
  service: number | null;
  atmosphere: number | null;
  wait: number | null;
}

export interface RestaurantDetail {
  entity_key: string;
  summary: RestaurantSummary;
  aspects: AspectDetail[];
  top_dishes: FacetValue[];
  top_descriptors: FacetValue[];
  neighborhoods: FacetValue[];
  addresses: unknown[] | null;
}

export interface Mention {
  mention_id: number;
  comment_id: string;
  author: string | null;
  score: number | null;
  created_utc: string | null;
  body: string | null;
  // Relative ("/r/FoodNYC/...") or absolute; null when deleted from Reddit.
  permalink: string | null;
  was_deleted_later: boolean;
  thread_title: string | null;
  is_negated: boolean;
  is_firsthand: boolean | null;
  aspects: Partial<Aspects> | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

/** A restaurant a stream comment mentions. */
export interface FeedPlace {
  key: string;
  name: string;
}

/** One post or comment in the live stream, newest first. `cursor` is opaque:
 *  pass it back as before= for older items or after= for newer ones. */
export interface FeedItem {
  kind: "post" | "comment";
  id: string;
  cursor: string;
  author: string | null;
  score: number | null;
  created_utc: string;
  body: string;
  permalink: string | null;
  was_deleted_later: boolean;
  /** The post's own title for a post; the thread it is in for a comment. */
  title: string | null;
  /** Posts only. */
  num_comments: number | null;
  /** Comments only: posts are not extracted. */
  places: FeedPlace[];
}

export interface Feed {
  items: FeedItem[];
}

/** One mention row as stored. Levels run -2..2; null means the model said nothing. */
export interface ExtractedMention {
  mention_id: number;
  restaurant_raw: string;
  entity_key: string;
  resolved_key: string | null;
  resolved_name: string | null;
  overall_level: number | null;
  taste_level: number | null;
  value_level: number | null;
  service_level: number | null;
  atmosphere_level: number | null;
  wait_level: number | null;
  dish_opinions: { dish: string; level: number | null; avoid: boolean | null }[] | null;
  price_level: number | null;
  timeframe: string | null;
  trend: string | null;
  status: string | null;
  avoid: boolean | null;
  kind: string | null;
  experience: string | null;
  opinion: string | null;
  tags: string[] | null;
  is_chain: boolean | null;
  /** Legacy extractor fields, present on old rows only. */
  aspects: Record<string, number | null> | null;
  dishes: unknown;
  is_negated: boolean;
}

export interface ExtractionGroup {
  prompt_hash: string;
  schema_version: number | null;
  label: string;
  mentions: ExtractedMention[];
}

/** What the extractor took from one comment or post. `state` is the v6 bookkeeping row, null if never queued. */
export interface Extraction {
  item_id: string;
  groups: ExtractionGroup[];
  state: { extracted_at: string | null; error: string | null; cost_usd: number | null } | null;
}
