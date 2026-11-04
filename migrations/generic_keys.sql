-- ===========================================================================
-- Identity decisions for short, generic keys. Applied by hand (psql -f), then
-- the scoring layer is refreshed (refresh.py, or POST /api/admin/refresh).
--
-- A short key such as "joes" or "rays" is a fragment of several longer names,
-- and the city's list often licenses an unrelated shop under exactly that
-- fragment (JOE'S is an Italian place in Queens, SOPHIE'S sells bottled
-- drinks), so the exact match quietly gives the fragment a wrong official
-- record and a board row of its own. Each row below was decided by reading a
-- sample of the key's mentions over the last twelve months; the notes say
-- what the sample showed.
--
-- Three kinds of decision:
--   * a fragment that, read in context, nearly always means one place is
--     merged into that place's key;
--   * a fragment that means several places is pinned to itself and listed in
--     excluded_entities, so its mentions stay in the database but no board
--     ranks a blend of different restaurants;
--   * a short key that really is one restaurant ("The Modern", "The Grill",
--     "Craft", "King", "Supper") is left alone, which is why there is no
--     general rule here: being contained in longer names does not make a key
--     ambiguous.
--
-- Safe to re-run: every row is an upsert.
-- ===========================================================================

begin;

insert into alias_overrides (entity_key, resolved_key, note) values
  -- Fragments of one place.
  ('joes',                         'joes pizza',                'generic key 2026-11: sampled mentions are Joe''s Pizza (pizza/slice in ~90%); a few mean Joe''s Shanghai'),
  ('cote',                         'cote korean steakhouse',    'generic key 2026-11: Cote the Korean steakhouse, now on the city list'),
  ('cote steakhouse',              'cote korean steakhouse',    'generic key 2026-11: same restaurant as cote'),
  ('cote flatiron',                'cote korean steakhouse',    'generic key 2026-11: same restaurant as cote'),
  ('mamas',                        'mamas too',                 'generic key 2026-11: pizza threads, Mama''s Too; MAMA''S on the city list is a Latin American place'),
  ('mamas too philly cheesesteak', 'mamas too',                 'generic key 2026-11: a dish at Mama''s Too, extracted as a name'),
  ('mamas too pizzeria',           'mamas too',                 'generic key 2026-11: spelling'),
  ('mamas toos',                   'mamas too',                 'generic key 2026-11: spelling'),
  ('ramirez',                      'taqueria ramirez',          'generic key 2026-11: Greenpoint/CDMX tacos, Taqueria Ramirez; a few may mean Carnitas Ramirez'),
  ('sophies',                      'sophies cuban cuisine',     'generic key 2026-11: Cuban food; SOPHIE''S on the city list sells bottled drinks'),
  ('electric',                     'electric burrito',          'generic key 2026-11: burrito threads, Electric Burrito'),
  ('absolute',                     'absolute bagels',           'generic key 2026-11: bagel threads, Absolute Bagels'),
  ('absolute bagel',               'absolute bagels',           'generic key 2026-11: spelling'),
  ('una',                          'una pizza napoletana',      'generic key 2026-11: Neapolitan pizza threads, Una Pizza Napoletana'),
  ('una pizza',                    'una pizza napoletana',      'generic key 2026-11: short form'),
  ('una pizza napolitana',         'una pizza napoletana',      'generic key 2026-11: spelling'),
  ('charles',                      'charles pan fried chicken', 'generic key 2026-11: fried chicken in Harlem; rarely 4 Charles'),
  ('sip',                          'sip guzzle',                'generic key 2026-11: Sip & Guzzle (its upstairs bar is called Sip)'),
  -- Union Square Cafe is licensed together with Daily Provisions next door,
  -- so merging it into that combined name labelled one restaurant as two.
  -- Daily Provisions keeps its own key; Union Square Cafe stands as itself.
  ('union square cafe',            'union square cafe',         'generic key 2026-11: not the combined licence UNION SQUARE CAFE/ DAILY PROVISIONS'),
  ('union sq cafe',                'union square cafe',         'generic key 2026-11: spelling'),
  ('usc',                          'union square cafe',         'generic key 2026-11: nickname'),
  ('usq',                          'union square cafe',         'generic key 2026-11: nickname'),
  -- Fragments of several places: pinned apart, and excluded below.
  ('blue ribbon',                  'blue ribbon',               'generic key 2026-11: ambiguous, Blue Ribbon Sushi / Brasserie / Fried Chicken'),
  ('rays',                         'rays',                      'generic key 2026-11: ambiguous, Ray''s Candy Store / Ray''s Pizza / Ray''s bar'),
  ('angelina',                     'angelina',                  'generic key 2026-11: ambiguous, Angelina Paris / Angelina Bakery'),
  ('frankies',                     'frankies',                  'generic key 2026-11: ambiguous, Frankies 457 / Frankie''s on Arthur Ave / others'),
  ('davids',                       'davids',                    'generic key 2026-11: ambiguous, David''s Bagels / David''s Brisket House'),
  ('empire',                       'empire',                    'generic key 2026-11: ambiguous, Empire Cake / Empire Steak House'),
  ('best',                         'best',                      'generic key 2026-11: ambiguous, Best Pizza / Best Bagel')
on conflict (entity_key) do update
  set resolved_key = excluded.resolved_key,
      note         = excluded.note;

-- Kept off the board, keyed on the resolved key like every other row here.
-- The note says why, so these are not mistaken for "not a restaurant".
insert into excluded_entities (entity_key, note) values
  ('blue ribbon', 'ambiguous: several restaurants share this name'),
  ('rays',        'ambiguous: several restaurants share this name'),
  ('angelina',    'ambiguous: several restaurants share this name'),
  ('frankies',    'ambiguous: several restaurants share this name'),
  ('davids',      'ambiguous: several restaurants share this name'),
  ('empire',      'ambiguous: several restaurants share this name'),
  ('best',        'ambiguous: several restaurants share this name')
on conflict (entity_key) do update
  set note = excluded.note;

commit;
