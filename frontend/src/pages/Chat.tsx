import ChatPanel from '../components/ChatPanel'

export default function Chat() {
  return (
    <section className="mx-auto flex h-[calc(100dvh-8rem)] max-w-3xl flex-col md:h-[calc(100dvh-4rem)]">
      <h1 className="font-display text-4xl leading-none font-extrabold tracking-tight sm:text-5xl">
        Chat with Khushi
      </h1>
      <p className="mt-3 mb-5 text-stone-500">
        Ask about your assignments, open apps, search the web, or play music.
      </p>
      <div className="min-h-0 flex-1">
        <ChatPanel />
      </div>
    </section>
  )
}
