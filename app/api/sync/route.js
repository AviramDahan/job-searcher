import { jsonResponse, handleSyncAction } from "../../../lib/sync-api.js";

export const dynamic = "force-dynamic";

export function OPTIONS() {
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Max-Age": "86400",
    },
  });
}

export async function GET() {
  return jsonResponse(await handleSyncAction({ action: "listUpdates" }, process.env));
}

export async function POST(request) {
  const params = await request.json().catch(() => ({}));
  return jsonResponse(await handleSyncAction(params, process.env));
}
