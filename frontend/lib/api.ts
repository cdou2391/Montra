/**
 * Thin API client.
 *
 * Sessions are HTTP-only cookies, so every request forwards credentials and no
 * token is ever read or stored by JavaScript (API spec section 5).
 */

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export type ApiError = {
  code: string;
  message: string;
  details?: { field: string; message: string }[] | null;
  request_id?: string;
};

export class MontraApiError extends Error {
  code: string;
  details?: { field: string; message: string }[] | null;
  status: number;

  constructor(status: number, error: ApiError) {
    super(error.message);
    this.status = status;
    this.code = error.code;
    this.details = error.details;
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new MontraApiError(
      response.status,
      body?.error ?? { code: "UNKNOWN", message: "Something went wrong." },
    );
  }

  return body as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown, headers?: Record<string, string>) =>
    request<T>(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
      headers,
    }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

// ------------------------------------------------------------------ resources

export type Money = { amount: string; currency: string };

export type CreditCardFields = {
  credit_limit: string | null;
  statement_balance: string | null;
  statement_closing_day: number | null;
  payment_due_day: number | null;
  minimum_payment: string | null;
  interest_rate: string | null;
  expiry_month: number | null;
  expiry_year: number | null;
};

export type Account = {
  id: string;
  name: string;
  account_type: string;
  account_nature: "ASSET" | "LIABILITY";
  currency: string;
  balance: string;
  opening_balance: string;
  masked_identifier: string | null;
  visibility: string;
  ownership_type: string;
  status: string;
  can_edit: boolean;
  can_transact: boolean;
  credit_card: CreditCardFields | null;
  is_favorite: boolean;
};

export type CardSummary = {
  account_id: string;
  currency: string;
  outstanding_balance: string;
  available_credit: string | null;
  credit_limit: string | null;
  utilization_percentage: string | null;
  utilization_band: "NORMAL" | "NEUTRAL" | "WARNING" | "HIGH" | null;
  statement_balance: string | null;
  minimum_payment: string | null;
  payment_due_date: string | null;
  statement_closing_day: number | null;
  interest_rate: string | null;
};

export type ReconciliationPreview = {
  current_balance: string;
  actual_balance: string;
  difference: string;
  direction: "INCREASE" | "DECREASE" | null;
  currency: string;
};

export type Transaction = {
  id: string;
  account: { id: string; name: string } | null;
  transaction_type: "INCOME" | "EXPENSE" | "TRANSFER" | "ADJUSTMENT";
  amount: string;
  currency: string;
  direction: "INCREASE" | "DECREASE";
  occurred_at: string;
  status: string;
  description: string | null;
  merchant: string | null;
  category: { id: string; name: string } | null;
  transfer_id: string | null;
};

export type Category = {
  id: string;
  name: string;
  category_type: "INCOME" | "EXPENSE";
};

export type CurrentUser = {
  id: string;
  email: string;
  display_name: string | null;
  base_currency: string;
  timezone: string;
  active_family: { id: string; name: string; role: string } | null;
};


export type PlannedTransaction = {
  id: string;
  planned_type: "INCOME" | "EXPENSE";
  amount: string;
  currency: string;
  expected_at: string;
  occurrence_date: string;
  description: string;
  notes: string | null;
  status: "UPCOMING" | "DUE" | "COMPLETED" | "MISSED" | "CANCELLED" | "SKIPPED";
  source: "ONE_TIME" | "RECURRING";
  bucket: "OVERDUE" | "TODAY" | "TOMORROW" | "THIS_WEEK" | "LATER";
  account: { id: string; name: string } | null;
  category: { id: string; name: string } | null;
  recurring_rule_id: string | null;
  completed_transaction_id: string | null;
};

export type RecurringRule = {
  id: string;
  name: string;
  planned_type: "INCOME" | "EXPENSE";
  amount: string;
  currency: string;
  frequency: "DAILY" | "WEEKLY" | "MONTHLY" | "QUARTERLY" | "YEARLY";
  interval_value: number;
  start_date: string;
  end_date: string | null;
  next_occurrence_date: string | null;
  status: "ACTIVE" | "PAUSED" | "ENDED";
  reminder_days_before: number | null;
  account_id: string;
  category_id: string | null;
};

