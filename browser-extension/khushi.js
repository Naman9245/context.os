// Khushi's tabs: one per site, reused instead of opening a new tab every time.
// Kept free of globals (Chrome's API is passed in) so it can be tested.

const TWO_PART_SUFFIXES = new Set(['co.in', 'co.uk', 'ac.in', 'edu.in', 'org.in', 'gov.in',
  'net.in', 'res.in', 'com.au', 'co.jp'])

/** "https://en.m.wikipedia.org/wiki/X" -> "wikipedia.org". Must match ContextOS's site_of(). */
export function siteOf(url) {
  let host
  try {
    host = new URL(url).hostname.toLowerCase()
  } catch {
    return ''
  }
  if (host === 'youtu.be') return 'youtube.com'
  const parts = host.split('.')
  const keep = TWO_PART_SUFFIXES.has(parts.slice(-2).join('.')) ? 3 : 2
  return parts.slice(-keep).join('.')
}

/**
 * Open `url` in Khushi's tab for `site`, or in a new tab that becomes hers.
 * A tab is only reused while it is still on that site: if you took it somewhere
 * else, it is yours now and is left alone. Tabs you opened yourself are never used.
 */
export async function openInKhushiTab(chrome, url, site) {
  const key = `tab:${site}`
  const saved = (await chrome.storage.session.get(key))[key]
  if (saved !== undefined) {
    try {
      const tab = await chrome.tabs.get(saved)
      if (siteOf(tab.url || tab.pendingUrl || '') === site) {
        await chrome.tabs.update(tab.id, { url, active: true })
        await chrome.windows.update(tab.windowId, { focused: true })
        return { reused: true, tabId: tab.id }
      }
    } catch {
      // the tab was closed
    }
  }
  const tab = await chrome.tabs.create({ url, active: true })
  await chrome.windows.update(tab.windowId, { focused: true })
  await chrome.storage.session.set({ [key]: tab.id })
  return { reused: false, tabId: tab.id }
}

/**
 * Open the first result on Khushi's results page for `site` ("open it").
 * Only her own tab, and only while it is still on that site.
 */
export async function openFirstResult(chrome, site, { tries = 20, every = 500 } = {}) {
  const key = `tab:${site}`
  const saved = (await chrome.storage.session.get(key))[key]
  if (saved === undefined) return { ok: false, error: 'no Khushi tab for this site' }
  let tab
  let found = null
  // The page may still be loading ("search X and then open the first video"):
  // wait for it, and for the results to appear, for up to tries x every ms.
  for (let i = 0; i < tries && !found; i++) {
    if (i) await new Promise((resolve) => setTimeout(resolve, every))
    try {
      tab = await chrome.tabs.get(saved)
    } catch {
      return { ok: false, error: 'the tab was closed' }
    }
    if (siteOf(tab.url || tab.pendingUrl || '') !== site) {
      return { ok: false, error: 'the tab is on another site' }
    }
    if (tab.status !== 'complete') continue
    const [injection] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: firstResult,
      args: [site],
    })
    found = injection && injection.result
  }
  if (!found) return { ok: false, error: 'no results on the page' }
  await chrome.tabs.update(tab.id, { url: found.url, active: true })
  await chrome.windows.update(tab.windowId, { focused: true })
  return { ok: true, title: found.title, url: found.url }
}

/**
 * Runs inside the results page (Chrome copies the function there), so it may only
 * use `document` and its own arguments. Returns {url, title} or null.
 */
export function firstResult(site) {
  const clean = (text) => (text || '').replace(/\s+/g, ' ').trim().slice(0, 120)
  if (site === 'youtube.com') {
    const a = document.querySelector('ytd-video-renderer a#video-title')
    return a && a.href ? { url: a.href, title: clean(a.getAttribute('title') || a.textContent) } : null
  }
  if (site === 'google.com') {
    const h3 = document.querySelector('#rso a h3, #search a h3')
    const a = h3 && h3.closest('a')
    return a && a.href ? { url: a.href, title: clean(h3.textContent) } : null
  }
  if (site === 'wikipedia.org') {
    const a = document.querySelector('.mw-search-result-heading a')
    if (a && a.href) return { url: a.href, title: clean(a.textContent) }
    // Wikipedia jumps straight to the article when the name matches: that is "it".
    const heading = document.querySelector('#firstHeading')
    return heading && !location.pathname.includes('Special:')
      ? { url: location.href, title: clean(heading.textContent) }
      : null
  }
  return null
}
