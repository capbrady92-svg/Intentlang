// content.il — Content domain consuming the identity interface
//
// Shows cross-domain references to the published identity interface.
// In a real multi-project setup, replace @identity with an import:
//   imports:
//     identity: github.com/myorg/myapp/intent@^2.1

domain content:
  description: "Posts, comments, and reactions"

model Post:
  id (uuid, pk)
  author: @identity/User!
  title (str, required)
  slug (str, required, unique, indexed)
  body (str, required)
  status (str, default "draft")
  published_at (datetime, optional)
  tags (list, optional)

  @level: low
  search_vector (tsvector, indexed)

model Comment:
  id (uuid, pk)
  post -> Post
  author: @identity/User!
  body (str, required)
  parent -> Comment
  deleted (bool, default false)

model Reaction:
  id (uuid, pk)
  post -> Post
  user: @identity/User!
  emoji (str, required)

feature Posts:
  route GET /posts:
    auth: public
    input: status? (published), tag?, limit? (default 20), cursor?
    action: fetch published Posts, cursor-paginated
    returns: { posts: Post[], next_cursor }

  route GET /posts/:slug:
    auth: public
    action: fetch Post with author Profile and comment count
    returns: { post: Post, author: Profile, comment_count: int }
    error: if not found -> 404

  route POST /posts:
    input: title, body, tags?, status? (default draft)
    action: create Post, auto-generate slug from title
    returns: Post

  route PUT /posts/:slug:
    input: title?, body?, tags?, status?
    action: update Post owned by current user
    returns: Post
    error: if not author -> 403

  route DELETE /posts/:slug:
    action: delete Post
    error: if not author -> 403

feature Comments:
  route GET /posts/:slug/comments:
    auth: public
    input: limit? (default 50)
    action: fetch top-level Comments with nested replies (max 2 levels)
    returns: Comment[]

  route POST /posts/:slug/comments:
    input: body, parent_id?
    action: create Comment
    returns: Comment

  route DELETE /comments/:id:
    action: soft delete Comment (set deleted=true, body="[deleted]")
    error: if not author -> 403

feature Reactions:
  route POST /posts/:slug/reactions:
    input: emoji
    action: toggle Reaction for current user (add if absent, remove if present)
    returns: { emoji, count, reacted: bool }

  @level: mid
  feature Search:
    route GET /posts/search:
      auth: public
      input: q (str, required), tag?
      action: full-text search Posts using search_vector, rank by relevance
      algorithm: postgres tsvector + tsquery with ts_rank_cd
      returns: { posts: Post[], total }

rules:
  - only post authors can edit or delete their own posts
  - deleted comments show body as [deleted] to others
  - reactions are toggled not stacked
  - published posts cannot be moved back to draft
  - slug auto-generated from title, unique enforced with numeric suffix if collision
