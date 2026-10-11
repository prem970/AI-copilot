import { useState, type FormEvent } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Upload, FileText, ExternalLink, Plus, Trash2 } from 'lucide-react'
import { api, type Extraction, type Candidate, type CandidateObservation, type CandidateMedication } from './api'
import { Empty, ErrorNotice, Status, Sources, dateLabel } from './ui'

function Review({ extraction, onComplete }: { extraction: Extraction; onComplete: () => void }) {
  const client = useQueryClient()
  const [candidate, setCandidate] = useState<Candidate>(() => structuredClone(extraction.structured_candidate_data))
  const [selectedObs, setSelectedObs] = useState(() => candidate.observations.map(o => o.id))
  const [selectedMeds, setSelectedMeds] = useState(() => candidate.medications.map(m => m.id))
  const [active, setActive] = useState<string[]>([])
  const [reviewed, setReviewed] = useState(false)
  const save = useMutation({ mutationFn: async (confirm: boolean) => {
    const updated = await api.edit(extraction.document_id, extraction.revision, candidate)
    if (confirm) await api.confirm(extraction.document_id, updated.revision, selectedObs, selectedMeds, active.filter(id => selectedMeds.includes(id)))
    return confirm
  }, onSuccess: async confirm => {
    await client.invalidateQueries({ queryKey: ['extraction', extraction.document_id] })
    await client.invalidateQueries({ queryKey: ['documents'] })
    if (confirm) { await client.invalidateQueries({ queryKey: ['observations'] }); await client.invalidateQueries({ queryKey: ['medications'] }); await client.invalidateQueries({ queryKey: ['trends'] }); onComplete() }
  } })
  function obs(index: number, patch: Partial<CandidateObservation>) { setCandidate(previous => ({ ...previous, observations: previous.observations.map((item, i) => i === index ? { ...item, ...patch } : item) })); setReviewed(false) }
  function med(index: number, patch: Partial<CandidateMedication>) { setCandidate(previous => ({ ...previous, medications: previous.medications.map((item, i) => i === index ? { ...item, ...patch } : item) })); setReviewed(false) }
  function toggle(ids: string[], id: string) { return ids.includes(id) ? ids.filter(item => item !== id) : [...ids, id] }
  function addObservation() {
    const item: CandidateObservation = { id: crypto.randomUUID(), test_name: '', value_numeric: null, value_text: null, unit: null, reference_low: null, reference_high: null, source_abnormal_flag: null, source_text: '' }
    setCandidate(previous => ({ ...previous, observations: [...previous.observations, item] })); setSelectedObs(previous => [...previous, item.id]); setReviewed(false)
  }
  function addMedication() {
    const item: CandidateMedication = { id: crypto.randomUUID(), medication_name: '', generic_name: null, strength: null, dose_instructions: null, route: null, frequency: null, duration: null, prescription_date: null, source_text: '' }
    setCandidate(previous => ({ ...previous, medications: [...previous.medications, item] })); setSelectedMeds(previous => [...previous, item.id]); setReviewed(false)
  }
  return <section className='panel review'><div className='section-heading'><div><h2>Verify extracted records</h2><p>Compare every selected record with the original. Correct unclear fields before confirming.</p></div><Status value={extraction.review_status} /></div>
    <p className='fine-print'>Extracted by {extraction.extraction_provider} · revision {extraction.revision}</p>
    <a href={'/api/v1/documents/' + extraction.document_id + '/file'} target='_blank' rel='noreferrer' className='source-link'><ExternalLink size={16} /> Open original document</a>
    <details className='raw-text'><summary>Read extracted source text</summary><pre>{extraction.raw_ocr_text}</pre></details>
    <div className='form-row'><label>Document type<select value={candidate.document_type} onChange={e => { setCandidate({ ...candidate, document_type: e.target.value }); setReviewed(false) }}>{['lab_report', 'prescription', 'discharge_summary', 'other'].map(type => <option key={type} value={type}>{type.replaceAll('_', ' ')}</option>)}</select></label><label>Report date<input type='date' value={candidate.document_date ?? ''} onChange={e => { setCandidate({ ...candidate, document_date: e.target.value || null }); setReviewed(false) }} /></label></div>
    {candidate.unreadable_segments.map((segment, i) => <p className='notice' key={i}>{segment}</p>)}
    <div className='section-heading'><h3>Laboratory results</h3><button onClick={addObservation}><Plus size={15} /> Add result from source</button></div>
    {candidate.observations.map((item, i) => <fieldset className='candidate' key={item.id}><legend>Result {i + 1}</legend><label className='check'><input type='checkbox' checked={selectedObs.includes(item.id)} onChange={() => setSelectedObs(toggle(selectedObs, item.id))} /> Include in confirmed history</label>
      <div className='form-row'><label>Test name<input required value={item.test_name} onChange={e => obs(i, { test_name: e.target.value })} /></label><label>Value<input type='number' step='any' value={item.value_numeric ?? ''} onChange={e => obs(i, { value_numeric: e.target.value === '' ? null : Number(e.target.value), value_text: e.target.value || null })} /></label><label>Unit<input value={item.unit ?? ''} onChange={e => obs(i, { unit: e.target.value || null })} /></label></div>
      <label>Reported text, for nonnumeric results<input maxLength={1000} disabled={item.value_numeric !== null} value={item.value_numeric === null ? item.value_text ?? '' : ''} onChange={e => obs(i, { value_text: e.target.value || null })} /></label>
      <div className='form-row'><label>Reference low<input type='number' step='any' value={item.reference_low ?? ''} onChange={e => obs(i, { reference_low: e.target.value === '' ? null : Number(e.target.value) })} /></label><label>Reference high<input type='number' step='any' value={item.reference_high ?? ''} onChange={e => obs(i, { reference_high: e.target.value === '' ? null : Number(e.target.value) })} /></label><label>Printed flag<select value={item.source_abnormal_flag ?? ''} onChange={e => obs(i, { source_abnormal_flag: e.target.value || null })}><option value=''>Not stated</option>{['NORMAL', 'H', 'L', 'CRITICAL'].map(flag => <option key={flag}>{flag}</option>)}</select></label></div>
      <label>Source excerpt<textarea required rows={2} value={item.source_text} onChange={e => obs(i, { source_text: e.target.value })} /></label><label>Source page<input type='number' min={1} value={item.page ?? ''} onChange={e => obs(i, { page: e.target.value ? Number(e.target.value) : null })} /></label>
    </fieldset>)}
    <div className='section-heading'><h3>Prescribed medications</h3><button onClick={addMedication}><Plus size={15} /> Add medication from source</button></div>
    {candidate.medications.map((item, i) => <fieldset className='candidate' key={item.id}><legend>Medication {i + 1}</legend><div className='form-row'><label className='check'><input type='checkbox' checked={selectedMeds.includes(item.id)} onChange={() => setSelectedMeds(toggle(selectedMeds, item.id))} /> Include in history</label><label className='check'><input type='checkbox' checked={active.includes(item.id)} onChange={() => setActive(toggle(active, item.id))} /> I currently take this medication</label></div>
      <div className='form-row'><label>Name<input value={item.medication_name} onChange={e => med(i, { medication_name: e.target.value })} /></label><label>Generic name, if printed<input value={item.generic_name ?? ''} onChange={e => med(i, { generic_name: e.target.value || null })} /></label><label>Strength<input value={item.strength ?? ''} onChange={e => med(i, { strength: e.target.value || null })} /></label></div>
      <label>Dose instructions, as prescribed<input value={item.dose_instructions ?? ''} onChange={e => med(i, { dose_instructions: e.target.value || null })} /></label><div className='form-row'><label>Frequency<input value={item.frequency ?? ''} onChange={e => med(i, { frequency: e.target.value || null })} /></label><label>Duration<input value={item.duration ?? ''} onChange={e => med(i, { duration: e.target.value || null })} /></label><label>Route<input value={item.route ?? ''} onChange={e => med(i, { route: e.target.value || null })} /></label><label>Prescription date<input type='date' value={item.prescription_date ?? ''} onChange={e => med(i, { prescription_date: e.target.value || null })} /></label></div>
      <label>Source excerpt<textarea rows={2} value={item.source_text} onChange={e => med(i, { source_text: e.target.value })} /></label><label>Source page<input type='number' min={1} value={item.page ?? ''} onChange={e => med(i, { page: e.target.value ? Number(e.target.value) : null })} /></label>
    </fieldset>)}
    <ErrorNotice error={save.error} /><label className='check'><input type='checkbox' checked={reviewed} onChange={e => setReviewed(e.target.checked)} /> I checked the selected values and medication instructions against the source.</label>
    <div className='actions'><button disabled={save.isPending} onClick={() => save.mutate(false)}>Save corrections</button><button className='primary' disabled={!reviewed || save.isPending || (!selectedObs.length && !selectedMeds.length)} onClick={() => save.mutate(true)}>{save.isPending ? 'Saving…' : 'Confirm selected records'}</button></div>
  </section>
}

