import { NextRequest, NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase'

const FG_PROXY = 'https://fg-proxy.vercel.app/api/fangraphs'
const FG_PITCH_TYPES = ['FF', 'SI', 'FC', 'SL', 'CH', 'CU', 'KC', 'FS'] as const

export async function GET(req: NextRequest) {
  const sp     = req.nextUrl.searchParams
  const season = parseInt(sp.get('season') ?? '2026')
  const minN   = parseInt(sp.get('min_n') ?? '50')

  // ── 1. Fetch FanGraphs pitch-type grades via fg-proxy ──────────────────────
  const fgUrl = `${FG_PROXY}?pos=all&stats=pit&lg=all&qual=0&season=${season}&season1=${season}&month=0&type=36&pageitems=2000&pagenum=1`
  const fgRes = await fetch(fgUrl, { next: { revalidate: 3600 } })
  if (!fgRes.ok) return NextResponse.json({ error: `fg-proxy ${fgRes.status}` }, { status: 502 })
  const fgJson = await fgRes.json()

  // Build map: mlbam_id → { pitch_type → { fg_stuff, fg_loc, fg_pitching } }
  const fgMap = new Map<number, Record<string, { fg_stuff: number; fg_loc: number | null; fg_pitching: number | null; player_name: string }>>()
  for (const row of fgJson.data ?? []) {
    const mlbam = row.xMLBAMID
    if (!mlbam) continue
    for (const pt of FG_PITCH_TYPES) {
      const s = row[`sp_s_${pt}`]
      if (s == null) continue
      if (!fgMap.has(mlbam)) fgMap.set(mlbam, {})
      fgMap.get(mlbam)![pt] = {
        fg_stuff:    Math.round(s * 10) / 10,
        fg_loc:      row[`sp_l_${pt}`] != null ? Math.round(row[`sp_l_${pt}`] * 10) / 10 : null,
        fg_pitching: row[`sp_p_${pt}`] != null ? Math.round(row[`sp_p_${pt}`] * 10) / 10 : null,
        player_name: row.PlayerName ?? '',
      }
    }
  }

  // ── 2. Fetch our platoon grades from Supabase ──────────────────────────────
  const supabase = createServiceClient()
  const { data: grades, error } = await supabase
    .from('platoon_grades')
    .select('pitcher_id, pitcher_name, pitch_type, stand, n_pitches, stuff_plus, loc_plus, pitching_plus')
    .eq('season', season)
    .gte('n_pitches', 0)
    .limit(20000)

  if (error) return NextResponse.json({ error: error.message }, { status: 500 })

  // Compute weighted overall per pitcher×pitch_type (merge L + R)
  const ourMap = new Map<string, {
    pitcher_id: number; pitcher_name: string; pitch_type: string
    n: number; stuff: number; loc: number; pitching: number
  }>()

  for (const g of grades ?? []) {
    const key = `${g.pitcher_id}__${g.pitch_type}`
    if (!ourMap.has(key)) {
      ourMap.set(key, { pitcher_id: g.pitcher_id, pitcher_name: g.pitcher_name, pitch_type: g.pitch_type, n: 0, stuff: 0, loc: 0, pitching: 0 })
    }
    const entry = ourMap.get(key)!
    const w = g.n_pitches ?? 0
    entry.n       += w
    entry.stuff   += (g.stuff_plus   ?? 0) * w
    entry.loc     += (g.loc_plus     ?? 0) * w
    entry.pitching += (g.pitching_plus ?? 0) * w
  }

  // ── 3. Join on pitcher_id + pitch_type ────────────────────────────────────
  const rows = []
  for (const [, our] of ourMap) {
    if (our.n < minN) continue
    const fgPitcher = fgMap.get(our.pitcher_id)
    if (!fgPitcher) continue
    const fg = fgPitcher[our.pitch_type]
    if (!fg) continue

    const our_stuff = Math.round(our.stuff / our.n * 10) / 10
    const our_loc   = Math.round(our.loc   / our.n * 10) / 10
    const our_pit   = Math.round(our.pitching / our.n * 10) / 10

    rows.push({
      pitcher_id:   our.pitcher_id,
      pitcher_name: our.pitcher_name,
      pitch_type:   our.pitch_type,
      n:            our.n,
      our_stuff,
      our_loc,
      our_pitching: our_pit,
      fg_stuff:     fg.fg_stuff,
      fg_loc:       fg.fg_loc,
      fg_pitching:  fg.fg_pitching,
      delta_stuff:   Math.round((our_stuff - fg.fg_stuff) * 10) / 10,
      delta_loc:     fg.fg_loc != null ? Math.round((our_loc - fg.fg_loc) * 10) / 10 : null,
      delta_pitching: fg.fg_pitching != null ? Math.round((our_pit - fg.fg_pitching) * 10) / 10 : null,
    })
  }

  // Sort by abs(delta_stuff) desc by default, unless overridden
  const sortCol = sp.get('sort') ?? 'abs_delta'
  const sortDir = sp.get('dir') ?? 'desc'
  rows.sort((a, b) => {
    let av: number, bv: number
    if (sortCol === 'abs_delta') {
      av = Math.abs(a.delta_stuff); bv = Math.abs(b.delta_stuff)
    } else {
      av = (a as unknown as Record<string, number>)[sortCol] ?? 0
      bv = (b as unknown as Record<string, number>)[sortCol] ?? 0
    }
    return sortDir === 'asc' ? av - bv : bv - av
  })

  return NextResponse.json({ rows, total: rows.length })
}
