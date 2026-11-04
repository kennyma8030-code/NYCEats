-- ===========================================================================
-- Identity decisions for short, generic keys. Applied by hand (psql -f), then
-- the scoring layer is refreshed (refresh.py, or POST /api/admin/refresh).
--
-- A short key such as "joes" or "rays" is a fragment of several longer names,
-- and the city's list often licenses an unrelated shop under exactly that
-- fragment (JOE'S is an Italian place in Queens, SOPHIE'S sells bottled
-- drinks), so the exact match quietly gives the fragment a wrong official
-- record and a board row of its own. Each row below was decided by reading the
-- key's mentions; the notes say what they showed, with the measured share of
-- the other place where one was at risk.
--
-- Three kinds of decision:
--   * a fragment that, read in context, nearly always means one place is
--     merged into that place's key, along with the spellings of that place
--     found beside it;
--   * a fragment that means several places is pinned to itself and listed in
--     excluded_entities, so its mentions stay in the database but no board
--     ranks a blend of different restaurants;
--   * a short key that really is one restaurant ("The Modern", "The Grill",
--     "Craft", "King", "Supper") is left alone, which is why there is no
--     general rule here: being contained in longer names does not make a key
--     ambiguous.
--
-- Safe to re-run: every row is an upsert, and a re-decided row gets a new
-- created_at like one written through the admin endpoint
-- (queries.upsert_alias), so it sorts as new in the admin list.
-- ===========================================================================

begin;

insert into alias_overrides (entity_key, resolved_key, note) values
  -- Joe's Pizza. Shanghai, dumpling, XLB or soup dumpling appear in the
  -- comment or thread title of 17 of the 829 live "joes" mentions (2.1%);
  -- pizza, slice or pie in 664 (80%).
  ('joes',                         'joes pizza',                'generic key 2026-11: Joe''s Pizza; Shanghai/dumpling/XLB cues in 17 of 829 live mentions (2.1%), pizza/slice/pie in 80%'),
  ('joe pizza',                    'joes pizza',                'generic key 2026-11: spelling'),
  ('joes pizza carmine',           'joes pizza',                'generic key 2026-11: a location of Joe''s Pizza'),
  ('joes pizza broadway',          'joes pizza',                'generic key 2026-11: a location of Joe''s Pizza'),
  ('joes pizza union square',      'joes pizza',                'generic key 2026-11: a location of Joe''s Pizza'),
  -- Cote, the Korean steakhouse, now on the city list. "cote 550" already
  -- resolves there by an October override.
  ('cote',                         'cote korean steakhouse',    'generic key 2026-11: Cote the Korean steakhouse, now on the city list'),
  ('cote steakhouse',              'cote korean steakhouse',    'generic key 2026-11: same restaurant as cote'),
  ('cote flatiron',                'cote korean steakhouse',    'generic key 2026-11: the original Cote'),
  ('cote korean steak house',      'cote korean steakhouse',    'generic key 2026-11: spelling'),
  ('cote kbbq',                    'cote korean steakhouse',    'generic key 2026-11: spelling'),
  ('cote steak',                   'cote korean steakhouse',    'generic key 2026-11: spelling'),
  ('cote cote 550',                'cote korean steakhouse',    'generic key 2026-11: "Cote/Cote 550", both locations'),
  ('cote 50',                      'cote korean steakhouse',    'generic key 2026-11: typo for Cote 550'),
  -- Mama's Too.
  ('mamas',                        'mamas too',                 'generic key 2026-11: pizza threads, Mama''s Too; MAMA''S on the city list is a Latin American place'),
  ('mamas too philly cheesesteak', 'mamas too',                 'generic key 2026-11: a dish at Mama''s Too, extracted as a name'),
  ('mama toos cheesesteak',        'mamas too',                 'generic key 2026-11: a dish at Mama''s Too, extracted as a name'),
  ('mama too',                     'mamas too',                 'generic key 2026-11: spelling; was pinned apart from "empanada mama to go", which this still is'),
  ('mamas too pizzeria',           'mamas too',                 'generic key 2026-11: spelling'),
  ('mamas toos',                   'mamas too',                 'generic key 2026-11: spelling'),
  ('mamma toos',                   'mamas too',                 'generic key 2026-11: spelling'),
  ('mamas too wv',                 'mamas too',                 'generic key 2026-11: the West Village location'),
  -- Sophie's Cuban.
  ('sophies',                      'sophies cuban cuisine',     'generic key 2026-11: Cuban food; SOPHIE''S on the city list sells bottled drinks'),
  -- Electric Burrito.
  ('electric',                     'electric burrito',          'generic key 2026-11: burrito threads, Electric Burrito'),
  ('electric burritos',            'electric burrito',          'generic key 2026-11: spelling'),
  -- Absolute Bagels. "new absolute bagels" is left apart (see the report).
  ('absolute',                     'absolute bagels',           'generic key 2026-11: bagel threads, Absolute Bagels'),
  ('absolute bagel',               'absolute bagels',           'generic key 2026-11: spelling'),
  -- Una Pizza Napoletana.
  ('una',                          'una pizza napoletana',      'generic key 2026-11: Neapolitan pizza threads, Una Pizza Napoletana'),
  ('una pizza',                    'una pizza napoletana',      'generic key 2026-11: short form'),
  ('una napoletana',               'una pizza napoletana',      'generic key 2026-11: short form'),
  ('una pizza napolitana',         'una pizza napoletana',      'generic key 2026-11: spelling'),
  ('una pizza napolitano',         'una pizza napoletana',      'generic key 2026-11: spelling'),
  ('una pizza neopolitana',        'una pizza napoletana',      'generic key 2026-11: spelling'),
  ('una pizza nepolitana',         'una pizza napoletana',      'generic key 2026-11: spelling'),
  ('una pizza napoeitana',         'una pizza napoletana',      'generic key 2026-11: spelling'),
  -- Charles Pan-Fried Chicken. Of all 36 live "charles" mentions, 28 sit
  -- beside fried chicken, Harlem or waffles; read by hand, 2 of the other 8
  -- mean 4 Charles (5.6%) and 1 a closed West Village French place.
  ('charles',                      'charles pan fried chicken', 'generic key 2026-11: Charles Pan-Fried Chicken; 2 of 36 live mentions mean 4 Charles (5.6%), 1 a closed French place'),
  ('charles pan',                  'charles pan fried chicken', 'generic key 2026-11: short form'),
  ('charles fried chicken',        'charles pan fried chicken', 'generic key 2026-11: short form'),
  ('charles pan friend chicken',   'charles pan fried chicken', 'generic key 2026-11: spelling'),
  -- Sip & Guzzle: Sip is its upstairs bar and Guzzle the one downstairs.
  ('sip',                          'sip guzzle',                'generic key 2026-11: Sip, the upstairs bar of Sip & Guzzle'),
  ('guzzle',                       'sip guzzle',                'generic key 2026-11: Guzzle, the downstairs bar of Sip & Guzzle'),
  ('sip at sip guzzle',            'sip guzzle',                'generic key 2026-11: spelling'),
  -- Fragments of several places: pinned apart, and excluded below.
  ('ramirez',                      'ramirez',                   'generic key 2026-11: ambiguous, Taqueria Ramirez / Carnitas Ramirez (about a quarter of contexts mean Carnitas)'),
  ('blue ribbon',                  'blue ribbon',               'generic key 2026-11: ambiguous, Blue Ribbon Sushi / Brasserie / Fried Chicken'),
  ('rays',                         'rays',                      'generic key 2026-11: ambiguous, Ray''s Candy Store / Ray''s Pizza / Ray''s bar'),
  ('angelina',                     'angelina',                  'generic key 2026-11: ambiguous, Angelina Paris / Angelina Bakery'),
  ('frankies',                     'frankies',                  'generic key 2026-11: ambiguous, Frankies 457 / Frankie''s on Arthur Ave / others'),
  ('davids',                       'davids',                    'generic key 2026-11: ambiguous, David''s Bagels / David''s Brisket House'),
  ('empire',                       'empire',                    'generic key 2026-11: ambiguous, Empire Cake / Empire Steak House'),
  ('best',                         'best',                      'generic key 2026-11: ambiguous, Best Pizza / Best Bagel')
