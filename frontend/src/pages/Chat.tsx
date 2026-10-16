import ChatPanel from '../components/ChatPanel'

export default function Chat() {
  return (
    <section className="mx-auto flex h-[calc(100dvh-8rem)] max-w-3xl flex-col md:h-[calc(100dvh-4rem)]">
      <h1 className="text-2xl font-semibold tracking-tight">Chat with Khushi</h1>
      <p className="mt-1 mb-4 text-sm text-zinc-500">
        Ask about your assignments, open apps, search the web, or play music.
      </p>
      <div className="min-h-0 flex-1">
        <ChatPanel />
      </div>
    </section>
  )
}
