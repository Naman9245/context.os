import { useEffect, useState } from 'react'
import { Button, Card, inputClass } from './ui'
import { useVoiceSettings } from '../lib/useVoiceSettings'
import {
  LISTEN_LANGUAGES,
  canListen,
  canSpeak,
  getVoices,
  pickVoice,
  speak,
} from '../lib/voice'

export default function VoiceSettings() {
  const [voice, setVoice] = useVoiceSettings()
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([])

  useEffect(() => {
    getVoices().then(setVoices)
  }, [])

  const english = voices.filter((v) => v.lang.toLowerCase().startsWith('en'))
  const options = english.length ? english : voices
  const current = pickVoice(voices, voice.voiceName)

  return (
    <section>
      <h2 className="font-semibold">Khushi's voice</h2>
      <p className="mb-3 text-sm text-stone-500">
        She can read her replies aloud, and you can talk to her with the mic button in the chat.
      </p>
      <Card>
        {!canSpeak() ? (
          <p className="text-sm text-stone-500">This browser can't speak. Try Google Chrome.</p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex items-center gap-2 text-sm sm:col-span-2">
              <input
                type="checkbox"
                checked={voice.speak}
                onChange={(e) => setVoice({ speak: e.target.checked })}
              />
              Read Khushi's replies aloud
            </label>
            <label className="text-xs text-stone-500">
              Voice
              <select
                className={inputClass}
                value={current?.name ?? ''}
                onChange={(e) => setVoice({ voiceName: e.target.value || null })}
              >
                {options.map((v) => (
                  <option key={v.name} value={v.name}>
                    {v.name} ({v.lang}){v.localService ? '' : ' - online'}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs text-stone-500">
              Speed: {voice.rate.toFixed(1)}×
              <input
                type="range"
                min={0.7}
                max={1.4}
                step={0.1}
                value={voice.rate}
                onChange={(e) => setVoice({ rate: Number(e.target.value) })}
                className="mt-2 w-full"
              />
            </label>
            <div className="sm:col-span-2">
              <Button
                onClick={() =>
                  speak("Hi! I'm Khushi. I'll keep track of your assignments for you.", voice)
                }
              >
                Test voice
              </Button>
            </div>
          </div>
        )}
        <div className="mt-4 border-t border-stone-100 pt-4 dark:border-stone-800">
          {canListen() ? (
            <label className="block text-xs text-stone-500 sm:w-1/2">
              Language you speak in
              <select
                className={inputClass}
                value={voice.listenLang}
                onChange={(e) => setVoice({ listenLang: e.target.value })}
              >
                {LISTEN_LANGUAGES.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.label}
                  </option>
                ))}
              </select>
              <span className="mt-1 block">
                Talking to Khushi uses Chrome's speech service, which sends your voice to Google
                to turn it into text.
              </span>
            </label>
          ) : (
            <p className="text-sm text-stone-500">
              Talking to Khushi needs Google Chrome. You can still type to her here.
            </p>
          )}
        </div>
      </Card>
    </section>
  )
}
