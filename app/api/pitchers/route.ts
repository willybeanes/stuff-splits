import { NextRequest, NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase'

function deaccent(s: string) {
  return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
}

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const q = searchParams.get('q') ?? ''
  const season = parseInt(searchParams.get('season') ?? '2026')

  if (q.length < 2) return NextResponse.json([])

  const db = createServiceClient()
  const { data, error } = await db
    .from('pitcher_catcher_stats')
    .select('pitcher_id, pitcher_name, pitcher_team')
    .eq('season', season)
    .eq('catcher_id', 0)

  if (error) return NextResponse.json({ error: error.message }, { status: 500 })

  const needle = deaccent(q)
  const results = (data ?? [])
    .filter(r => deaccent(r.pitcher_name ?? '').includes(needle))
    .sort((a, b) => (a.pitcher_name ?? '').localeCompare(b.pitcher_name ?? ''))
    .slice(0, 10)
    .map(r => ({ mlbam_id: r.pitcher_id, name: r.pitcher_name, team: r.pitcher_team }))

  return NextResponse.json(results)
}
