'use client'

import React, { useState } from 'react'
import { PlatoonViz } from './PlatoonViz'

export interface PlatoonRow {
  pitcher_id: number
  pitcher_name: string
  pitcher_team: string | null
  pitch_type: string
  pitch_label: string
  n_l: number | null
  n_r: number | null
  stuff_l: number | null
  stuff_r: number | null
  loc_l: number | null
  loc_r: number | null
  pitching_l: number | null
  pitching_r: number | null
  velo_l: number | null
  velo_r: number | null
  zone_l: number | null
  zone_r: number | null
  whiff_l: number | null
  whiff_r: number | null
  stuff_overall: number | null
  loc_overall: number | null
  pitching_overall: number | null
  stuff_gap: number | null
  loc_gap: number | null
  pitching_gap: number | null
}

interface Props {
  rows: PlatoonRow[]
  total: number
  page: number
  pageSize: number
  sortCol: string
  sortDir: 'asc' | 'desc'
  onSort: (col: string) => void
  onPage: (p: number) => void
  loading: boolean
  season: number
}

type ExpandedKey = string  // `${pitcher_id}__${pitch_type}`

function fmt(v: number | null, decimals = 1) {
  if (v == null) return <span className="text-[#bbb]">—</span>
  return v.toFixed(decimals)
}

function gapColor(v: number | null) {
  if (v == null) return 'text-[#999]'
  if (v > 5)  return 'text-emerald-600 font-semibold'
  if (v > 2)  return 'text-emerald-500'
  if (v < -5) return 'text-red-500 font-semibold'
  if (v < -2) return 'text-red-400'
  return 'text-[#666]'
}

function SortIcon({ col, sortCol, sortDir }: { col: string; sortCol: string; sortDir: 'asc' | 'desc' }) {
  if (col !== sortCol) return <span className="text-[#ccc] ml-0.5">↕</span>
  return <span className="text-[#1a1a1a] ml-0.5">{sortDir === 'asc' ? '↑' : '↓'}</span>
}

function Th({ col, label, sortCol, sortDir, onSort, className = '' }: {
  col: string; label: string; sortCol: string; sortDir: 'asc' | 'desc'
  onSort: (c: string) => void; className?: string
}) {
  return (
    <th
      className={`px-2 py-2 text-left text-[10px] font-semibold uppercase tracking-wide text-[#888] whitespace-nowrap cursor-pointer hover:text-[#1a1a1a] select-none ${className}`}
      onClick={() => onSort(col)}
    >
      {label}<SortIcon col={col} sortCol={sortCol} sortDir={sortDir} />
    </th>
  )
}

