import { serve } from "bun";
import { readFile } from "fs/promises";
import { extname } from "path";

const PORT = 3000;

const MIME_TYPES = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".eot": "application/vnd.ms-fontobject",
};

const server = serve({
  port: PORT,
  fetch: async (req) => {
    let url = new URL(req.url);
    let filePath = `.${url.pathname}`;
    if (filePath === "./") filePath = "./index.html";
    
    console.log(`Request: ${req.method} ${url.pathname}`);
    
    try {
      const file = await readFile(filePath);
      const ext = extname(filePath);
      const contentType = MIME_TYPES[ext] || "application/octet-stream";
      
      return new Response(file, {
        headers: { "Content-Type": contentType },
      });
    } catch (err) {
      console.log(`Error: ${err.message}`);
      return new Response("File not found", { status: 404 });
    }
  },
});

console.log(`Server running on http://localhost:${PORT}`);

