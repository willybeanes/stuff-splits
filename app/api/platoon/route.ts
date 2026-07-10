import { NextRequest, NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase'

const PAGE_SIZE = 50

const PITCH_LABELS: Record<string, string> = {
  FF: '4-Seam', SI: 'Sinker', FC: 'Cutter', SL: 'Slider',
  ST: 'Sweeper', CH: 'Changeup', CU: 'Curveball', KC: 'Knuckle-Curve',
  FS: 'Splitter', SV: 'Slurve',
}

export async function GET(req: NextRequest) {
  const sp      = req.nextUrl.searchParams
  const season  = parseInt(sp.get('season') ?? '2026')
  const pitchType = sp.get('pitch_type') ?? ''
  const pitcherId = sp.get('pitcher_id') ? parseInt(sp.get('pitcher_id')!) : null
  const minN    = parseInt(sp.get('min_n') ?? '50')
  const sortCol = sp.get('sort') ?? 'stuff_gap'
  const sortDir = (sp.get('dir') ?? 'desc') as 'asc' | 'desc'
  const page    = Math.max(1, parseInt(sp.get('page') ?? '1'))

  const supabase = createServiceClient()

  // Fetch both L and R rows in one query, then pivot client-side
  let query = supabase
    .from('platoon_grades')
    .select('*')
    .eq('season', season)
    .gte('n_pitches', minN)

  if (pitchType) query = query.eq('pitch_type', pitchType)
  if (pitcherId) query = query.eq('pitcher_id', pitcherId)

  const { data, error } = await query.limit(10000)
  if (error) return NextResponse.json({ error: error.message }, { status: 500 })

  // Pivot: group by pitcher_id + pitch_type, merge L and R
  const map = new Map<string, Record<string, unknown>>()

  for (const row of data ?? []) {
    const key = `${row.pitcher_id}__${row.pitch_type}`
    if (!map.has(key)) {
      map.set(key, {
        pitcher_id:   row.pitcher_id,
        pitcher_name: row.pitcher_name,
        pitcher_team: row.pitcher_team,
        pitch_type:   row.pitch_type,
        pitch_label:  PITCH_LABELS[row.pitch_type] ?? row.pitch_type,
      })
    }
    const entry = map.get(key)!
    const hand  = row.stand === 'L' ? 'l' : 'r'
    entry[`n_${hand}`]         = row.n_pitches
    entry[`stuff_${hand}`]     = row.stuff_plus
    entry[`loc_${hand}`]       = row.loc_plus
    entry[`pitching_${hand}`]  = row.pitching_plus
    entry[`velo_${hand}`]      = row.avg_velo
    entry[`zone_${hand}`]      = row.zone_pct
    entry[`whiff_${hand}`]     = row.whiff_pct
    entry[`cs_${hand}`]        = row.cs_pct
  }

  // Only include rows that have both L and R
  let rows = [...map.values()].filter(r => r.n_l != null && r.n_r != null)

  // Compute gaps and overall weighted averages
  for (const r of rows) {
    r.stuff_gap    = r.stuff_l != null && r.stuff_r != null
      ? Math.round(((r.stuff_l as number) - (r.stuff_r as number)) * 10) / 10 : null
    r.loc_gap      = r.loc_l != null && r.loc_r != null
      ? Math.round(((r.loc_l as number) - (r.loc_r as number)) * 10) / 10 : null
    r.pitching_gap = r.pitching_l != null && r.pitching_r != null
      ? Math.round(((r.pitching_l as number) - (r.pitching_r as number)) * 10) / 10 : null

    const nl = (r.n_l as number) ?? 0
    const nr = (r.n_r as number) ?? 0
    const total = nl + nr
    r.stuff_overall    = r.stuff_l != null && r.stuff_r != null && total > 0
      ? Math.round(((r.stuff_l as number) * nl + (r.stuff_r as number) * nr) / total * 10) / 10 : null
    r.loc_overall      = r.loc_l != null && r.loc_r != null && total > 0
      ? Math.round(((r.loc_l as number) * nl + (r.loc_r as number) * nr) / total * 10) / 10 : null
    r.pitching_overall = r.pitching_l != null && r.pitching_r != null && total > 0
      ? Math.round(((r.pitching_l as number) * nl + (r.pitching_r as number) * nr) / total * 10) / 10 : null
  }

  // Sort
  const dir = sortDir === 'asc' ? 1 : -1
  rows.sort((a, b) => {
    const av = a[sortCol] as number | null
    const bv = b[sortCol] as number | null
    if (av == null && bv == null) return 0
    if (av == null) return 1
    if (bv == null) return -1
    return (av - bv) * dir
  })

  const total  = rows.length
  const paged  = rows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  return NextResponse.json({ rows: paged, total, page, pageSize: PAGE_SIZE })
}
