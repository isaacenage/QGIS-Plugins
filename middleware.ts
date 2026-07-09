// Basic-auth gate for the private review desk at /approvals.
//
// Credentials come from APPROVALS_USER / APPROVALS_PASSWORD (set in
// .env.local and the Vercel project env). Fails closed: if they are not
// configured, the route is unavailable rather than open.

import { NextRequest, NextResponse } from "next/server";

export const config = { matcher: "/approvals/:path*" };

export function middleware(request: NextRequest) {
  const user = process.env.APPROVALS_USER;
  const password = process.env.APPROVALS_PASSWORD;
  if (!user || !password) {
    return new NextResponse(
      "The review desk is not configured. Set APPROVALS_USER and APPROVALS_PASSWORD.",
      { status: 503 }
    );
  }

  const header = request.headers.get("authorization") ?? "";
  if (header.startsWith("Basic ")) {
    try {
      const decoded = atob(header.slice(6));
      const separator = decoded.indexOf(":");
      const givenUser = decoded.slice(0, separator);
      const givenPassword = decoded.slice(separator + 1);
      if (separator > 0 && givenUser === user && givenPassword === password) {
        return NextResponse.next();
      }
    } catch {
      // fall through to the 401
    }
  }

  return new NextResponse("Authentication required.", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Approvals", charset="UTF-8"' },
  });
}
