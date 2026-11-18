// Which city a page shows, and how that reaches the API. Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import { areaWords, cityFromQuery, currentCity, HOME, setCurrentCity, withCity } from "../src/state/city.ts";

test("no subreddit in the URL is New York", () => {
  assert.equal(cityFromQuery(""), HOME);
  assert.equal(cityFromQuery("?view=boards&subreddit="), HOME);
  assert.equal(cityFromQuery("?view=boards&subreddit=FoodLosAngeles"), "FoodLosAngeles");
});

test("every request carries the city, and New York's stay as they were", () => {
  assert.equal(withCity("/api/facets", HOME), "/api/facets");
  assert.equal(withCity("/api/ledger?window=7", HOME), "/api/ledger?window=7");
  assert.equal(withCity("/api/facets", "austinfood"), "/api/facets?subreddit=austinfood");
  assert.equal(withCity("/api/ledger?window=7", "austinfood"), "/api/ledger?window=7&subreddit=austinfood");
  assert.equal(withCity("/api/restaurants/joes%20pizza/mentions?sort=recent", "chicagofood"),
    "/api/restaurants/joes%20pizza/mentions?sort=recent&subreddit=chicagofood");
});

test("a request with no city named is the current city's", () => {
  assert.equal(currentCity(), HOME);
  setCurrentCity("austinfood");
  assert.equal(withCity("/api/facets"), "/api/facets?subreddit=austinfood");
  setCurrentCity(HOME);
  assert.equal(withCity("/api/facets"), "/api/facets");
});

test("only New York has boroughs", () => {
  assert.equal(areaWords(HOME).one, "Borough");
  assert.deepEqual(areaWords("FoodSanDiego"), { one: "Area", all: "All areas" });
});