on conflict (entity_key) do update
  set resolved_key = excluded.resolved_key,
      note         = excluded.note,
      created_at   = now();

-- Kept off the board, keyed on the resolved key like every other row here.
-- The note says why, so these are not mistaken for "not a restaurant".
insert into excluded_entities (entity_key, note) values
  ('ramirez',     'ambiguous: several restaurants share this name'),
  ('blue ribbon', 'ambiguous: several restaurants share this name'),
  ('rays',        'ambiguous: several restaurants share this name'),
  ('angelina',    'ambiguous: several restaurants share this name'),
  ('frankies',    'ambiguous: several restaurants share this name'),
  ('davids',      'ambiguous: several restaurants share this name'),
  ('empire',      'ambiguous: several restaurants share this name'),
  ('best',        'ambiguous: several restaurants share this name')
on conflict (entity_key) do update
  set note       = excluded.note,
      created_at = now();

-- Checks, inside the same transaction, so a bad state rolls everything back.
-- entity_alias does not chain overrides: a typed key goes straight to its
-- override's resolved_key. So a merge target that is itself re-pointed would
-- strand every mention merged into it, and an excluded key that some override
-- or exact match moves elsewhere would leave the board ranking it anyway.
-- These look at the whole tables, not just the rows above, so a later edit
-- that broke one of these decisions also fails here on a re-run.
do $$
declare
  bad text;
begin
  select string_agg(x.entity_key, ', ' order by x.entity_key) into bad
  from excluded_entities x
  where x.note like 'ambiguous:%'
    and not exists (select 1 from alias_overrides o
                    where o.entity_key = x.entity_key and o.resolved_key = x.entity_key);
  if bad is not null then
    raise exception 'excluded as ambiguous but not pinned to itself: %', bad;
  end if;

  select string_agg(distinct o.resolved_key || ' -> ' || t.resolved_key, ', ') into bad
  from alias_overrides o
  join alias_overrides t on t.entity_key = o.resolved_key
  where o.resolved_key <> o.entity_key
    and t.resolved_key <> t.entity_key;
  if bad is not null then
    raise exception 'merge target re-pointed by another override (overrides do not chain): %', bad;
  end if;
end $$;

commit;
