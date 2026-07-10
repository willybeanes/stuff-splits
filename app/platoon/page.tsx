'use client'

import { useState, useEffect, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { PlatoonTable, PlatoonRow } from '@/components/PlatoonTable'
import { PitcherFilter } from '@/components/PitcherFilter'
import { Pitcher } from '@/lib/types'

const PITCH_TYPES = [
  { value: '',   label: 'All Pitches' },
  { value: 'FF', label: '4-Seam' },
  { value: 'SI', label: 'Sinker' },
  { value: 'FC', label: 'Cutter' },
  { value: 'SL', label: 'Slider' },
  { value: 'ST', label: 'Sweeper' },
  { value: 'CH', label: 'Changeup' },
  { value: 'CU', label: 'Curveball' },
  { value: 'KC', label: 'Knuckle-Curve' },
  { value: 'FS', label: 'Splitter' },
]

const SORT_DEFAULTS: Record<string, 'asc' | 'desc'> = {
  pitcher_name: 'asc',
  pitch_label:  'asc',
  stuff_gap:    'desc',
  loc_gap:      'desc',
  pitching_gap: 'desc',
}

function PlatoonContent() {
  const router = useRouter()
  const sp     = useSearchParams()

  const [pitcher,   setPitcher]   = useState<Pitcher | null>(null)
  const [pitchType, setPitchType] = useState(sp.get('pitch_type') ?? '')
  const [minN,      setMinN]      = useState(parseInt(sp.get('min_n') ?? '50'))
  const [sortCol,   setSortCol]   = useState(sp.get('sort') ?? 'stuff_gap')
  const [sortDir,   setSortDir]   = useState<'asc'|'desc'>((sp.get('dir') as 'asc'|'desc') ?? 'desc')
  const [page,      setPage]      = useState(1)
  const [rows,      setRows]      = useState<PlatoonRow[]>([])
  const [total,     setTotal]     = useState(0)
  const [loading,   setLoading]   = useState(true)
  const [error,     setError]     = useState<string | null>(null)

  // Sync URL
  useEffect(() => {
    const params = new URLSearchParams()
    if (pitchType)         params.set('pitch_type', pitchType)
    if (minN !== 50)       params.set('min_n', String(minN))
    if (sortCol !== 'stuff_gap') params.set('sort', sortCol)
    if (sortDir !== 'desc')      params.set('dir', sortDir)
    if (page !== 1)        params.set('page', String(page))
    if (pitcher)           params.set('pitcher_id', String(pitcher.mlbam_id))
    const qs = params.toString()
    router.replace(qs ? `?${qs}` : '/platoon', { scroll: false })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pitchType, minN, sortCol, sortDir, page, pitcher?.mlbam_id])

  // Fetch data
  useEffect(() => {
    let alive = true
    setLoading(true)
    const params = new URLSearchParams({
      season: '2026',
      min_n: String(minN),
      sort: sortCol,
      dir: sortDir,
      page: String(page),
    })
    if (pitchType)   params.set('pitch_type', pitchType)
    if (pitcher)     params.set('pitcher_id', String(pitcher.mlbam_id))

    fetch(`/api/platoon?${params}`)
      .then(r => r.json())
      .then(d => {
        if (!alive) return
        if (d.error) { setError(d.error); setLoading(false); return }
        setRows(d.rows); setTotal(d.total); setError(null); setLoading(false)
      })
      .catch(e => { if (alive) { setError(String(e)); setLoading(false) } })
    return () => { alive = false }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pitchType, minN, sortCol, sortDir, page, pitcher?.mlbam_id])

  function handleSort(col: string) {
    if (col === sortCol) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortCol(col)
      setSortDir(SORT_DEFAULTS[col] ?? 'desc')
    }
    setPage(1)
  }

  return (
    <main className="min-h-screen bg-[#edeae4] text-[#1a1a1a]">
      <div className="max-w-7xl mx-auto px-4 py-10 flex flex-col gap-6">

        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-black tracking-tight text-[#1a1a1a]">Platoon Splits</h1>
            <p className="text-sm text-[#666] mt-1">
              Pitch-quality model grades (Stuff+ / Loc+ / Pitching+) by batter handedness · 2026
            </p>
          </div>
        </div>

        {/* Filters */}
        <div className="bg-white border border-[#ddd8d0] rounded-2xl shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-[#ece8e1] flex flex-wrap items-center gap-4">

            {/* Pitch type pills */}
            <div className="flex flex-wrap gap-1">
              {PITCH_TYPES.map(pt => (
                <button
                  key={pt.value}
                  onClick={() => { setPitchType(pt.value); setPage(1) }}
                  className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors ${
                    pitchType === pt.value
                      ? 'bg-[#1a1a1a] text-white'
                      : 'bg-[#f0ece4] text-[#555] hover:bg-[#e8e3db]'
                  }`}
                >
                  {pt.label}
                </button>
              ))}
            </div>

            <div className="w-px h-5 bg-[#e0dbd2] hidden sm:block" />

            {/* Pitcher search */}
            <PitcherFilter
              season={2026}
              selectedPitcher={pitcher}
              onPitcherChange={p => { setPitcher(p); setPage(1) }}
            />

            <div className="w-px h-5 bg-[#e0dbd2] hidden sm:block" />

            {/* Min pitches */}
            <label className="flex items-center gap-2 text-xs text-[#888]">
              Min pitches per hand
              <select
                value={minN}
                onChange={e => { setMinN(parseInt(e.target.value)); setPage(1) }}
                className="text-xs border border-[#ddd] rounded-lg px-2 py-1 bg-white text-[#333]"
              >
                {[20, 50, 100, 150, 200].map(n => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </label>
          </div>

          {/* Table */}
          <div className="px-5 py-3 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-bold text-[#1a1a1a]">
                {pitcher ? pitcher.name : 'All Pitchers'}
                {pitchType ? ` · ${PITCH_TYPES.find(p => p.value === pitchType)?.label}` : ''}
              </h2>
              <p className="text-xs text-[#999] mt-0.5">{total.toLocaleString()} pitcher-pitch combinations</p>
            </div>
            {loading && <span className="text-xs text-[#999] animate-pulse">Loading…</span>}
          </div>

          {error && (
            <div className="mx-5 mb-3 bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">{error}</div>
          )}

          <div className="px-4 pb-5">
            <PlatoonTable
              rows={rows}
              total={total}
              page={page}
              pageSize={50}
              sortCol={sortCol}
              sortDir={sortDir}
              onSort={handleSort}
              onPage={setPage}
              loading={loading}
              season={2026}
            />
          </div>
        </div>

        <p className="text-xs text-[#aaa] text-center pb-4">
          Pitch grades calibrated to Fangraphs Stuff+/Loc+/Pitching+ scale · Click any row to explore pitch locations
        </p>
      </div>
    </main>
  )
}

export default function PlatoonPage() {
  return (
    <Suspense>
      <PlatoonContent />
    </Suspense>
  )
}
