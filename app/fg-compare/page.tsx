'use client'

import { useState, useEffect } from 'react'

const PITCH_LABELS: Record<string, string> = {
  FF: '4-Seam', SI: 'Sinker', FC: 'Cutter', SL: 'Slider',
  ST: 'Sweeper', CH: 'Changeup', CU: 'Curveball', KC: 'Knuckle-Curve', FS: 'Splitter',
}

const PITCH_TYPES = [
  { value: '', label: 'All' },
  { value: 'FF', label: '4-Seam' },
  { value: 'SI', label: 'Sinker' },
  { value: 'FC', label: 'Cutter' },
  { value: 'SL', label: 'Slider' },
  { value: 'CH', label: 'Changeup' },
  { value: 'CU', label: 'Curveball' },
  { value: 'KC', label: 'Knuckle-Curve' },
  { value: 'FS', label: 'Splitter' },
]

interface CompareRow {
  pitcher_id: number
  pitcher_name: string
  pitch_type: string
  n: number
  our_stuff: number
  our_loc: number
  our_pitching: number
  fg_stuff: number
  fg_loc: number | null
  fg_pitching: number | null
  delta_stuff: number
  delta_loc: number | null
  delta_pitching: number | null
}

function deltaColor(d: number | null) {
  if (d == null) return 'text-[#999]'
  if (d > 10)  return 'text-red-500 font-semibold'
  if (d > 5)   return 'text-orange-400'
  if (d < -10) return 'text-blue-500 font-semibold'
  if (d < -5)  return 'text-blue-400'
  return 'text-[#555]'
}

function fmt(v: number | null, d = 1) {
  if (v == null) return <span className="text-[#bbb]">—</span>
  return v.toFixed(d)
}

function fmtDelta(v: number | null) {
  if (v == null) return <span className="text-[#bbb]">—</span>
  return (v > 0 ? '+' : '') + v.toFixed(1)
}

type SortCol = 'pitcher_name' | 'pitch_type' | 'n' | 'our_stuff' | 'fg_stuff' | 'delta_stuff' | 'abs_delta' | 'our_loc' | 'fg_loc' | 'delta_loc'

