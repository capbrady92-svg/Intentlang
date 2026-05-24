// expenses.il — Expense tracking core
domain expenses:

model Category:
  id (uuid, pk)
  name (str, required)
  icon (str, optional)
  color (str, optional)
  owner: @users/User!

model Expense:
  id (uuid, pk)
  amount (int, required)
  description (str, required)
  date (date, required)
  category -> Category
  owner: @users/User!
  receipt_url (str, optional)
  notes (str, optional)
  tags (list, optional)

model Budget:
  id (uuid, pk)
  category -> Category
  owner: @users/User!
  amount (int, required)
  period (str, default "monthly")
  start_date (date, required)

feature Categories:
  route GET /categories:
    action: fetch Categories for current user
    returns: Category[]

  route POST /categories:
    input: name, icon?, color?
    action: create Category for current user
    returns: Category

  route DELETE /categories/:id:
    action: delete Category if no Expenses reference it
    error: if has expenses -> 409 "Category has expenses"

feature Expenses:
  route GET /expenses:
    input: from_date?, to_date?, category_id?, limit? (default 50), offset?
    action: fetch Expenses for current user, filter by params
    returns: { expenses: Expense[], total, has_more }

  route POST /expenses:
    input: amount (int, required), description, date, category_id, receipt_url?, notes?, tags?
    action: create Expense for current user
    returns: Expense

  route PUT /expenses/:id:
    input: amount?, description?, date?, category_id?, notes?, tags?
    action: update Expense owned by current user
    returns: Expense
    error: if not found or not owner -> 404

  route DELETE /expenses/:id:
    action: delete Expense
    error: if not found or not owner -> 404

feature Budgets:
  route GET /budgets:
    action: fetch Budgets with current spend for current user
    returns: { budget: Budget, spent: int, remaining: int, percent: float }[]

  route POST /budgets:
    input: category_id, amount, period?, start_date
    action: create Budget
    returns: Budget

rules:
  - amounts are always in cents (integer)
  - date filters are inclusive on both ends
  - deleting a category with expenses is forbidden
  - users can only read/write their own expenses and categories
