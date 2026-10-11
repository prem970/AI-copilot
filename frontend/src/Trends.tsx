import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, type Trend } from './api'
import { Empty, ErrorNotice } from './ui'

function TrendChart({ trend }: { trend: Trend }) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null)
  const history = [...trend.history].sort((a, b) => a.date.localeCompare(b.date))
  const values = history.map(h => h.value)

  const rawMin = Math.min(...values)
  const rawMax = Math.max(...values)
  const span = rawMax - rawMin
  const padding = span === 0 ? (rawMax === 0 ? 1 : Math.abs(rawMax * 0.2)) : span * 0.15
  const minVal = Number((rawMin - padding).toFixed(1))
  const maxVal = Number((rawMax + padding).toFixed(1))
  const valRange = maxVal - minVal || 1

  const width = 500
  const height = 220
  const padLeft = 55
  const padRight = 25
  const padTop = 25
  const padBottom = 35
  const plotWidth = width - padLeft - padRight
  const plotHeight = height - padTop - padBottom

  const getX = (index: number) => {
    if (history.length <= 1) return padLeft + plotWidth / 2
    return padLeft + (index / (history.length - 1)) * plotWidth
  }

  const getY = (val: number) => {
    return padTop + plotHeight - ((val - minVal) / valRange) * plotHeight
  }

  const points = history.map((pt, i) => ({
    ...pt,
    x: getX(i),
    y: getY(pt.value),
  }))

  const pathD = points.length === 1
    ? ''
    : points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')

  const gridTicks = [minVal, minVal + valRange * 0.33, minVal + valRange * 0.66, maxVal]
  const hoveredPoint = hoveredIndex !== null ? points[hoveredIndex] : null

  return (
    <article key={trend.test_name + ':' + (trend.unit ?? '')}>
      <h3>{trend.test_name} <small>{trend.unit ?? 'Unit not stated'}</small></h3>
      <div className='chart' role='img' aria-label={trend.test_name + ' results over time'}>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          style={{ width: '100%', height: '100%', display: 'block' }}
          preserveAspectRatio='none'
        >
          {gridTicks.map((tick, i) => {
            const y = getY(tick)
            return (
              <g key={i}>
                <line
                  x1={padLeft}
                  y1={y}
                  x2={width - padRight}
                  y2={y}
                  stroke='var(--line, #e2e8f0)'
                  strokeDasharray='3 3'
                  strokeWidth={1}
                />
                <text
                  x={padLeft - 8}
                  y={y + 4}
                  textAnchor='end'
                  fontSize={10}
                  fill='currentColor'
                  opacity={0.7}
                >
                  {Number(tick.toFixed(1))}
                </text>
              </g>
            )
          })}

          {points.map((p, i) => {
            const showLabel = history.length <= 6 || i === 0 || i === history.length - 1 || i % Math.ceil(history.length / 5) === 0
            if (!showLabel) return null
            return (
              <text
                key={'x-' + i}
                x={p.x}
                y={height - 10}
                textAnchor='middle'
                fontSize={10}
                fill='currentColor'
                opacity={0.7}
              >
                {p.date}
              </text>
            )
          })}

          {points.length > 1 && (
            <path
              d={`${pathD} L ${points[points.length - 1].x.toFixed(1)} ${(padTop + plotHeight).toFixed(1)} L ${points[0].x.toFixed(1)} ${(padTop + plotHeight).toFixed(1)} Z`}
              fill='rgba(14, 119, 113, 0.08)'
            />
          )}

          {points.length > 1 && (
            <path
              d={pathD}
              fill='none'
              stroke='#0e7771'
              strokeWidth={2.5}
              strokeLinecap='round'
              strokeLinejoin='round'
            />
          )}

          {points.map((p, i) => (
            <g key={'pt-' + i}>
              <circle
                cx={p.x}
                cy={p.y}
                r={hoveredIndex === i ? 7 : 5}
                fill={hoveredIndex === i ? '#084844' : '#0e7771'}
                stroke='#ffffff'
                strokeWidth={2}
                style={{ cursor: 'pointer', transition: 'r 0.15s ease' }}
                onMouseEnter={() => setHoveredIndex(i)}
                onMouseLeave={() => setHoveredIndex(null)}
              />
              <circle
                cx={p.x}
                cy={p.y}
                r={16}
                fill='transparent'
                style={{ cursor: 'pointer' }}
                onMouseEnter={() => setHoveredIndex(i)}
                onMouseLeave={() => setHoveredIndex(null)}
              />
            </g>
          ))}
        </svg>

        {hoveredPoint && (
          <div
            className='chart-tooltip'
            style={{
              left: `${(hoveredPoint.x / width) * 100}%`,
              top: `${(hoveredPoint.y / height) * 100}%`,
            }}
          >
            <strong>{hoveredPoint.value} {trend.unit ?? ''}</strong>
            <small style={{ display: 'block', opacity: 0.8 }}>{hoveredPoint.date}</small>
            {(hoveredPoint.reference_low != null || hoveredPoint.reference_high != null) && (
              <small style={{ display: 'block', opacity: 0.7 }}>
                Range: {hoveredPoint.reference_low ?? '—'} – {hoveredPoint.reference_high ?? '—'}
              </small>
            )}
          </div>
        )}
      </div>

      <details>
        <summary>View values as a table</summary>
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Value</th>
            </tr>
          </thead>
          <tbody>
            {trend.history.map((point, i) => (
              <tr key={point.source_document_id + ':' + i}>
                <td>{point.date}</td>
                <td>{point.value} {trend.unit}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </article>
  )
}

export default function Trends() {
  const trends = useQuery({ queryKey: ['trends'], queryFn: api.trends })
  return (
    <section className='panel'>
      <h2>Changes over time</h2>
      <p className='fine-print'>Only results with a recorded report date are plotted. Each chart uses the same test name and unit.</p>
      <ErrorNotice error={trends.error} />
      {trends.isPending ? (
        <Empty>Loading trends…</Empty>
      ) : !trends.data?.length ? (
        <Empty>No dated results to plot yet.</Empty>
      ) : (
        <div className='trend-grid'>
          {trends.data.map(trend => (
            <TrendChart key={trend.test_name + ':' + (trend.unit ?? '')} trend={trend} />
          ))}
        </div>
      )}
    </section>
  )
}
