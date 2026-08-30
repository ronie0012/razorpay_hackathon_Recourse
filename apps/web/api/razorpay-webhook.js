export const config = {
  api: { bodyParser: false },
}

const UPSTREAM =
  'https://recourse-razorpay-recovery-api.onrender.com/api/v1/webhooks/razorpay'

export default async function handler(request, response) {
  if (request.method !== 'POST') {
    response.setHeader('Allow', 'POST')
    return response.status(405).send('Method Not Allowed')
  }

  const chunks = []
  for await (const chunk of request) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk))
  }
  const rawBody = Buffer.concat(chunks)

  const headers = {}
  for (const name of ['content-type', 'x-razorpay-signature', 'x-razorpay-event-id']) {
    const value = request.headers[name]
    if (typeof value === 'string') headers[name] = value
  }

  try {
    const upstream = await fetch(UPSTREAM, { method: 'POST', headers, body: rawBody })
    const body = await upstream.arrayBuffer()
    response.status(upstream.status)
    response.setHeader('content-type', upstream.headers.get('content-type') ?? 'application/json')
    return response.send(Buffer.from(body))
  } catch {
    return response.status(503).json({ error: { code: 'WEBHOOK_UPSTREAM_UNAVAILABLE' } })
  }
}
