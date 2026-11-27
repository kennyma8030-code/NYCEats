export type AspectKey = "food" | "value" | "service" | "atmosphere" | "wait";
export type Category = "top" | "gems";
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
  // Over the rating's own fixed window, whatever the ledger window is. null
  // when nobody voiced an opinion or recommendation in it.
  rating?: Rating | null;
  // Where the map pins it (app/geo.py): null when no coordinates are known,
  // and then the place is listed without a pin.
  location?: Location | null;
  location_count?: number;
}

/** One location of a place. `address` is as the city's licence writes it, in capitals. */
export interface Location {
  lat: number;
  lng: number;
  address: string | null;
  borough: string | null;
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

/** A city with a board. `subreddit` is what the page's ?subreddit= takes. */
export interface City {
  subreddit: string;
  name: string;
  short: string;
  home: boolean;
  places: number;
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

export interface PlaceSummary {
  text: string;
  comment_count: number | null;
  written_at: string | null;
}

export interface RestaurantDetail {
  entity_key: string;
  summary: RestaurantSummary;
  // An AI-written paragraph; null for the many places without one.
  place_summary?: PlaceSummary | null;
  aspects: AspectDetail[];
  top_dishes: FacetValue[];
  top_descriptors: FacetValue[];
  neighborhoods: FacetValue[];
  addresses: unknown[] | null;
  // Every known location, the pinned one first; empty when none is known.
  locations?: Location[];
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
  // Only from /voices: what this mention counted as, and the level it carried.
  voice?: string | null;
  level?: number | null;
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

/** The rating's categories; "taste" is the food, so it is not an AspectKey. */
export type RatingCategory = "taste" | "value" | "service" | "atmosphere" | "wait";
export type Badge = "consensus" | "overhyped_mixed" | "hidden_gem";
/** Each board ranks by one value and filters on the rest: no composite score. */
export type BoardId = OverallBoard | RatingCategory;
/** The comments to list behind a count (/voices). */
/** With a category, a voice list has no bare endorsements, recommenders or superlatives. */
export type CategoryVoice = "pos" | "neg" | "neutral" | "opinions" | "all";
export type OverallBoard = "top" | "popular" | "gems";
export type Voice = "pos" | "neg" | "neutral" | "endorse" | "recommenders" | "superlative" | "opinions" | "all";

export interface CategoryRating {
  pos: number;
  neg: number;
  neutral: number;
  // A fraction in [0, 1]; null when nobody was positive or negative.
  pct_pos: number | null;
  lb: number | null;
  rankable: boolean;
}

/** People, one voice each (their latest in the window). pos, neg and neutral
 *  are stated opinions; endorse is a bare recommendation. */
export interface Rating {
  window_days: number;
  pos: number;
  neg: number;
  neutral: number;
  endorse: number;
  superlative: number;
  recommenders: number;
  pct_pos: number | null;
  lb: number | null;
  neg_share: number | null;
  rankable: boolean;
  busy: boolean;
  badge: Badge | null;
  last_voice: string | null;
  categories: Partial<Record<RatingCategory, CategoryRating>>;
}

/** The settings and cut-offs the badges were made with. */
export interface RatingLines {
  window_days: number;
  z: number;
  min_rated: number;
  min_category_rated: number;
  busy_pct: number;
  share_pct: number;
  gem_pct: number;
  busy_line: number | null;
  share_line: number | null;
  gem_line: number | null;
}

export interface BoardResponse {
  board: BoardId;
  // Only the window the counts and series cover, never what was ranked on.
  window_days: WindowDays;
  bucket_days: 1 | 7;
  cuisine: string | null;
  borough: string | null;
  lines: RatingLines;
  total: number;
  limit: number;
  offset: number;
  items: LedgerItem[];
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
}

export interface ExtractionGroup {
  prompt_hash: string;
  label: string;
  mentions: ExtractedMention[];
}

/** What the extractor took from one comment or post. `state` is the item's latest v6 read, null if never
 *  queued; `this_prompt` is false when that read was under another prompt than the one whose rows are shown,
 *  and `pending` is true while the item sits in a batch whose answer is not stored yet. */
export interface Extraction {
  item_id: string;
  groups: ExtractionGroup[];
  state: { extracted_at: string | null; failed: boolean; this_prompt: boolean; pending: boolean } | null;
}

/** What search matches in the browser: `[label, n]` rows, most used first.
 *  `n` is places for a cuisine or an area and mentions for a dish or a tag. */
export type TermRow = [string, number];
export interface SearchVocabulary {
  cuisines: TermRow[];
  areas: TermRow[];
  dishes: TermRow[];
  tags: TermRow[];
}

export interface SearchFilter {
  type: "cuisine" | "area" | "restaurant";
  value: string;
}

/** How the query was read, shown so a reader can see why a place is there. */
export interface SearchParse {
  search_text: string;
  include: SearchFilter[];
  exclude: SearchFilter[];
  ignored: string[];
  no_data: string[];
  hard: boolean;
}

export interface SearchItem {
  entity_key: string;
  name: string;
  cuisine: string | null;
  borough: string | null;
  neighborhood: string | null;
  /** The number the place is ranked by; `comments` are among the ones it counts. */
  people: number;
  total_people: number | null;
  best_similarity: number | null;
  /** Every comment `people` counts, one mention each, in the order shown;
   *  `comments` are the first of them and api.searchComments reads the rest.
   *  Null when the count is the board's own, which the place's page opens. */
  mention_ids: number[] | null;
  comments: Mention[];
}

export interface SearchResponse {
  query: string;
  mode: "fast" | "full";
  /** A fast answer the vocabulary could not fully explain: ask again in full. */
  needs_model: boolean;
  source: "vocabulary" | "model" | "cache" | "unparsed" | "fallback";
  parse: SearchParse;
  /** ok: the text was matched by meaning. text: it could not be, so its
   *  words were matched as text. unavailable: it could not be and held no
   *  word to match, so the list is the board. none: there was no text. */
  semantic: "ok" | "text" | "none" | "unavailable";
  ranked_by: "matching_people" | "people";
  total: number;
  items: SearchItem[];
  notes: string[];
}
