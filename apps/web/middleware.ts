const RAZORPAY_WEBHOOK_UPSTREAM =
  'https://recourse-razorpay-recovery-api.onrender.com/api/v1/webhooks/razorpay'

export const config = {
  matcher: '/webhooks/razorpay',
}

export default async function middleware(request: Request): Promise<Response> {
  if (request.method !== 'POST') {
    return new Response('Method Not Allowed', { status: 405, headers: { Allow: 'POST' } })
  }

  // Signature verification depends on the untouched provider bytes. Forward only
  // the required headers and the exact ArrayBuffer; never parse or reserialize JSON.
  const headers = new Headers()
  for (const name of ['content-type', 'x-razorpay-signature', 'x-razorpay-event-id']) {
    const value = request.headers.get(name)
    if (value) headers.set(name, value)
  }

  try {
    const upstream = await fetch(RAZORPAY_WEBHOOK_UPSTREAM, {
      method: 'POST',
      headers,
      body: await request.arrayBuffer(),
    })
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { 'content-type': upstream.headers.get('content-type') ?? 'application/json' },
    })
  } catch {
    return Response.json({ error: { code: 'WEBHOOK_UPSTREAM_UNAVAILABLE' } }, { status: 503 })
  }
}
