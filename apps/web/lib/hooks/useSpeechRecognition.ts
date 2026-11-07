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
  // Ends the session now and drops anything it still delivers. Call on send:
  // a continuous session re-sends its whole transcript with every result, so
  // one landing after the box was cleared would write the sent text back.
  stop: () => void
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
    // React Strict Mode (and any unmount/remount cycle) runs the cleanup
    // between mounts; without re-arming mountedRef here it stays false on
    // the second mount, which causes the rec.onend stop callback to skip
    // setListening(false) and leave the mic UI stuck in the listening state.
    mountedRef.current = true
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
      // Events from a session that is no longer current (stopped, or replaced
      // by a newer one) are ignored.
      rec.onresult = (e) => {
        if (recRef.current !== rec) return
        let transcript = ""
        for (let i = 0; i < e.results.length; i++) {
          transcript += e.results[i][0].transcript
        }
        const p = prefixRef.current
        const sep = p && !/\s$/.test(p) ? " " : ""
        callbackRef.current(p + sep + transcript)
      }
      const ended = () => {
        if (recRef.current !== rec) return
        if (mountedRef.current) setListening(false)
        recRef.current = null
        prefixRef.current = ""
      }
      rec.onend = ended
      rec.onerror = ended
      // Registered before start() so a result delivered during start() counts
      // as the current session's.
      recRef.current = rec
      rec.start()
      setListening(true)
    },
    [lang, listening],
  )

  const stop = useCallback(() => {
    const rec = recRef.current
    if (!rec) return
    // Detach first so the session's trailing results and onend are ignored.
    recRef.current = null
    prefixRef.current = ""
    setListening(false)
    rec.stop()
  }, [])

  return { supportsMic, listening, toggle, stop }
}
