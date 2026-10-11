import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from './api'
import { Empty, ErrorNotice, dateLabel, ErrorBoundary } from './ui'
import Trends from './Trends'

export function Records() {
  const client = useQueryClient()
  const observations = useQuery({ queryKey: ['observations'], queryFn: api.observations })
  const medications = useQuery({ queryKey: ['medications'], queryFn: api.medications })
  const update = useMutation({ mutationFn: ({ id, status }: { id: string; status: string }) => api.medication(id, status), onSuccess: () => client.invalidateQueries() })
  return <><div className='page-heading'><div><p className='eyebrow'>CONFIRMED HISTORY</p><h1>Records & trends</h1><p>Only the records you have reviewed and confirmed appear here.</p></div></div><ErrorNotice error={observations.error || medications.error || update.error} />
    <section className='panel'><h2>Laboratory results</h2>{observations.isPending ? <Empty>Loading results…</Empty> : !observations.data?.length ? <Empty>Confirm laboratory results from your documents to see them here.</Empty> : <div className='table-wrap'><table><thead><tr><th>Test</th><th>Result</th><th>Printed range</th><th>Date</th><th>Source</th></tr></thead><tbody>{observations.data.map(row => <tr key={row.id}><td>{row.display_name}</td><td><strong>{row.value_numeric ?? row.value_text ?? 'Not stated'}{row.unit ? ` ${row.unit}` : ''}</strong>{row.source_abnormal_flag && <small>{row.source_abnormal_flag}</small>}</td><td>{row.reference_low ?? '—'} – {row.reference_high ?? '—'}</td><td>{dateLabel(row.effective_at)}</td><td><a target='_blank' rel='noreferrer' href={'/api/v1/documents/' + row.document_id + '/file'}>Original</a></td></tr>)}</tbody></table></div>}</section>
    <ErrorBoundary fallback={<Empty>Loading trend viewer…</Empty>}><Trends /></ErrorBoundary>
    <section className='panel'><h2>Medication history</h2><p className='fine-print'>Track whether you currently take a prescribed medication. Status changes do not change its prescribed instructions.</p>{medications.isPending ? <Empty>Loading medications…</Empty> : !medications.data?.length ? <Empty>Confirm prescriptions to build your medication history.</Empty> : <div className='table-wrap'><table><thead><tr><th>Medication</th><th>Prescribed directions</th><th>Date</th><th>Your current status</th></tr></thead><tbody>{medications.data.map(row => <tr key={row.id}><td><strong>{row.medication_name}</strong><small>{row.generic_name} {row.strength}</small></td><td>{row.dose_instructions ?? 'Not stated'}<small>{row.frequency} · {row.duration}</small></td><td>{dateLabel(row.prescription_date)}</td><td><label className='sr-only' htmlFor={row.id}>Status for {row.medication_name}</label><select id={row.id} disabled={update.isPending} value={row.medication_status} onChange={e => update.mutate({ id: row.id, status: e.target.value })}>{['prescribed', 'active', 'discontinued', 'completed'].map(status => <option key={status}>{status}</option>)}</select></td></tr>)}</tbody></table></div>}</section>
  </>
}
