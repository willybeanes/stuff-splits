'use client'

import { useEffect, useRef, useState } from 'react'

interface Bin {
  stand: string
  bin_x: number
  bin_z: number
  total_count: number
  cs_count: number
  whiff_count: number
  ball_count: number
  in_play_count: number
  foul_count: number
}

interface Props {
  pitcherId: number
  pitchType: string
  pitchLabel: string
  season?: number
}

type VizMode = 'density'

// Grid bounds must match 6_export_platoon_splits.py
const X_MIN = -2.0, X_MAX = 2.0, X_BINS = 21
const Z_MIN = 0.3,  Z_MAX = 4.7,  Z_BINS = 21
const BIN_W = (X_MAX - X_MIN) / X_BINS
const BIN_H = (Z_MAX - Z_MIN) / Z_BINS

// Strike zone in data coords
const SZ_X1 = -0.83, SZ_X2 = 0.83
const SZ_Z1 = 1.5,   SZ_Z2 = 3.5

// Canvas dimensions
const CW = 240, CH = 300
const PAD = { top: 8, right: 8, bottom: 28, left: 32 }
const PW = CW - PAD.left - PAD.right
const PH = CH - PAD.top  - PAD.bottom

function dataToCanvas(x: number, z: number) {
  const cx = PAD.left + ((x - X_MIN) / (X_MAX - X_MIN)) * PW
  const cy = PAD.top  + ((Z_MAX - z) / (Z_MAX - Z_MIN)) * PH
  return [cx, cy]
}


function densityColor(t: number): [number, number, number, number] {
  // dark blue → gold
  const stops: Array<[[number,number,number], number]> = [
    [[13, 17, 23],  0],
    [[13, 32, 64],  0.15],
    [[26, 64,128],  0.35],
    [[32, 96,192],  0.55],
    [[232,197, 58], 0.75],
    [[255,102,  0], 1],
  ]
  let r=0,g=0,b=0
  for (let i=1; i<stops.length; i++) {
    const [c0,t0] = stops[i-1]
    const [c1,t1] = stops[i]
    if (t <= t1) {
      const f = (t - t0) / (t1 - t0)
      r = c0[0] + f*(c1[0]-c0[0])
      g = c0[1] + f*(c1[1]-c0[1])
      b = c0[2] + f*(c1[2]-c0[2])
      break
    }
    [r,g,b] = c1
  }
  return [r,g,b, t < 0.05 ? 0 : 0.88]
}

function drawPanel(
  ctx: CanvasRenderingContext2D,
  bins: Bin[],
  stand: string,
  maxCount: number,
) {
  ctx.clearRect(0, 0, CW, CH)
  ctx.fillStyle = '#0d1117'
  ctx.fillRect(0, 0, CW, CH)

  const [szX1, szZ1] = dataToCanvas(SZ_X1, SZ_Z2)
  const [szX2, szZ2] = dataToCanvas(SZ_X2, SZ_Z1)

  // Shadow zone
  ctx.strokeStyle = '#444'
  ctx.lineWidth = 1
  ctx.setLineDash([3, 3])
  const shadowPx = (0.167 / (X_MAX - X_MIN)) * PW
  const shadowPz = (0.167 / (Z_MAX - Z_MIN)) * PH
  ctx.strokeRect(szX1 - shadowPx, szZ1 - shadowPz,
    (szX2-szX1) + shadowPx*2, (szZ2-szZ1) + shadowPz*2)
  ctx.setLineDash([])

  // Bin pixels
  const bwPx = (BIN_W / (X_MAX - X_MIN)) * PW + 1
  const bhPx = (BIN_H / (Z_MAX - Z_MIN)) * PH + 1

  for (const bin of bins) {
    if (bin.stand !== stand) continue
    const [cx, cy] = dataToCanvas(
      X_MIN + bin.bin_x * BIN_W + BIN_W/2,
      Z_MIN + bin.bin_z * BIN_H + BIN_H/2,
    )

    const t = maxCount > 0 ? Math.sqrt(bin.total_count / maxCount) : 0
    const [r,g,b,a] = densityColor(t)

    if (a < 0.03) continue
    ctx.fillStyle = `rgba(${Math.round(r)},${Math.round(g)},${Math.round(b)},${a.toFixed(2)})`
    ctx.fillRect(cx - bwPx/2, cy - bhPx/2, bwPx, bhPx)
  }

  // Strike zone
  ctx.strokeStyle = '#fff'
  ctx.lineWidth = 1.5
  ctx.strokeRect(szX1, szZ1, szX2-szX1, szZ2-szZ1)

  // Zone grid
  ctx.strokeStyle = '#444'
  ctx.lineWidth = 0.6
  for (let i=1; i<3; i++) {
    const gx = szX1 + i*(szX2-szX1)/3
    ctx.beginPath(); ctx.moveTo(gx, szZ1); ctx.lineTo(gx, szZ2); ctx.stroke()
    const gz = szZ1 + i*(szZ2-szZ1)/3
    ctx.beginPath(); ctx.moveTo(szX1, gz); ctx.lineTo(szX2, gz); ctx.stroke()
  }

  // Home plate
  const [hx1] = dataToCanvas(-0.71, 0.38)
  const [hx2] = dataToCanvas( 0.71, 0.38)
  const [,hy]  = dataToCanvas(0, 0.38)
  ctx.strokeStyle = '#666'; ctx.lineWidth = 1.5
  ctx.beginPath(); ctx.moveTo(hx1, hy); ctx.lineTo(hx2, hy); ctx.stroke()

  // Y-axis tick labels
  ctx.fillStyle = '#666'; ctx.font = '9px monospace'; ctx.textAlign = 'right'
  for (const z of [1.5, 2.5, 3.5]) {
    const [,cy] = dataToCanvas(X_MIN, z)
    ctx.fillText(z.toFixed(1), PAD.left - 3, cy + 3)
  }

  // Hand label
  const label = stand === 'L' ? 'vs LHB' : 'vs RHB'
  ctx.fillStyle = '#aaa'; ctx.font = 'bold 10px sans-serif'; ctx.textAlign = 'center'
  ctx.fillText(label, CW/2, CH - 8)
}

export function PlatoonViz({ pitcherId, pitchType, pitchLabel, season = 2026 }: Props) {
  const canvasL = useRef<HTMLCanvasElement>(null)
  const canvasR = useRef<HTMLCanvasElement>(null)
  const [bins, setBins] = useState<Bin[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    fetch(`/api/platoon-bins?season=${season}&pitcher_id=${pitcherId}&pitch_type=${pitchType}`)
      .then(r => r.json())
      .then(d => { setBins(d.bins ?? []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [pitcherId, pitchType, season])

  useEffect(() => {
    if (loading || !bins.length) return
    const maxCount = Math.max(...bins.map(b => b.total_count))
    for (const [ref, stand] of [[canvasL, 'L'], [canvasR, 'R']] as const) {
      const ctx = ref.current?.getContext('2d')
      if (ctx) drawPanel(ctx, bins, stand, maxCount)
    }
  }, [bins, loading])

  return (
    <div className="flex flex-col gap-3">
      {/* Canvases */}
      {loading ? (
        <div className="flex gap-3">
          {[0,1].map(i => (
            <div key={i} style={{ width: CW, height: CH }}
              className="rounded-xl bg-[#0d1117] animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="flex gap-3">
          <canvas ref={canvasL} width={CW} height={CH}
            className="rounded-xl" style={{ background: '#0d1117' }} />
          <canvas ref={canvasR} width={CW} height={CH}
            className="rounded-xl" style={{ background: '#0d1117' }} />
        </div>
      )}

    </div>
  )
}
