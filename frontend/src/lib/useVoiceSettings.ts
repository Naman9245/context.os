import { useEffect, useState } from 'react'
import {
  loadVoiceSettings,
  onVoiceSettings,
  saveVoiceSettings,
  type VoiceSettings,
} from './voice'

/** Voice preferences shared live between the chat and Settings. */
export function useVoiceSettings(): [VoiceSettings, (patch: Partial<VoiceSettings>) => void] {
  const [settings, setSettings] = useState(loadVoiceSettings)
  useEffect(() => onVoiceSettings(setSettings), [])
  const update = (patch: Partial<VoiceSettings>) =>
    saveVoiceSettings({ ...loadVoiceSettings(), ...patch })
  return [settings, update]
}
