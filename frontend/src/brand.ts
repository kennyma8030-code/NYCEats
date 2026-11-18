/** The product's name, which is a placeholder. Everything that shows it reads
 *  it from here; the second word is the one drawn in the accent. */
export const BRAND = { first: "Food", second: "Finder" } as const;

export const BRAND_NAME = `${BRAND.first} ${BRAND.second}`;

export const TAGLINE = "Where each city's food subreddit actually eats.";