export type ResetPreview = {
  accounts: number;
  transactions: number;
  transfers: number;
  loans: number;
  loan_payments: number;
  planned_transactions: number;
  recurring_rules: number;
  notifications: number;
  custom_categories: number;
};

export type BackupSummary = {
  accounts: number;
  transactions: number;
  transfers: number;
  loans: number;
  loan_payments: number;
  planned_transactions: number;
  recurring_rules: number;
  categories: number;
};

export type BackupFile = {
  montra_backup_version: number;
  exported_at: string;
  user?: { email?: string; display_name?: string | null };
  [key: string]: unknown;
};

export type Preferences = {
  hide_balances: boolean;
  persist_balance_privacy: boolean;
  default_context: "PERSONAL" | "FAMILY";
  default_reminder_days: number | null;
  notifications_enabled: boolean;
  favorite_account_id: string | null;
};

export type Loan = {
  id: string;
  name: string;
  direction: "PAYABLE" | "RECEIVABLE";
  counterparty: string | null;
  currency: string;
  original_principal: string;
  opening_outstanding_principal: string;
  outstanding_principal: string;
  principal_paid: string;
  percent_paid: string | null;
  interest_rate: string | null;
  start_date: string;
  end_date: string | null;
  expected_payment_amount: string | null;
  payment_frequency: string | null;
  next_payment_date: string | null;
  status: "ACTIVE" | "SETTLED" | "ARCHIVED";
  visibility: string;
  notes: string | null;
};

export type LoanPayment = {
  id: string;
  loan_id: string;
  account: { id: string; name: string } | null;
  payment_date: string;
  total_amount: string;
  principal_amount: string;
  interest_amount: string;
  fee_amount: string;
  notes: string | null;
  created_at: string;
};

export type AppNotification = {
  id: string;
  notification_type: string;
  title: string;
  body: string;
  related_entity_type: string | null;
  related_entity_id: string | null;
  read_at: string | null;
  created_at: string;
};

type Envelope<T> = { data: T };
type Collection<T> = { data: T[]; pagination: { limit: number; next_cursor: string | null } };

