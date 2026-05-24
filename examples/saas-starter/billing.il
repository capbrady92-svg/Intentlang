// billing.il — Stripe billing, subscriptions, usage
domain billing:

model Subscription:
  id (uuid, pk)
  org: @orgs/Org!
  stripe_customer_id (str, required, unique)
  stripe_subscription_id (str, optional, unique)
  plan (str, required)
  status (str, default "trialing")
  current_period_end (datetime, optional)
  cancel_at_period_end (bool, default false)

model Invoice:
  id (uuid, pk)
  org: @orgs/Org!
  stripe_invoice_id (str, required, unique)
  amount_cents (int, required)
  currency (str, default "usd")
  status (str, required)
  pdf_url (str, optional)
  paid_at (datetime, optional)

feature Plans:
  route GET /billing/plans:
    auth: public
    action: return plan definitions with features and pricing
    returns: { id, name, price_monthly, price_yearly, features, limits }[]

  route GET /orgs/:slug/billing:
    guard: role = owner or admin
    action: fetch Subscription with current Invoice list
    returns: { subscription: Subscription, invoices: Invoice[] }

feature Checkout:
  route POST /orgs/:slug/billing/checkout:
    guard: role = owner
    input: plan, interval (monthly|yearly)
    action: create or retrieve Stripe customer, create checkout session
    returns: { checkout_url }

  route POST /orgs/:slug/billing/portal:
    guard: role = owner
    action: create Stripe billing portal session
    returns: { portal_url }

  route POST /orgs/:slug/billing/cancel:
    guard: role = owner
    action: set cancel_at_period_end = true on Stripe subscription
    returns: { cancels_at }

feature Webhooks:
  route POST /webhooks/stripe:
    auth: stripe_signature
    action: handle Stripe events
    events:
      - checkout.session.completed -> activate subscription
      - customer.subscription.updated -> sync plan and status
      - customer.subscription.deleted -> downgrade to free
      - invoice.payment_succeeded -> record Invoice
      - invoice.payment_failed -> email owner, set status=past_due

  @level: mid
  config WebhookIdempotency:
    strategy: store processed stripe_event_ids in postgres
    on_duplicate: return 200 immediately
    reason: Stripe may deliver webhooks more than once

rules:
  - only org owners can manage billing
  - webhook endpoint verifies Stripe signature before processing
  - failed payments trigger email notification, not immediate suspension
  - all billing amounts in cents
  - free plan has no Stripe subscription record