export default function FgComparePage() {
  const [rows, setRows]         = useState<CompareRow[]>([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState<string | null>(null)
  const [pitchType, setPitchType] = useState('')
  const [minN, setMinN]         = useState(100)
  const [search, setSearch]     = useState('')
  const [sortCol, setSortCol]   = useState<SortCol>('abs_delta')
  const [sortDir, setSortDir]   = useState<'asc' | 'desc'>('desc')

  useEffect(() => {
    setLoading(true)
    fetch(`/api/fg-compare?season=2026&min_n=${minN}`)
      .then(r => r.json())
      .then(d => {
        if (d.error) { setError(d.error); setLoading(false); return }
        setRows(d.rows); setLoading(false)
      })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [minN])

  function handleSort(col: SortCol) {
    if (col === sortCol) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortCol(col); setSortDir(col === 'pitcher_name' || col === 'pitch_type' ? 'asc' : 'desc') }
  }

  function SortIcon({ col }: { col: SortCol }) {
    if (col !== sortCol) return <span className="text-[#ccc] ml-0.5">↕</span>
    return <span className="ml-0.5">{sortDir === 'asc' ? '↑' : '↓'}</span>
  }

  function Th({ col, label, className = '' }: { col: SortCol; label: string; className?: string }) {
    return (
      <th
        onClick={() => handleSort(col)}
        className={`px-2 py-2 text-left text-[10px] font-semibold uppercase tracking-wide text-[#888] whitespace-nowrap cursor-pointer hover:text-[#1a1a1a] select-none ${className}`}
      >
        {label}<SortIcon col={col} />
      </th>
    )
  }

  // Filter + sort client-side
  let visible = rows
  if (pitchType) visible = visible.filter(r => r.pitch_type === pitchType)
  if (search)    visible = visible.filter(r => r.pitcher_name.toLowerCase().includes(search.toLowerCase()))

  visible = [...visible].sort((a, b) => {
    let av: number, bv: number
    if (sortCol === 'abs_delta') {
      av = Math.abs(a.delta_stuff); bv = Math.abs(b.delta_stuff)
    } else if (sortCol === 'pitcher_name' || sortCol === 'pitch_type') {
      return sortDir === 'asc'
        ? String(a[sortCol]).localeCompare(String(b[sortCol]))
        : String(b[sortCol]).localeCompare(String(a[sortCol]))
    } else {
      av = (a[sortCol] as number) ?? 0; bv = (b[sortCol] as number) ?? 0
    }
    return sortDir === 'asc' ? av - bv : bv - av
  })

  // Summary stats (from visible filtered rows)
  const deltas = visible.map(r => r.delta_stuff)
  const mae = deltas.length ? deltas.reduce((s, d) => s + Math.abs(d), 0) / deltas.length : null
  const bias = deltas.length ? deltas.reduce((s, d) => s + d, 0) / deltas.length : null

  // MAE by pitch type — always from ALL rows (unaffected by pitch type filter)
  const PT_ORDER = ['FF', 'SI', 'FC', 'SL', 'ST', 'CH', 'CU', 'KC', 'FS']
  const maeByType = PT_ORDER.map(pt => {
    const ptRows = rows.filter(r => r.pitch_type === pt)
    if (ptRows.length === 0) return null
    const ptMae  = ptRows.reduce((s, r) => s + Math.abs(r.delta_stuff), 0) / ptRows.length
    const ptBias = ptRows.reduce((s, r) => s + r.delta_stuff, 0) / ptRows.length
    return { pt, label: PITCH_LABELS[pt] ?? pt, mae: ptMae, bias: ptBias, n: ptRows.length }
  }).filter(Boolean) as { pt: string; label: string; mae: number; bias: number; n: number }[]

  return (
    <main className="min-h-screen bg-[#edeae4] text-[#1a1a1a]">
      <div className="max-w-6xl mx-auto px-4 py-10 flex flex-col gap-6">

        {/* Header */}
        <div>
          <a href="/" className="text-sm text-[#888] hover:text-[#1a1a1a] transition-colors">← Stuff Splits</a>
          <h1 className="text-3xl font-black tracking-tight mt-1">FanGraphs Comparison</h1>
          <p className="text-sm text-[#666] mt-1">
            Our Stuff+ / Loc+ vs FanGraphs pitch-level grades · 2026
          </p>
        </div>

        {/* Summary chips */}
        {!loading && mae != null && (
          <div className="flex gap-3 flex-wrap">
            {[
              { label: 'Pairs matched', value: visible.length.toString() },
              { label: 'MAE (Stuff+)', value: mae.toFixed(1) + ' pts' },
              { label: 'Bias (our − FG)', value: (bias! > 0 ? '+' : '') + bias!.toFixed(1) + ' pts' },
            ].map(({ label, value }) => (
              <div key={label} className="bg-white border border-[#ddd8d0] rounded-xl px-4 py-2.5 shadow-sm">
                <p className="text-[10px] uppercase tracking-wide text-[#999] font-semibold">{label}</p>
                <p className="text-lg font-black text-[#1a1a1a]">{value}</p>
              </div>
            ))}
          </div>
        )}

        {/* MAE by pitch type */}
        {!loading && maeByType.length > 0 && (
          <div className="bg-white border border-[#ddd8d0] rounded-2xl shadow-sm px-5 py-4">
            <p className="text-[10px] uppercase tracking-wide text-[#999] font-semibold mb-3">MAE by pitch type · Stuff+ vs FanGraphs (all pitchers)</p>
            <div className="overflow-x-auto">
              <table className="text-xs w-full">
                <thead>
                  <tr className="text-[10px] uppercase tracking-wide text-[#aaa] border-b border-[#f0ece4]">
                    <th className="text-left pb-1.5 pr-6">Pitch type</th>
                    <th className="text-right pb-1.5 pr-6">Pairs</th>
                    <th className="text-right pb-1.5 pr-6">MAE</th>
                    <th className="text-right pb-1.5">Bias (our − FG)</th>
                  </tr>
                </thead>
                <tbody>
                  {maeByType.sort((a, b) => b.mae - a.mae).map(({ pt, label, mae: ptMae, bias: ptBias, n }) => (
                    <tr key={pt} className="border-t border-[#f5f2ed]">
                      <td className="py-1.5 pr-6 font-medium text-[#1a1a1a]">{label}</td>
                      <td className="py-1.5 pr-6 text-right text-[#999]">{n}</td>
                      <td className={`py-1.5 pr-6 text-right font-semibold ${ptMae > 10 ? 'text-red-500' : ptMae > 7 ? 'text-orange-400' : 'text-[#22a55e]'}`}>
                        {ptMae.toFixed(1)}
                      </td>
                      <td className={`py-1.5 text-right ${ptBias > 3 ? 'text-orange-400' : ptBias < -3 ? 'text-blue-400' : 'text-[#555]'}`}>
                        {(ptBias > 0 ? '+' : '') + ptBias.toFixed(1)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="bg-white border border-[#ddd8d0] rounded-2xl shadow-sm px-5 py-4 flex flex-wrap items-center gap-4">
          <div className="flex flex-wrap gap-1">
            {PITCH_TYPES.map(pt => (
              <button
                key={pt.value}
                onClick={() => setPitchType(pt.value)}
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

          <input
            type="text"
            placeholder="Search pitcher…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="text-xs border border-[#ddd] rounded-lg px-3 py-1.5 bg-white text-[#333] w-44 focus:outline-none focus:ring-1 focus:ring-[#1a1a1a]"
          />

          <div className="w-px h-5 bg-[#e0dbd2] hidden sm:block" />

          <label className="flex items-center gap-2 text-xs text-[#888]">
            Min pitches
            <select
              value={minN}
              onChange={e => setMinN(parseInt(e.target.value))}
              className="text-xs border border-[#ddd] rounded-lg px-2 py-1 bg-white text-[#333]"
            >
              {[50, 100, 150, 200, 300].map(n => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
        </div>

        {/* Table */}
        <div className="bg-white border border-[#ddd8d0] rounded-2xl shadow-sm overflow-hidden">
          {error && (
            <div className="mx-5 mt-4 bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">{error}</div>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead className="bg-[#f5f2ed] border-b border-[#e8e3db]">
                <tr>
                  <th className="px-2 py-2 text-left text-[10px] font-semibold uppercase tracking-wide text-[#888] whitespace-nowrap" colSpan={3} />
                  <th className="px-2 py-2 text-[10px] font-bold uppercase tracking-wide text-[#4A90D9] text-center border-l border-[#e8e3db]" colSpan={2}>Stuff+</th>
                  <th className="px-2 py-2 text-[10px] font-semibold uppercase tracking-wide text-[#888] text-center border-l border-[#e8e3db]" colSpan={1}>Δ</th>
                  <th className="px-2 py-2 text-[10px] font-bold uppercase tracking-wide text-[#4A90D9] text-center border-l border-[#e8e3db]" colSpan={2}>Loc+</th>
                  <th className="px-2 py-2 text-[10px] font-semibold uppercase tracking-wide text-[#888] text-center border-l border-[#e8e3db]" colSpan={1}>Δ</th>
                </tr>
                <tr className="bg-[#f0ece4] border-b border-[#e8e3db]">
                  <Th col="pitcher_name" label="Pitcher"  className="min-w-[130px]" />
                  <Th col="pitch_type"   label="Pitch" />
                  <Th col="n"            label="n" />
                  <Th col="our_stuff"    label="Ours"   className="border-l border-[#e8e3db] text-center" />
                  <Th col="fg_stuff"     label="FG"     className="text-center" />
                  <Th col="abs_delta"    label="Δ"      className="border-l border-[#e8e3db] text-center" />
                  <Th col="our_loc"      label="Ours"   className="border-l border-[#e8e3db] text-center" />
                  <Th col="fg_loc"       label="FG"     className="text-center" />
                  <Th col="delta_loc"    label="Δ"      className="border-l border-[#e8e3db] text-center" />
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr><td colSpan={9} className="text-center text-[#aaa] py-12 text-sm">Loading…</td></tr>
                )}
                {!loading && visible.length === 0 && (
                  <tr><td colSpan={9} className="text-center text-[#aaa] py-12 text-sm">No results</td></tr>
                )}
                {!loading && visible.map((row, i) => (
                  <tr key={`${row.pitcher_id}__${row.pitch_type}`}
                    className={`border-b border-[#f0ece4] ${i % 2 === 0 ? '' : 'bg-[#faf8f5]'}`}>
                    <td className="px-2 py-2.5 font-medium text-[#1a1a1a] text-xs">{row.pitcher_name}</td>
                    <td className="px-2 py-2.5 text-[#555] text-xs">{PITCH_LABELS[row.pitch_type] ?? row.pitch_type}</td>
                    <td className="px-2 py-2.5 text-[#999] text-xs">{row.n}</td>

                    <td className="px-2 py-2.5 text-center text-xs border-l border-[#f0ece4]">{fmt(row.our_stuff)}</td>
                    <td className="px-2 py-2.5 text-center text-xs">{fmt(row.fg_stuff)}</td>
                    <td className={`px-2 py-2.5 text-center text-xs border-l border-[#f0ece4] ${deltaColor(row.delta_stuff)}`}>
                      {fmtDelta(row.delta_stuff)}
                    </td>

                    <td className="px-2 py-2.5 text-center text-xs border-l border-[#f0ece4]">{fmt(row.our_loc)}</td>
                    <td className="px-2 py-2.5 text-center text-xs">{fmt(row.fg_loc)}</td>
                    <td className={`px-2 py-2.5 text-center text-xs border-l border-[#f0ece4] ${deltaColor(row.delta_loc)}`}>
                      {fmtDelta(row.delta_loc)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[10px] text-[#bbb] px-5 py-3">
            Δ = Ours − FanGraphs. Red = we grade higher than FG, Blue = FG grades higher than us.
          </p>
        </div>

      </div>
    </main>
  )
}
