// Run with: node --test browser-extension/
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { firstResult, openFirstResult, openInKhushiTab, siteOf } from './khushi.js'

const cases = JSON.parse(readFileSync(new URL('./site-cases.json', import.meta.url)))

test('siteOf matches ContextOS for every shared case', () => {
  for (const [url, site] of cases) assert.equal(siteOf(url), site, url)
})

/** A pretend Chrome with tabs, windows and session storage. `open` holds its tabs. */
function fakeChrome() {
  const open = new Map()
  const store = {}
  const calls = []
  let nextId = 1
  const fake = {
    open,
    calls,
    storage: {
      session: {
        get: async (key) => (key in store ? { [key]: store[key] } : {}),
        set: async (obj) => Object.assign(store, obj),
      },
    },
    tabs: {
      get: async (id) => {
        if (!open.has(id)) throw new Error(`No tab with id: ${id}`)
        return { ...open.get(id) }
      },
      create: async ({ url }) => {
        const tab = { id: nextId++, windowId: 1, url, status: 'complete' }
        open.set(tab.id, tab)
        calls.push(['create', url])
        return { ...tab }
      },
      update: async (id, { url }) => {
        open.get(id).url = url
        calls.push(['update', id, url])
        return { ...open.get(id) }
      },
    },
    windows: { update: async () => {} },
    // What the results page lists: set `found` to a result, or leave it null for none.
    found: null,
    scripting: {
      executeScript: async () => [{ result: fake.found }],
    },
  }
  return fake
}

test('the second YouTube request reuses Khushi\'s YouTube tab', async () => {
  const chrome = fakeChrome()
  const first = await openInKhushiTab(chrome, 'https://www.youtube.com', 'youtube.com')
  const second = await openInKhushiTab(chrome,
    'https://www.youtube.com/results?search_query=carryminati', 'youtube.com')
  assert.equal(first.reused, false)
  assert.deepEqual(second, { reused: true, tabId: first.tabId })
  assert.deepEqual(chrome.calls.map((c) => c[0]), ['create', 'update'])
})

test('each site gets its own Khushi tab', async () => {
  const chrome = fakeChrome()
  const yt = await openInKhushiTab(chrome, 'https://www.youtube.com', 'youtube.com')
  const wiki = await openInKhushiTab(chrome, 'https://en.wikipedia.org/wiki/X', 'wikipedia.org')
  assert.notEqual(yt.tabId, wiki.tabId)
})

test('a tab you took to another site is yours: Khushi opens a new one', async () => {
  const chrome = fakeChrome()
  const first = await openInKhushiTab(chrome, 'https://www.youtube.com', 'youtube.com')
  chrome.open.get(first.tabId).url = 'https://mail.google.com/' // you went to Gmail in it
  const again = await openInKhushiTab(chrome, 'https://www.youtube.com/results?q=x', 'youtube.com')
  assert.equal(again.reused, false)
  assert.notEqual(again.tabId, first.tabId)
  assert.equal(chrome.open.get(first.tabId).url, 'https://mail.google.com/') // left alone
})

test('a closed Khushi tab is replaced by a new one', async () => {
  const chrome = fakeChrome()
  const first = await openInKhushiTab(chrome, 'https://www.youtube.com', 'youtube.com')
  chrome.open.delete(first.tabId) // you closed it
  const again = await openInKhushiTab(chrome, 'https://www.youtube.com', 'youtube.com')
  assert.equal(again.reused, false)
})

test('"open it" opens the first result in Khushi\'s tab', async () => {
  const chrome = fakeChrome()
  const { tabId } = await openInKhushiTab(chrome,
    'https://www.youtube.com/results?search_query=carryminati', 'youtube.com')
  chrome.found = { url: 'https://www.youtube.com/watch?v=abc', title: 'PODCAST OF THE DECADE' }
  const result = await openFirstResult(chrome, 'youtube.com')
  assert.deepEqual(result, { ok: true, title: 'PODCAST OF THE DECADE',
                             url: 'https://www.youtube.com/watch?v=abc' })
  assert.equal(chrome.open.get(tabId).url, 'https://www.youtube.com/watch?v=abc')
})

test('"open it" never touches a tab that moved to another site', async () => {
  const chrome = fakeChrome()
  const { tabId } = await openInKhushiTab(chrome, 'https://www.youtube.com/results?q=x',
    'youtube.com')
  chrome.open.get(tabId).url = 'https://mail.google.com/'
  chrome.found = { url: 'https://www.youtube.com/watch?v=abc', title: 'x' }
  const result = await openFirstResult(chrome, 'youtube.com')
  assert.equal(result.ok, false)
  assert.equal(chrome.open.get(tabId).url, 'https://mail.google.com/')
})

test('"open it" with no Khushi tab, or no results, says so', async () => {
  const chrome = fakeChrome()
  assert.equal((await openFirstResult(chrome, 'youtube.com')).ok, false)
  await openInKhushiTab(chrome, 'https://www.youtube.com/results?q=x', 'youtube.com')
  chrome.found = null
  assert.deepEqual(await openFirstResult(chrome, 'youtube.com', { tries: 3, every: 0 }),
    { ok: false, error: 'no results on the page' })
})

/** A pretend page: `selectors` maps a CSS selector to the element it finds. */
function withPage(selectors, path, fn) {
  globalThis.document = { querySelector: (sel) => selectors[sel] ?? null }
  globalThis.location = { href: `https://en.wikipedia.org${path}`, pathname: path }
  try {
    return fn()
  } finally {
    delete globalThis.document
    delete globalThis.location
  }
}

test('"open it" waits for a page that is still loading', async () => {
  const chrome = fakeChrome()
  const { tabId } = await openInKhushiTab(chrome, 'https://www.youtube.com/results?q=x',
    'youtube.com')
  chrome.open.get(tabId).status = 'loading'
  chrome.found = { url: 'https://www.youtube.com/watch?v=abc', title: 'First video' }
  setTimeout(() => (chrome.open.get(tabId).status = 'complete'), 5) // loads a moment later
  const result = await openFirstResult(chrome, 'youtube.com', { tries: 50, every: 2 })
  assert.equal(result.ok, true)
  assert.equal(result.title, 'First video')
})

test('firstResult reads the first video on a YouTube results page', () => {
  const link = { href: 'https://www.youtube.com/watch?v=abc',
                 getAttribute: () => 'PODCAST  OF THE\nDECADE', textContent: '' }
  const found = withPage({ 'ytd-video-renderer a#video-title': link }, '/',
    () => firstResult('youtube.com'))
  assert.deepEqual(found, { url: 'https://www.youtube.com/watch?v=abc',
                            title: 'PODCAST OF THE DECADE' })
})

test('firstResult reads the first Google result', () => {
  const a = { href: 'https://en.wikipedia.org/wiki/Black_hole' }
  const h3 = { textContent: 'Black hole - Wikipedia', closest: () => a }
  const found = withPage({ '#rso a h3, #search a h3': h3 }, '/', () => firstResult('google.com'))
  assert.deepEqual(found, { url: a.href, title: 'Black hole - Wikipedia' })
})

test('on a Wikipedia article (no results list) "it" is the article itself', () => {
  const found = withPage({ '#firstHeading': { textContent: 'Alan Turing' } },
    '/wiki/Alan_Turing', () => firstResult('wikipedia.org'))
  assert.deepEqual(found, { url: 'https://en.wikipedia.org/wiki/Alan_Turing',
                            title: 'Alan Turing' })
})

test('firstResult finds nothing on an empty page', () => {
  assert.equal(withPage({}, '/', () => firstResult('youtube.com')), null)
})
