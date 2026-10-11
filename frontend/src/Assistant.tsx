import { useState, type FormEvent } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, type Patient } from './api'
import { Empty, ErrorNotice, Sources, Status } from './ui'

export function Assistant({ patient }: { patient: Patient }) {
  const client = useQueryClient()
  const [selected, setSelected] = useState<string | null>(null)
  const [question, setQuestion] = useState('')
  const [language, setLanguage] = useState(patient.preferred_language)
  const conversations = useQuery({ queryKey: ['conversations'], queryFn: api.conversations })
  const conversationId = selected ?? conversations.data?.[0]?.id
  const messages = useQuery({ queryKey: ['messages', conversationId], queryFn: () => api.messages(conversationId!), enabled: !!conversationId })
  const create = useMutation({ mutationFn: api.conversation, onSuccess: conversation => { setSelected(conversation.id); client.invalidateQueries({ queryKey: ['conversations'] }) } })
  const send = useMutation({ mutationFn: async () => {
    const id = conversationId ?? (await api.conversation()).id
    setSelected(id)
    return { id, message: await api.ask(id, question, language) }
  }, onSuccess: ({ id }) => { setQuestion(''); client.invalidateQueries({ queryKey: ['messages', id] }); client.invalidateQueries({ queryKey: ['conversations'] }) }, onError: () => client.invalidateQueries({ queryKey: ['messages'] }) })
  function submit(event: FormEvent) { event.preventDefault(); if (question.trim()) send.mutate() }
  return <><div className='page-heading'><div><p className='eyebrow'>EVIDENCE FROM YOUR RECORDS</p><h1>Health assistant</h1><p>Ask about reviewed results, prescriptions, and changes over time.</p></div><button disabled={create.isPending || send.isPending} onClick={() => create.mutate()}>New conversation</button></div>
    {!patient.external_ai_consent && <div className='notice'>Enable external AI processing in <a href='#profile'>Profile & consent</a> to use Laya decisions, record search, and generated answers.</div>}
    <ErrorNotice error={conversations.error || messages.error || send.error || create.error} />
    <div className='conversation-picker'><label>Conversation<select disabled={send.isPending} value={conversationId ?? ''} onChange={e => setSelected(e.target.value)}><option value='' disabled>Start a conversation</option>{conversations.data?.map(c => <option key={c.id} value={c.id}>{c.title} · {new Date(c.created_at + 'Z').toLocaleString()}</option>)}</select></label></div>
    <section className='panel chat'><div className='chat-history' aria-live='polite'>
      {!messages.data?.length && <Empty>Your assistant answers using cited, confirmed records. Try “What were my latest HbA1c results?” or “What changed between my glucose reports?”</Empty>}
      {messages.data?.map(message => <article key={message.id} className={'message ' + message.role} lang={message.data.language}><strong>{message.role === 'user' ? 'You' : 'Health Copilot'}</strong>{message.data.status && <Status value={message.data.status} />}<p>{message.data.question ?? message.data.answer}</p>{message.data.citations?.length ? <Sources citations={message.data.citations} /> : null}{message.data.safety_disclaimer && <small>{message.data.safety_disclaimer}</small>}</article>)}
      {send.isPending && <p className='notice' role='status'>Checking reviewed evidence and generating a cited answer…</p>}
    </div><form onSubmit={submit} className='composer'><label htmlFor='question'>Your question<textarea id='question' rows={3} maxLength={1000} required value={question} placeholder='Ask a specific question about your reviewed records…' onChange={e => setQuestion(e.target.value)} disabled={send.isPending} /></label><div className='actions'><label>Answer language<select value={language} onChange={e => setLanguage(e.target.value as 'en' | 'ta')}><option value='en'>English</option><option value='ta'>தமிழ்</option></select></label><button className='primary' disabled={send.isPending || !question.trim() || !patient.external_ai_consent}>Ask about my records</button></div></form></section>
  </>
}
