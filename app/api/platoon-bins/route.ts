import { NextRequest, NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase'

export async function GET(req: NextRequest) {
  const sp        = req.nextUrl.searchParams
  const season    = parseInt(sp.get('season') ?? '2026')
  const pitcherId = parseInt(sp.get('pitcher_id') ?? '0')
  const pitchType = sp.get('pitch_type') ?? ''

  if (!pitcherId || !pitchType) {
    return NextResponse.json({ error: 'pitcher_id and pitch_type required' }, { status: 400 })
  }

  const supabase = createServiceClient()

  const { data, error } = await supabase
    .from('platoon_location_bins')
    .select('stand,bin_x,bin_z,total_count,cs_count,whiff_count,ball_count,in_play_count,foul_count')
    .eq('season', season)
    .eq('pitcher_id', pitcherId)
    .eq('pitch_type', pitchType)

  if (error) return NextResponse.json({ error: error.message }, { status: 500 })

  return NextResponse.json({ bins: data ?? [] })
}
