// Keeps a connection to ContextOS on this laptop and opens links in Khushi's tabs.
// Only talks to 127.0.0.1:8000. ContextOS only accepts this extension's ID.

import { openFirstResult, openInKhushiTab } from './khushi.js'

const SERVER = 'ws://127.0.0.1:8000/api/browser/ws'
let socket = null

function connect() {
  if (socket && socket.readyState <= WebSocket.OPEN) return // connecting or connected
  try {
    socket = new WebSocket(SERVER)
  } catch {
    return // ContextOS isn't running; the alarm below tries again
  }
  socket.onopen = () =>
    socket.send(JSON.stringify({ type: 'hello', version: chrome.runtime.getManifest().version }))
  socket.onmessage = async (event) => {
    let msg
    try {
      msg = JSON.parse(event.data)
    } catch {
      return
    }
    if (msg.type === 'ping') {
      socket.send(JSON.stringify({ type: 'pong' })) // also keeps this worker awake
      return
    }
    let run = null
    if (msg.type === 'open' && /^https?:\/\//.test(msg.url)) {
      run = async () => ({ ok: true, ...(await openInKhushiTab(chrome, msg.url, msg.site)) })
    } else if (msg.type === 'open_first') {
      run = () => openFirstResult(chrome, msg.site)
    }
    if (run) {
      try {
        socket.send(JSON.stringify({ type: 'result', id: msg.id, ...(await run()) }))
      } catch (e) {
        socket.send(JSON.stringify({ type: 'result', id: msg.id, ok: false, error: String(e) }))
      }
    }
  }
  socket.onclose = () => {
    socket = null
  }
}

// Reconnect when Chrome starts, when the extension is (re)loaded, and every
// minute in case ContextOS was started after Chrome.
chrome.runtime.onStartup.addListener(connect)
chrome.runtime.onInstalled.addListener(connect)
chrome.alarms.create('khushi-reconnect', { periodInMinutes: 1 })
chrome.alarms.onAlarm.addListener((alarm) => alarm.name === 'khushi-reconnect' && connect())
connect()
