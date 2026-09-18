import { NextRequest, NextResponse } from "next/server";

const backendUrl = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

async function proxyToBackend(request: NextRequest) {
  const url = new URL(request.url);
  const targetUrl = `${backendUrl}${url.pathname}${url.search}`;

  // Forward headers but strip hop-by-hop / host that node fetch will set
  const headers = new Headers();
  request.headers.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (["host", "connection", "content-length"].includes(lower)) return;
    headers.set(key, value);
  });

  // Buffer body for multipart; for GET/HEAD no body
  let body: BodyInit | undefined = undefined;
  if (request.method !== "GET" && request.method !== "HEAD") {
    const buf = await request.arrayBuffer();
    if (buf.byteLength > 0) {
      body = Buffer.from(buf) as unknown as BodyInit;
    }
  }

  const backendResponse = await fetch(targetUrl, {
    method: request.method,
    headers,
    body,
    // undici requires duplex for streaming bodies; buffering makes it safe anyway
    // @ts-expect-error duplex is required for Node fetch with body
    duplex: "half",
  });

  // Clone headers, remove encoding that Next might handle
  const responseHeaders = new Headers(backendResponse.headers);
  responseHeaders.delete("content-encoding");
  responseHeaders.delete("content-length");

  // Stream body back
  return new NextResponse(backendResponse.body, {
    status: backendResponse.status,
    statusText: backendResponse.statusText,
    headers: responseHeaders,
  });
}

export async function POST(request: NextRequest) {
  return proxyToBackend(request);
}

export async function GET(request: NextRequest) {
  return proxyToBackend(request);
}

export async function PUT(request: NextRequest) {
  return proxyToBackend(request);
}

export async function DELETE(request: NextRequest) {
  return proxyToBackend(request);
}

export async function PATCH(request: NextRequest) {
  return proxyToBackend(request);
}