function SummaryView({ id, status }: { id: string; status: string }) {
  const client = useQueryClient()
  const [language, setLanguage] = useState('en')
  const summary = useQuery({ queryKey: ['summary', id, language], queryFn: () => api.summary(id, language), retry: false, refetchInterval: ['queued', 'processing'].includes(status) ? 2000 : false })
  const regenerate = useMutation({ mutationFn: () => api.generate(id), onSuccess: () => { client.invalidateQueries({ queryKey: ['summary', id] }); client.invalidateQueries({ queryKey: ['documents'] }) } })
  return <section className='panel'><div className='section-heading'><h2>Document summary</h2><label>Language<select value={language} onChange={e => setLanguage(e.target.value)}><option value='en'>English</option><option value='ta'>தமிழ்</option></select></label></div>
    <ErrorNotice error={regenerate.error} />{summary.data ? <div lang={language}><ul className='findings'>{summary.data.key_findings.map((finding, i) => <li key={i}>{finding}</li>)}</ul><Sources citations={summary.data.citations} /><p className='fine-print'>{summary.data.safety_disclaimer}</p></div> : <Empty>{summary.isPending ? 'Loading summary…' : ['queued', 'processing'].includes(status) ? 'Generating summary. Reviewed records remain available.' : summary.error instanceof Error ? summary.error.message : 'No summary yet.'}</Empty>}
    <div className='actions'><button disabled={regenerate.isPending || ['queued', 'processing'].includes(status)} onClick={() => regenerate.mutate()}>Generate / retry summary</button><small>English + Tamil · {status.replaceAll('_', ' ')}</small></div></section>
}

