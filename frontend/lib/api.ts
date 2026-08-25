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
  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

// ------------------------------------------------------------------ resources

export type Money = { amount: string; currency: string };

export type ExchangeRate = {
  id: string;
  base_currency: string;
  quote_currency: string;
  rate: string;
  as_of: string;
  source: string;
  automatic: boolean;
};

export type CurrenciesInUse = {
  base_currency: string;
  currencies: string[];
  missing: string[];
};

export type CardExpiry = {
  expires_on: string;
  days_remaining: number;
  status: "VALID" | "EXPIRING" | "EXPIRED";
  advice: string;
};

export type CreditCardFields = {
  available_credit: string | null;
  utilization_percentage: string | null;
  utilization_band: "NORMAL" | "NEUTRAL" | "WARNING" | "HIGH" | null;
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
  /** The balance restated in the viewer's base currency; null with no rate. */
  balance_in_base: string | null;
  base_currency: string;
  opening_balance: string;
  masked_identifier: string | null;
  visibility: string;
  ownership_type: string;
  status: string;
  can_edit: boolean;
  expiry: CardExpiry | null;
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
  expiry_month: number | null;
  expiry_year: number | null;
  expiry: CardExpiry | null;
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
  fee_for_transaction_id?: string | null;
  notes?: string | null;
  reference?: string | null;
  created_at?: string;
};

export type Attachment = {
  id: string;
  transaction_id: string | null;
  file_name: string;
  mime_type: string;
  file_size: number;
  uploaded: boolean;
  created_at: string;
};

type UploadTicket = Attachment & {
  upload: { url: string; method: string; headers: Record<string, string> };
};

export type Category = {
  id: string;
  name: string;
  category_type: "INCOME" | "EXPENSE";
};

export type FamilyMember = {
  user_id: string;
  display_name: string | null;
  email: string;
  role: "OWNER" | "ADULT" | "MEMBER";
  status: "ACTIVE" | "LEFT" | "REMOVED";
  joined_at: string;
};

export type AuditEvent = {
  id: string;
  event_type: string;
  entity_type: string;
  entity_id: string | null;
  actor: { id: string; display_name: string | null } | null;
  metadata: Record<string, string> | null;
  created_at: string;
};

export type Family = {
  id: string;
  name: string;
  base_currency: string;
  status: string;
  role: "OWNER" | "ADULT" | "MEMBER";
  members: FamilyMember[];
};

export type Invitation = {
  id: string;
  invitee_email: string | null;
  proposed_role: string;
  status: string;
  expires_at: string;
  created_at: string;
  token?: string;
};

export type Position = {
  assets: string;
  liabilities: string;
  net_worth: string;
  account_count: number;
  loan_count: number;
};

export type NetWorth = Position & {
  context: "personal" | "family";
  currency: string;
  shared?: Position | null;
};

export type Dashboard = {
  context: "personal" | "family";
  currency: string;
  in_family: boolean;
  net_worth: NetWorth | null;
  month: {
    month: string;
    income: string;
    expense: string;
    saved: string;
    savings_rate: string | null;
  } | null;
  upcoming: PlannedTransaction[];
  recent: Transaction[];
  loans?: LoanPaymentDue[];
  insights: Insight[];
};

export type ForecastPoint = { date: string; projected_balance: string };

export type ForecastWarning = {
  account_id: string;
  account_name: string;
  date: string;
  projected_balance: string;
  message: string;
};

export type Forecast = {
  context: "personal" | "family";
  period: "7d" | "30d";
  currency: string;
  starting_balance: string;
  projected_ending_balance: string;
  upcoming_income: string;
  upcoming_expenses: string;
  net_change: string;
  points: ForecastPoint[];
  warnings: ForecastWarning[];
};

