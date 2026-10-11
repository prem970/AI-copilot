import { useQuery } from '@tanstack/react-query'
import { ResponsiveContainer, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip } from 'recharts'
import { api } from './api'
import { Empty, ErrorNotice } from './ui'

export default function Trends() {
  const trends = useQuery({ queryKey: ['trends'], queryFn: api.trends })
  return <section className='panel'><h2>Changes over time</h2><p className='fine-print'>Only results with a recorded report date are plotted. Each chart uses the same test name and unit.</p><ErrorNotice error={trends.error} />
    {trends.isPending ? <Empty>Loading trends…</Empty> : !trends.data?.length ? <Empty>No dated results to plot yet.</Empty> : <div className='trend-grid'>{trends.data.map(trend => <article key={trend.test_name + ':' + trend.unit}><h3>{trend.test_name} <small>{trend.unit ?? 'Unit not stated'}</small></h3><div className='chart' role='img' aria-label={trend.test_name + ' results over time'}><ResponsiveContainer width='100%' height={220}><LineChart data={trend.history}><CartesianGrid strokeDasharray='3 3' vertical={false} /><XAxis dataKey='date' tick={{ fontSize: 11 }} /><YAxis domain={['auto', 'auto']} tick={{ fontSize: 11 }} width={45} /><Tooltip /><Line type='linear' dataKey='value' stroke='#0e7771' strokeWidth={2} dot={{ r: 4 }} isAnimationActive={false} /></LineChart></ResponsiveContainer></div><details><summary>View values as a table</summary><table><thead><tr><th>Date</th><th>Value</th></tr></thead><tbody>{trend.history.map((point, i) => <tr key={point.source_document_id + ':' + i}><td>{point.date}</td><td>{point.value} {trend.unit}</td></tr>)}</tbody></table></details></article>)}</div>}
  </section>
}