export function Documents() {
  const client = useQueryClient()
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<string | null>(null)
  const [view, setView] = useState<'review' | 'summary'>('review')
  const documents = useQuery({ queryKey: ['documents', offset], queryFn: () => api.documents(offset), refetchInterval: query => query.state.data?.some(d => [d.processing_status, d.summary_status, d.index_status].some(s => ['queued', 'processing'].includes(s))) ? 2000 : false })
  const extraction = useQuery({ queryKey: ['extraction', selected], queryFn: () => api.extraction(selected!), enabled: !!selected && view === 'review', retry: false })
  const upload = useMutation({ mutationFn: api.upload, onSuccess: () => client.invalidateQueries({ queryKey: ['documents'] }) })
  const action = useMutation({ mutationFn: async ({ id, kind }: { id: string; kind: 'delete' | 'retry' | 'index' }) => {
    if (kind === 'delete') await api.remove(id); else if (kind === 'retry') await api.retry(id); else await api.index(id)
    return { id, kind }
  }, onSuccess: ({ id, kind }) => { if (kind === 'delete' && selected === id) setSelected(null); client.invalidateQueries() } })
  function onUpload(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const file = (event.currentTarget.elements.namedItem('document') as HTMLInputElement).files?.[0]; if (file) { upload.mutate(file); event.currentTarget.reset() } }
  const selectedDoc = documents.data?.find(d => d.id === selected)
  return <><div className='page-heading'><div><p className='eyebrow'>DOCUMENT WORKSPACE</p><h1>Documents & review</h1><p>Upload the original. Verify the results. Build a reliable history.</p></div></div>
    <form className='upload-box' onSubmit={onUpload}><Upload size={26} /><div><label htmlFor='document-upload'>Add a laboratory report or prescription</label><p>PDF, JPG, or PNG · up to 15 MB. Scans use Sarvam when processing consent is enabled.</p><input id='document-upload' name='document' type='file' accept='application/pdf,image/jpeg,image/png' required /></div><button className='primary' disabled={upload.isPending}>{upload.isPending ? 'Uploading…' : 'Upload document'}</button></form><ErrorNotice error={upload.error || action.error || documents.error} />
    <section className='panel'><div className='section-heading'><h2>Your documents</h2><button onClick={() => documents.refetch()}>Refresh</button></div>
    {documents.isPending ? <Empty>Loading documents…</Empty> : !documents.data?.length ? <Empty>No documents on this page. Upload your first record to get started.</Empty> : <div className='table-wrap'><table><thead><tr><th>Document</th><th>Status</th><th>AI processing</th><th>Actions</th></tr></thead><tbody>{documents.data.map(doc => <tr key={doc.id}><td><strong>{doc.original_filename}</strong><small>{dateLabel(doc.document_date)} · {doc.document_type.replaceAll('_', ' ')}</small>{doc.error_message && <small className='error-text'>{doc.error_message}</small>}</td><td><Status value={doc.processing_status} /></td><td><small>Index: {doc.index_status.replaceAll('_', ' ')}</small><small>Summary: {doc.summary_status.replaceAll('_', ' ')}</small></td><td><div className='row-actions'><a className='button' aria-label={'View ' + doc.original_filename} href={'/api/v1/documents/' + doc.id + '/file'} target='_blank' rel='noreferrer'><FileText size={15} /> View</a>{['awaiting_review', 'completed'].includes(doc.processing_status) && <button onClick={() => { setSelected(doc.id); setView('review') }}>Review</button>}{doc.processing_status === 'completed' && <button onClick={() => { setSelected(doc.id); setView('summary') }}>Summary</button>}{doc.processing_status === 'failed' && <button disabled={action.isPending} onClick={() => action.mutate({ id: doc.id, kind: 'retry' })}>Retry extraction</button>}{['failed', 'consent_required', 'not_requested'].includes(doc.index_status) && doc.processing_status === 'completed' && <button disabled={action.isPending} onClick={() => action.mutate({ id: doc.id, kind: 'index' })}>Index / retry search</button>}<button className='danger' aria-label={'Delete ' + doc.original_filename} disabled={action.isPending} onClick={() => { if (window.confirm('Delete this document and its derived records?')) action.mutate({ id: doc.id, kind: 'delete' }) }}><Trash2 size={15} /></button></div></td></tr>)}</tbody></table></div>}
    <div className='actions'><button disabled={offset === 0} onClick={() => { setOffset(Math.max(0, offset - 50)); setSelected(null) }}>Previous</button><span>Page {offset / 50 + 1}</span><button disabled={(documents.data?.length ?? 0) < 50} onClick={() => { setOffset(offset + 50); setSelected(null) }}>Next</button></div></section>
    {selected && <><div className='section-heading'><h2>{selectedDoc?.original_filename}</h2><button onClick={() => setSelected(null)}>Close</button></div>{view === 'review' ? extraction.data ? <Review key={selected + ':' + extraction.data.revision} extraction={extraction.data} onComplete={() => setView('summary')} /> : <section className='panel'><ErrorNotice error={extraction.error} /><Empty>{extraction.isPending ? 'Loading extraction…' : 'Extraction is unavailable. Check document status.'}</Empty></section> : <SummaryView id={selected} status={selectedDoc?.summary_status ?? 'not_requested'} />}</>}
  </>
}
