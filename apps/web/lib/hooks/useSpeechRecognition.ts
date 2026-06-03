"use client"
import { useCallback, useEffect, useRef, useState } from "react"

// Loose typing for the SpeechRecognition globals — the TS DOM lib omits them.
type Recognition = {
  lang: string
  continuous: boolean
  interimResults: boolean
  onresult:
    | ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void)
    | null
  onend: (() => void) | null
  onerror: ((e: { error: string }) => void) | null
  start(): void
  stop(): void
}
type RecognitionCtor = new () => Recognition

function getRecognitionCtor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null
  const w = window as unknown as {
    SpeechRecognition?: RecognitionCtor
    webkitSpeechRecognition?: RecognitionCtor
  }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

type Options = {
  // Called on each interim/final result with the prefix + concatenated
  // transcript. The prefix is captured once at start() time.
  onTranscript: (combined: string) => void
  lang?: string
}

export type UseSpeechRecognition = {
  supportsMic: boolean
  listening: boolean
  // `prefix` is the textarea's current value at toggle-on time; new transcripts
  // are appended to it so the user doesn't lose what they had typed.
  toggle: (prefix: string) => void
}

export function useSpeechRecognition({
  onTranscript,
  lang = "ja-JP",
}: Options): UseSpeechRecognition {
  const [supportsMic, setSupportsMic] = useState(false)
  const [listening, setListening] = useState(false)
  const recRef = useRef<Recognition | null>(null)
  const prefixRef = useRef("")
  const mountedRef = useRef(true)
  // Keep the latest onTranscript without re-binding rec.onresult.
  const callbackRef = useRef(onTranscript)
  callbackRef.current = onTranscript

  useEffect(() => {
    setSupportsMic(getRecognitionCtor() !== null)
    return () => {
      mountedRef.current = false
      recRef.current?.stop()
    }
  }, [])

  const toggle = useCallback(
    (prefix: string) => {
      if (listening) {
        recRef.current?.stop()
        return
      }
      const Ctor = getRecognitionCtor()
      if (!Ctor) return
      const rec = new Ctor()
      rec.lang = lang
      rec.continuous = true
      rec.interimResults = true
      prefixRef.current = prefix
      rec.onresult = (e) => {
        let transcript = ""
        for (let i = 0; i < e.results.length; i++) {
          transcript += e.results[i][0].transcript
        }
        const p = prefixRef.current
        const sep = p && !/\s$/.test(p) ? " " : ""
        callbackRef.current(p + sep + transcript)
      }
      const stop = () => {
        if (mountedRef.current) setListening(false)
        recRef.current = null
        prefixRef.current = ""
      }
      rec.onend = stop
      rec.onerror = stop
      rec.start()
      recRef.current = rec
      setListening(true)
    },
    [lang, listening],
  )

  return { supportsMic, listening, toggle }
}
