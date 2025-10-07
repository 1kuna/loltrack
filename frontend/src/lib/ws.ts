export function connectLive(onMessage: (data: any) => void): WebSocket {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const url = `${proto}://${location.host}/ws/live`
  const ws = new WebSocket(url)
  ws.onmessage = (ev) => {
    try { onMessage(JSON.parse(ev.data)) } catch {}
  }
  return ws
}

