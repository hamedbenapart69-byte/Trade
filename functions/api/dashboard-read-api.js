const ALLOWED_ORIGIN = "https://crypto-market-intelligence.bool.so";

function corsHeaders(origin) {
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Accept, Content-Type",
    "Vary": "Origin",
    "Cache-Control": "no-store",
  };
}

function jsonResponse(status, body, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...headers },
  });
}

/**
 * Server-side proxy for the Activepieces Dashboard Read API.\n * Fail closed until both server-side environment variables are configured.
 *
 * Required Cloudflare Pages environment variables:
 * - ACTIVEPIECES_DASHBOARD_WEBHOOK_URL: exact published /sync webhook URL
 * - ACTIVEPIECES_DASHBOARD_API_KEY: Header Auth value stored in Activepieces
 *
 * Never expose either value to browser code or commit them to Git.
 */
export async function handleDashboardRequest(request, env, fetchImpl = fetch) {
  const origin = request.headers.get("Origin") || "";
  if (origin !== ALLOWED_ORIGIN) {
    return jsonResponse(403, { error: "ORIGIN_NOT_ALLOWED" });
  }

  const headers = corsHeaders(origin);
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers });
  }
  if (request.method !== "GET") {
    return jsonResponse(405, { error: "METHOD_NOT_ALLOWED" }, {
      ...headers,
      Allow: "GET, OPTIONS",
    });
  }

  const webhookUrl = env?.ACTIVEPIECES_DASHBOARD_WEBHOOK_URL;
  const apiKey = env?.ACTIVEPIECES_DASHBOARD_API_KEY;
  if (typeof webhookUrl !== "string" || !webhookUrl.startsWith("https://")
      || typeof apiKey !== "string" || apiKey.length < 32) {
    return jsonResponse(503, { error: "SERVER_PROXY_NOT_CONFIGURED" }, headers);
  }

  let upstream;
  try {
    upstream = await fetchImpl(webhookUrl, {
      method: "GET",
      headers: {
        Accept: "application/json",
        "X-Api-Key": apiKey,
      },
      cache: "no-store",
      redirect: "error",
    });
  } catch {
    return jsonResponse(502, { error: "UPSTREAM_UNAVAILABLE" }, headers);
  }

  const body = await upstream.text();
  const contentType = upstream.headers.get("Content-Type") || "application/json";
  return new Response(body, {
    status: upstream.status,
    headers: {
      ...headers,
      "Content-Type": contentType,
    },
  });
}

export async function onRequest(context) {
  return handleDashboardRequest(context.request, context.env);
}