export function PlatoonTable({ rows, total, page, pageSize, sortCol, sortDir, onSort, onPage, loading, season }: Props) {
  const [expanded, setExpanded] = useState<ExpandedKey | null>(null)
  const totalPages = Math.ceil(total / pageSize)

  function toggleRow(key: ExpandedKey) {
    setExpanded(prev => prev === key ? null : key)
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="overflow-x-auto rounded-xl border border-[#e8e3db]">
        <table className="w-full text-sm border-collapse">
          <thead className="bg-[#f5f2ed] border-b border-[#e8e3db]">
            <tr>
              <th className="px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wide text-[#888] w-6" />
              <Th col="pitcher_name" label="Pitcher"    sortCol={sortCol} sortDir={sortDir} onSort={onSort} className="min-w-[130px]" />
              <Th col="pitch_label"  label="Pitch"      sortCol={sortCol} sortDir={sortDir} onSort={onSort} />

              {/* Overall */}
              <th className="px-2 py-2 text-[10px] font-semibold uppercase tracking-wide text-[#888] text-center border-l border-[#e8e3db]" colSpan={1}>Overall</th>

              {/* vs L */}
              <th className="px-2 py-2 text-[10px] font-bold uppercase tracking-wide text-[#4A90D9] text-center border-l border-[#e8e3db]" colSpan={4}>vs LHB</th>

              {/* Gap */}
              <th className="px-2 py-2 text-[10px] font-semibold uppercase tracking-wide text-[#888] text-center border-l border-[#e8e3db]" colSpan={3}>Gap (L−R)</th>

              {/* vs R */}
              <th className="px-2 py-2 text-[10px] font-bold uppercase tracking-wide text-[#E8543A] text-center border-l border-[#e8e3db]" colSpan={4}>vs RHB</th>
            </tr>
            <tr className="bg-[#f0ece4] border-b border-[#e8e3db]">
              <th />
              <th /><th />
              {/* Overall col */}
              <Th col="stuff_overall" label="Stf+" sortCol={sortCol} sortDir={sortDir} onSort={onSort} className="text-center border-l border-[#e8e3db]" />

              {/* vs L cols */}
              <Th col="n_l"         label="n"      sortCol={sortCol} sortDir={sortDir} onSort={onSort} className="text-center border-l border-[#e8e3db]" />
              <Th col="stuff_l"     label="Stf+"   sortCol={sortCol} sortDir={sortDir} onSort={onSort} className="text-center" />
              <Th col="loc_l"       label="Loc+"   sortCol={sortCol} sortDir={sortDir} onSort={onSort} className="text-center" />
              <Th col="pitching_l"  label="Pit+"   sortCol={sortCol} sortDir={sortDir} onSort={onSort} className="text-center" />
              {/* Gap cols */}
              <Th col="stuff_gap"   label="ΔStf+"  sortCol={sortCol} sortDir={sortDir} onSort={onSort} className="text-center border-l border-[#e8e3db]" />
              <Th col="loc_gap"     label="ΔLoc+"  sortCol={sortCol} sortDir={sortDir} onSort={onSort} className="text-center" />
              <Th col="pitching_gap" label="ΔPit+" sortCol={sortCol} sortDir={sortDir} onSort={onSort} className="text-center" />
              {/* vs R cols */}
              <Th col="n_r"         label="n"      sortCol={sortCol} sortDir={sortDir} onSort={onSort} className="text-center border-l border-[#e8e3db]" />
              <Th col="stuff_r"     label="Stf+"   sortCol={sortCol} sortDir={sortDir} onSort={onSort} className="text-center" />
              <Th col="loc_r"       label="Loc+"   sortCol={sortCol} sortDir={sortDir} onSort={onSort} className="text-center" />
              <Th col="pitching_r"  label="Pit+"   sortCol={sortCol} sortDir={sortDir} onSort={onSort} className="text-center" />
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={15} className="text-center text-[#aaa] py-12 text-sm">Loading…</td></tr>
            )}
            {!loading && rows.length === 0 && (
              <tr><td colSpan={15} className="text-center text-[#aaa] py-12 text-sm">No results</td></tr>
            )}
            {!loading && rows.map(row => {
              const key = `${row.pitcher_id}__${row.pitch_type}`
              const isOpen = expanded === key
              return (
                <React.Fragment key={key}>
                  <tr
                    onClick={() => toggleRow(key)}
                    className={`border-b border-[#f0ece4] cursor-pointer transition-colors
                      ${isOpen ? 'bg-[#f5f2ed]' : 'hover:bg-[#faf8f5]'}`}
                  >
                    <td className="px-3 py-2.5 text-[#aaa] text-xs">{isOpen ? '▼' : '▶'}</td>
                    <td className="px-2 py-2.5 font-medium text-[#1a1a1a] text-xs">{row.pitcher_name}</td>
                    <td className="px-2 py-2.5 text-[#555] text-xs">{row.pitch_label}</td>

                    {/* Overall */}
                    <td className="px-2 py-2.5 text-center text-xs font-semibold border-l border-[#f0ece4]">{fmt(row.stuff_overall)}</td>

                    {/* vs L */}
                    <td className="px-2 py-2.5 text-center text-[#999] text-xs border-l border-[#f0ece4]">{row.n_l ?? '—'}</td>
                    <td className="px-2 py-2.5 text-center text-xs">{fmt(row.stuff_l)}</td>
                    <td className="px-2 py-2.5 text-center text-xs">{fmt(row.loc_l)}</td>
                    <td className="px-2 py-2.5 text-center text-xs font-medium">{fmt(row.pitching_l)}</td>

                    {/* Gap */}
                    <td className={`px-2 py-2.5 text-center text-xs border-l border-[#f0ece4] ${gapColor(row.stuff_gap)}`}>
                      {row.stuff_gap != null ? (row.stuff_gap > 0 ? '+' : '') + row.stuff_gap.toFixed(1) : '—'}
                    </td>
                    <td className={`px-2 py-2.5 text-center text-xs ${gapColor(row.loc_gap)}`}>
                      {row.loc_gap != null ? (row.loc_gap > 0 ? '+' : '') + row.loc_gap.toFixed(1) : '—'}
                    </td>
                    <td className={`px-2 py-2.5 text-center text-xs ${gapColor(row.pitching_gap)}`}>
                      {row.pitching_gap != null ? (row.pitching_gap > 0 ? '+' : '') + row.pitching_gap.toFixed(1) : '—'}
                    </td>

                    {/* vs R */}
                    <td className="px-2 py-2.5 text-center text-[#999] text-xs border-l border-[#f0ece4]">{row.n_r ?? '—'}</td>
                    <td className="px-2 py-2.5 text-center text-xs">{fmt(row.stuff_r)}</td>
                    <td className="px-2 py-2.5 text-center text-xs">{fmt(row.loc_r)}</td>
                    <td className="px-2 py-2.5 text-center text-xs font-medium">{fmt(row.pitching_r)}</td>
                  </tr>

                  {/* Expanded viz panel */}
                  {isOpen && (
                    <tr key={`${key}__viz`} className="bg-[#faf8f5] border-b border-[#e8e3db]">
                      <td colSpan={15} className="px-6 py-5">
                        <div className="flex flex-col gap-1">
                          <p className="text-xs font-semibold text-[#555] mb-2">
                            {row.pitcher_name} — {row.pitch_label} · Pitch location (catcher's POV)
                          </p>
                          <PlatoonViz
                            pitcherId={row.pitcher_id}
                            pitchType={row.pitch_type}
                            pitchLabel={row.pitch_label}
                            season={season}
                          />
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-xs text-[#888]">
          <span>{total.toLocaleString()} rows</span>
          <div className="flex items-center gap-1">
            <button
              disabled={page <= 1}
              onClick={() => onPage(page - 1)}
              className="px-2.5 py-1 rounded-lg border border-[#e0dbd2] hover:bg-[#f0ece4] disabled:opacity-40 disabled:cursor-not-allowed"
            >←</button>
            <span className="px-2">{page} / {totalPages}</span>
            <button
              disabled={page >= totalPages}
              onClick={() => onPage(page + 1)}
              className="px-2.5 py-1 rounded-lg border border-[#e0dbd2] hover:bg-[#f0ece4] disabled:opacity-40 disabled:cursor-not-allowed"
            >→</button>
          </div>
        </div>
      )}
    </div>
  )
}