export type Insight = {
  code: string;
  title: string;
  detail: string;
  tone: "positive" | "neutral" | "warning" | "negative";
  currency?: string;
  value?: string;
  account_id?: string;
  category?: string;
  count?: number;
  change_percent?: string;
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
  planned_type: "INCOME" | "EXPENSE" | "TRANSFER";
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
  destination_account: { id: string; name: string } | null;
  category: { id: string; name: string } | null;
  recurring_rule_id: string | null;
  completed_transaction_id: string | null;
  completed_transfer_id: string | null;
};

export type RecurringRule = {
  id: string;
  name: string;
  planned_type: "INCOME" | "EXPENSE" | "TRANSFER";
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
  destination_account_id: string | null;
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

export type LoanPaymentDue = {
  id: string;
  kind: "LOAN_PAYMENT";
  loan_id: string;
  direction: "PAYABLE" | "RECEIVABLE";
  description: string;
  counterparty: string | null;
  amount: string;
  currency: string;
  due_date: string;
  bucket: "OVERDUE" | "TODAY" | "TOMORROW" | "THIS_WEEK" | "LATER";
  outstanding_principal: string;
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

/** Which lens the app is looking through (API spec section 11). */
export type Context = "personal" | "family";

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

  accounts: (context: Context = "personal") =>
    api.get<Collection<Account>>(`/accounts?context=${context}`).then((r) => r.data),
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
  transaction: (id: string) =>
    api.get<Envelope<Transaction>>(`/transactions/${id}`).then((r) => r.data),
  updateTransaction: (id: string, payload: Record<string, unknown>) =>
    api.patch<Envelope<Transaction>>(`/transactions/${id}`, payload).then((r) => r.data),
  deleteTransaction: (id: string) => api.delete<void>(`/transactions/${id}`),

  attachments: (transactionId: string) =>
    api
      .get<Collection<Attachment>>(`/transactions/${transactionId}/attachments`)
      .then((r) => r.data),
  /**
   * Three steps, because the file never passes through the API: ask for a
   * link, PUT the bytes straight to storage, then tell the API it landed.
   */
  uploadAttachment: async (transactionId: string, file: File): Promise<Attachment> => {
    const ticket = await api
      .post<Envelope<UploadTicket>>(`/transactions/${transactionId}/attachments`, {
        file_name: file.name,
        mime_type: file.type,
        file_size: file.size,
      })
      .then((r) => r.data);

    const response = await fetch(ticket.upload.url, {
      method: ticket.upload.method,
      headers: ticket.upload.headers,
      body: file,
    });
    if (!response.ok) throw new Error("The upload did not complete.");

    return api
      .post<Envelope<Attachment>>(`/attachments/${ticket.id}/complete`, {})
      .then((r) => r.data);
  },
  /** Same three steps, but the receipt belongs to a transfer's outgoing side. */
  uploadTransferAttachment: async (transferId: string, file: File): Promise<Attachment> => {
    const ticket = await api
      .post<Envelope<UploadTicket>>(`/transfers/${transferId}/attachments`, {
        file_name: file.name,
        mime_type: file.type,
        file_size: file.size,
      })
      .then((r) => r.data);

    const response = await fetch(ticket.upload.url, {
      method: ticket.upload.method,
      headers: ticket.upload.headers,
      body: file,
    });
    if (!response.ok) throw new Error("The upload did not complete.");

    return api
      .post<Envelope<Attachment>>(`/attachments/${ticket.id}/complete`, {})
      .then((r) => r.data);
  },
  attachmentUrl: (id: string) =>
    api
      .get<Envelope<{ url: string; expires_in: number }>>(`/attachments/${id}/download`)
      .then((r) => r.data.url),
  deleteAttachment: (id: string) => api.delete<void>(`/attachments/${id}`),

  cardSummary: (id: string) =>
    api.get<Envelope<CardSummary>>(`/credit-cards/${id}/summary`).then((r) => r.data),
  updateAccount: (id: string, payload: Record<string, unknown>) =>
    api.patch<Envelope<Account>>(`/accounts/${id}`, payload).then((r) => r.data),
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
    api
      .post<Envelope<{ id: string }>>("/transfers", payload, {
        "Idempotency-Key": idempotencyKey,
      })
      .then((r) => r.data),

  // ------------------------------------------------------------- household
  familyActivity: (familyId: string) =>
    api
      .get<Collection<AuditEvent>>(`/families/${familyId}/activity`)
      .then((r) => r.data),
  currentFamily: () =>
    api.get<Envelope<Family | null>>("/families/current").then((r) => r.data),
  createFamily: (name: string, base_currency: string) =>
    api.post<Envelope<Family>>("/families", { name, base_currency }).then((r) => r.data),
  invite: (familyId: string, invitee_email: string | null, proposed_role = "ADULT") =>
    api
      .post<Envelope<Invitation>>(`/families/${familyId}/invitations`, {
        invitee_email,
        proposed_role,
      })
      .then((r) => r.data),
  invitations: (familyId: string) =>
    api.get<Collection<Invitation>>(`/families/${familyId}/invitations`).then((r) => r.data),
  cancelInvitation: (familyId: string, invitationId: string) =>
    api.delete<Envelope<Invitation>>(`/families/${familyId}/invitations/${invitationId}`),
  acceptInvitation: (token: string) =>
    api.post<Envelope<Family>>(`/family-invitations/${token}/accept`).then((r) => r.data),
  removeMember: (familyId: string, userId: string) =>
    api.delete<Envelope<unknown>>(`/families/${familyId}/members/${userId}`),
  leaveFamily: (familyId: string) =>
    api.post<Envelope<unknown>>(`/families/${familyId}/leave`),
  setAccountVisibility: (accountId: string, visibility: string) =>
    api
      .patch<Envelope<Account>>(`/accounts/${accountId}/visibility`, { visibility })
      .then((r) => r.data),

  forecast: (context: Context = "personal", period: "7d" | "30d" = "30d") =>
    api
      .get<Envelope<Forecast>>(`/forecasts/cash-flow?context=${context}&period=${period}`)
      .then((r) => r.data),
  exchangeRates: () =>
    api.get<Collection<ExchangeRate>>("/exchange-rates").then((r) => r.data),
  currenciesInUse: () =>
    api
      .get<Envelope<CurrenciesInUse>>("/exchange-rates/currencies-in-use")
      .then((r) => r.data),
  setExchangeRate: (payload: Record<string, unknown>) =>
    api.put<Envelope<ExchangeRate>>("/exchange-rates", payload).then((r) => r.data),
  deleteExchangeRate: (id: string) => api.delete<void>(`/exchange-rates/${id}`),
  refreshExchangeRates: () =>
    api.post<Collection<ExchangeRate>>("/exchange-rates/refresh").then((r) => r.data),
  insights: (context: Context = "personal") =>
    api.get<Collection<Insight>>(`/insights?context=${context}`).then((r) => r.data),

  // ------------------------------------------------------------- reporting
  dashboard: (context: Context = "personal") =>
    api.get<Envelope<Dashboard>>(`/dashboard?context=${context}`).then((r) => r.data),
  netWorth: (context: Context = "personal") =>
    api.get<Envelope<NetWorth>>(`/reports/net-worth?context=${context}`).then((r) => r.data),

  // ---------------------------------------------------------------- loans
  loans: (query = "") =>
    api.get<Collection<Loan>>(`/loans${query}`).then((r) => r.data),
  loan: (id: string) => api.get<Envelope<Loan>>(`/loans/${id}`).then((r) => r.data),
  createLoan: (payload: Record<string, unknown>) =>
    api.post<Envelope<Loan>>("/loans", payload).then((r) => r.data),
  archiveLoan: (id: string) => api.post<Envelope<Loan>>(`/loans/${id}/archive`),
  upcomingLoanPayments: () =>
    api.get<Collection<LoanPaymentDue>>("/loans/upcoming").then((r) => r.data),
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
