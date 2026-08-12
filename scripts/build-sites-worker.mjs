import { copyFileSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

const distDir = "dist";
const serverDir = join(distDir, "server");
const hostingTarget = join(distDir, ".openai", "hosting.json");
const syncTarget = join(serverDir, "sync-api.js");
const workerTarget = join(serverDir, "index.js");

function readText(path) {
  return readFileSync(path, "utf8");
}

function writeText(path, content) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, content, "utf8");
}

rmSync(distDir, { recursive: true, force: true });
mkdirSync(serverDir, { recursive: true });
mkdirSync(dirname(hostingTarget), { recursive: true });

copyFileSync(join(".openai", "hosting.json"), hostingTarget);
copyFileSync(join("lib", "sync-api.js"), syncTarget);

const files = {
  "/": {
    contentType: "text/html; charset=utf-8",
    cacheControl: "no-store",
    body: readText(join("docs", "index.html")),
  },
  "/index.html": {
    contentType: "text/html; charset=utf-8",
    cacheControl: "no-store",
    body: readText(join("docs", "index.html")),
  },
  "/assets/pages.css": {
    contentType: "text/css; charset=utf-8",
    cacheControl: "public, max-age=300",
    body: readText(join("docs", "assets", "pages.css")),
  },
  "/assets/pages.js": {
    contentType: "text/javascript; charset=utf-8",
    cacheControl: "public, max-age=300",
    body: readText(join("docs", "assets", "pages.js")),
  },
  "/assets/job-data.json": {
    contentType: "application/json; charset=utf-8",
    cacheControl: "no-store",
    body: readText(join("docs", "assets", "job-data.json")),
  },
  "/assets/dashboard-config.json": {
    contentType: "application/json; charset=utf-8",
    cacheControl: "no-store",
    body: JSON.stringify(
      {
        updatesEndpoint: "/api/sync",
        transport: "cors",
      },
      null,
      2
    ),
  },
};

const workerSource = `import { jsonResponse, handleSyncAction } from "./sync-api.js";

const STATIC_FILES = ${JSON.stringify(files, null, 2)};

function staticResponse(pathname) {
  const file = STATIC_FILES[pathname] || (pathname.endsWith("/") ? STATIC_FILES["/"] : null);
  if (!file) {
    return null;
  }

  return new Response(file.body, {
    headers: {
      "Content-Type": file.contentType,
      "Cache-Control": file.cacheControl,
    },
  });
}

function methodNotAllowed() {
  return new Response("Method Not Allowed", {
    status: 405,
    headers: {
      Allow: "GET, POST, OPTIONS",
    },
  });
}

async function syncJsonResponse(callback) {
  try {
    return jsonResponse(await callback());
  } catch (error) {
    return jsonResponse(
      {
        ok: false,
        error: error?.message || "sync_error",
      },
      503
    );
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/api/sync") {
      if (request.method === "OPTIONS") {
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

      if (request.method === "GET") {
        const params = Object.fromEntries(url.searchParams.entries());
        return syncJsonResponse(() => handleSyncAction({ action: params.action || "listUpdates", ...params }, env));
      }

      if (request.method === "POST") {
        const params = await request.json().catch(() => ({}));
        return syncJsonResponse(() => handleSyncAction(params, env));
      }

      return methodNotAllowed();
    }

    if (url.pathname === "/favicon.ico") {
      return new Response(null, { status: 204 });
    }

    return staticResponse(url.pathname) || new Response("Not Found", { status: 404 });
  },
};
`;

writeText(workerTarget, workerSource);
