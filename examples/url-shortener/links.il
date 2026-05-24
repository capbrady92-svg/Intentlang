// links.il — Core link shortening domain
domain links:
  description: "URL shortening, redirects, click tracking"

model Link:
  id (uuid, pk)
  slug (str, required, unique, indexed)
  original_url (str, required)
  title (str, optional)
  expires_at (datetime, optional)
  active (bool, default true)
  click_count (int, default 0)

model Click:
  id (uuid, pk)
  link -> Link
  ip (str, optional)
  user_agent (str, optional)
  referer (str, optional)
  country (str, optional)

feature Shorten:
  route POST /links:
    input: original_url (str, required), slug?, title?, expires_at?
    action: validate url, generate slug if not provided (6 chars alphanumeric), create Link
    returns: { slug, short_url, original_url, expires_at }
    error: if slug taken -> 409 "Slug already in use"
    error: if invalid url -> 400 "Invalid URL"

  route GET /links:
    action: fetch all Links for api_key owner
    returns: Link[]

  route GET /links/:slug:
    action: fetch Link by slug
    returns: Link
    error: if not found -> 404

  route DELETE /links/:slug:
    action: deactivate Link
    returns: { ok: true }

feature Redirect:
  route GET /:slug:
    auth: public
    action: lookup slug in redis cache, fallback to postgres, record Click, redirect
    returns: 302 redirect to original_url
    error: if not found or inactive -> 404
    error: if expired -> 410 "Link expired"

feature Analytics:
  route GET /links/:slug/stats:
    action: fetch Link with click_count, recent Clicks
    returns: { link, total_clicks, clicks_by_day, top_countries }

  @level: mid
  config ClickAggregation:
    strategy: write to redis queue, batch flush to postgres every 60s
    reason: avoid write amplification on hot slugs

rules:
  - slugs are lowercase alphanumeric + hyphens only
  - max slug length: 50 chars
  - max original_url length: 2048 chars
  - expired links return 410 not 404
  - click tracking is async, never blocks redirect
