'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { Pitcher, Season } from '@/lib/types'

interface Props {
  season: Season
  selectedPitcher: Pitcher | null
  onPitcherChange: (p: Pitcher | null) => void
}

export function PitcherFilter({ season, selectedPitcher, onPitcherChange }: Props) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Pitcher[]>([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const fetchPitchers = useCallback(async (q: string) => {
    if (q.length < 2) { setResults([]); return }
    setLoading(true)
    try {
      const res = await fetch(`/api/pitchers?q=${encodeURIComponent(q)}&season=${season}`)
      const data = await res.json()
      setResults(data)
      setOpen(true)
    } finally {
      setLoading(false)
    }
  }, [season])

  useEffect(() => {
    const t = setTimeout(() => fetchPitchers(query), 200)
    return () => clearTimeout(t)
  }, [query, fetchPitchers])

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (
        dropdownRef.current && !dropdownRef.current.contains(e.target as Node) &&
        inputRef.current && !inputRef.current.contains(e.target as Node)
      ) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  function selectPitcher(p: Pitcher) {
    onPitcherChange(p)
    setQuery('')
    setOpen(false)
  }

  function clear() {
    onPitcherChange(null)
    setQuery('')
    setResults([])
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <span className="text-xs font-semibold text-[#888] uppercase tracking-widest">Pitcher</span>

      <div className="relative">
        <div className="flex items-center gap-2 bg-white border border-[#d0cbc3] rounded-lg px-3 py-1.5 min-w-[220px]">
          {selectedPitcher ? (
            <span className="text-sm text-[#1a1a1a] font-medium flex-1">{selectedPitcher.name}</span>
          ) : (
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onFocus={() => results.length > 0 && setOpen(true)}
              placeholder="Search pitcher…"
              className="bg-transparent text-sm text-[#1a1a1a] placeholder-[#aaa] outline-none flex-1 w-full"
            />
          )}
          <svg className="w-4 h-4 text-[#aaa] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z" />
          </svg>
        </div>

        {open && results.length > 0 && !selectedPitcher && (
          <div
            ref={dropdownRef}
            className="absolute top-full mt-1 left-0 w-full bg-white border border-[#d0cbc3] rounded-lg shadow-lg z-50 overflow-hidden"
          >
            {loading && <div className="px-3 py-2 text-xs text-[#999]">Loading…</div>}
            {results.map((p) => (
              <button
                key={p.mlbam_id}
                onMouseDown={() => selectPitcher(p)}
                className="w-full text-left px-3 py-2 text-sm text-[#1a1a1a] hover:bg-[#f5f2ed] flex items-center justify-between gap-2 transition-colors"
              >
                <span className="font-medium">{p.name}</span>
                {p.team && <span className="text-xs text-[#999]">{p.team}</span>}
              </button>
            ))}
          </div>
        )}
      </div>

      {selectedPitcher && (
        <button
          onClick={clear}
          className="text-sm text-[#999] hover:text-[#1a1a1a] flex items-center gap-1 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
          Clear
        </button>
      )}
    </div>
  )
}
