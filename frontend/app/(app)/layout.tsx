import { AppShell } from "@/components/shell";
import { Providers } from "@/app/providers";
import { RequireSession } from "@/components/session";
import { BalancePrivacyProvider } from "@/components/balance-privacy";
import { FinancialContextProvider } from "@/components/context";

/**
 * Layout for every authenticated route.
 *
 * The nesting order is the point. AppShell sits *outside* RequireSession, so
 * the navigation renders immediately and the auth check only gates the page
 * body. Previously each page carried this stack itself, below the route
 * boundary, so React tore the whole thing down on every navigation and the
 * bottom bar vanished for the length of an /auth/me round trip.
 *
 * Living in a layout, this subtree persists across navigations: the session is
 * fetched once per load rather than once per page, and the shell never
 * unmounts.
 *
 * `(app)` is a route group — it shares this layout without appearing in any
 * URL, which is what keeps /login and /register outside it.
 */
export default function AuthenticatedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <Providers>
      <FinancialContextProvider>
        <BalancePrivacyProvider>
          <AppShell>
            <RequireSession>{children}</RequireSession>
          </AppShell>
        </BalancePrivacyProvider>
      </FinancialContextProvider>
    </Providers>
  );
}