export const montra = {
  me: () => api.get<Envelope<CurrentUser>>("/auth/me").then((r) => r.data),
  login: (email: string, password: string) =>
    api.post<Envelope<{ user: CurrentUser }>>("/auth/login", { email, password }),
  register: (payload: {
    email: string;
    password: string;
    display_name?: string;
    base_currency: string;
    timezone: string;
  }) => api.post<Envelope<CurrentUser>>("/auth/register", payload),
  logout: () => api.post<void>("/auth/logout"),

  accounts: () => api.get<Collection<Account>>("/accounts").then((r) => r.data),
  account: (id: string) => api.get<Envelope<Account>>(`/accounts/${id}`).then((r) => r.data),
  createAccount: (payload: Record<string, unknown>) =>
    api.post<Envelope<Account>>("/accounts", payload).then((r) => r.data),
  archiveAccount: (id: string) => api.post<void>(`/accounts/${id}/archive`),
  setFavoriteAccount: (id: string) =>
    api.post<Envelope<Account>>(`/accounts/${id}/favorite`),
  clearFavoriteAccount: (id: string) =>
    api.delete<Envelope<Account>>(`/accounts/${id}/favorite`),

  transactions: (query = "") =>
    api.get<Collection<Transaction>>(`/transactions${query}`),
  createTransaction: (payload: Record<string, unknown>) =>
    api.post<Envelope<Transaction>>("/transactions", payload).then((r) => r.data),
  deleteTransaction: (id: string) => api.delete<void>(`/transactions/${id}`),

  cardSummary: (id: string) =>
    api.get<Envelope<CardSummary>>(`/credit-cards/${id}/summary`).then((r) => r.data),
  payCard: (id: string, payload: Record<string, unknown>, idempotencyKey: string) =>
    api.post<Envelope<unknown>>(`/credit-cards/${id}/payments`, payload, {
      "Idempotency-Key": idempotencyKey,
    }),
  topUpPrepaid: (id: string, payload: Record<string, unknown>, idempotencyKey: string) =>
    api.post<Envelope<unknown>>(`/prepaid-cards/${id}/top-ups`, payload, {
      "Idempotency-Key": idempotencyKey,
    }),

  reconciliationPreview: (id: string, actualBalance: string) =>
    api
      .get<Envelope<ReconciliationPreview>>(
        `/accounts/${id}/reconciliation-preview?actual_balance=${encodeURIComponent(
          actualBalance,
        )}`,
      )
      .then((r) => r.data),
  reconcile: (id: string, payload: Record<string, unknown>) =>
    api.post<Envelope<unknown>>(`/accounts/${id}/balance-adjustments`, payload),

  createTransfer: (payload: Record<string, unknown>, idempotencyKey: string) =>
    api.post<Envelope<unknown>>("/transfers", payload, {
      "Idempotency-Key": idempotencyKey,
    }),

  // ---------------------------------------------------------------- loans
  loans: (query = "") =>
    api.get<Collection<Loan>>(`/loans${query}`).then((r) => r.data),
  loan: (id: string) => api.get<Envelope<Loan>>(`/loans/${id}`).then((r) => r.data),
  createLoan: (payload: Record<string, unknown>) =>
    api.post<Envelope<Loan>>("/loans", payload).then((r) => r.data),
  archiveLoan: (id: string) => api.post<Envelope<Loan>>(`/loans/${id}/archive`),
  loanPayments: (id: string) =>
    api.get<Collection<LoanPayment>>(`/loans/${id}/payments`).then((r) => r.data),
  recordLoanPayment: (id: string, payload: Record<string, unknown>, key: string) =>
    api.post<Envelope<LoanPayment & { loan: Loan }>>(`/loans/${id}/payments`, payload, {
      "Idempotency-Key": key,
    }),

  // The download is a plain link, not fetch: the browser should save the file
  // rather than the app holding it in memory.
  backupUrl: () => `${BASE_URL}/profile/backup`,
  restoreBackup: (password: string, backup: unknown) =>
    api.post<Envelope<{ restored: BackupSummary }>>("/profile/restore", {
      password,
      backup,
    }),

  resetPreview: () =>
    api.get<Envelope<ResetPreview>>("/profile/reset-preview").then((r) => r.data),
  resetProfile: (password: string) =>
    api.post<Envelope<{ deleted: ResetPreview }>>("/profile/reset", { password }),

  preferences: () =>
    api.get<Envelope<Preferences>>("/preferences").then((r) => r.data),
  updatePreferences: (payload: Partial<Preferences>) =>
    api.patch<Envelope<Preferences>>("/preferences", payload).then((r) => r.data),

  // ------------------------------------------------------------- planning
  planned: (query = "") =>
    api.get<Collection<PlannedTransaction>>(`/planned-transactions${query}`).then((r) => r.data),
  createPlanned: (payload: Record<string, unknown>) =>
    api.post<Envelope<PlannedTransaction>>("/planned-transactions", payload).then((r) => r.data),
  completePlanned: (id: string, payload: Record<string, unknown>, key: string) =>
    api.post<Envelope<PlannedTransaction>>(
      `/planned-transactions/${id}/complete`,
      payload,
      { "Idempotency-Key": key },
    ),
  reschedulePlanned: (id: string, payload: Record<string, unknown>) =>
    api.post<Envelope<PlannedTransaction>>(`/planned-transactions/${id}/reschedule`, payload),
  cancelPlanned: (id: string) =>
    api.post<Envelope<PlannedTransaction>>(`/planned-transactions/${id}/cancel`),
  skipPlanned: (id: string) =>
    api.post<Envelope<PlannedTransaction>>(`/planned-transactions/${id}/skip`),

  recurringRules: () =>
    api.get<Collection<RecurringRule>>("/recurring-rules").then((r) => r.data),
  createRule: (payload: Record<string, unknown>) =>
    api.post<Envelope<RecurringRule>>("/recurring-rules", payload).then((r) => r.data),
  ruleAction: (id: string, action: "pause" | "resume" | "end") =>
    api.post<Envelope<RecurringRule>>(`/recurring-rules/${id}/${action}`),

  notifications: (unreadOnly = false) =>
    api.get<Collection<AppNotification> & { has_unread: boolean }>(
      `/notifications${unreadOnly ? "?unread_only=true" : ""}`,
    ),
  markNotificationRead: (id: string) => api.post<void>(`/notifications/${id}/read`),
  markAllNotificationsRead: () => api.post<void>("/notifications/read-all"),

  categories: (type?: "INCOME" | "EXPENSE") =>
    api
      .get<Collection<Category>>(`/categories${type ? `?type=${type}` : ""}`)
      .then((r) => r.data),
};
