'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

type Task = { id: string; title: string; due_date: string | null; status: string; source_url: string | null };
type Action = {
  title: string;
  confidence: number;
  rationale: string;
  kind: string;
  payload: { due_date?: string | null; source_url?: string | null };
};
type Approval = { id: string; action: Action; created_at: string };
type Audit = { event_type: string; created_at: string };
type Preference = 'interested' | 'not_interested' | null;
type Activity = { title: string; date: string; url: string; location: string; source: string; reason: string; preference: Preference; calendar_status?: 'available' | 'conflict'; calendar_conflicts?: { title: string; start: string }[] };
type Story = { title: string; url: string; source: string; topic: string; published_at: string; preference: Preference };
type Dashboard = { tasks: Task[]; completed_tasks: Task[]; approvals: Approval[]; audit: Audit[]; processed: number; feedback_count: number; activities: Activity[]; news: Story[] };

const API = 'http://127.0.0.1:8765';

export default function Home() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [selected, setSelected] = useState(0);
  const [title, setTitle] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [feedback, setFeedback] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [showCompleted, setShowCompleted] = useState(false);

  const load = useCallback(async () => {
    try {
      const response = await fetch(`${API}/api/dashboard`, { cache: 'no-store' });
      if (!response.ok) throw new Error('The local dashboard service did not respond.');
      setData(await response.json());
      setError('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to load assistant data.');
    }
  }, []);

  useEffect(() => { void load(); }, [load]);
  const approval = data?.approvals[selected] ?? null;
  useEffect(() => {
    setTitle(approval?.action.title ?? '');
    setDueDate(approval?.action.payload.due_date ?? '');
    setFeedback('');
  }, [approval?.id]);

  const resolve = async (decision: 'approve' | 'reject') => {
    if (!approval) return;
    setBusy(true);
    setError('');
    try {
      const response = await fetch(`${API}/api/approvals/${approval.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          decision,
          edited_title: decision === 'approve' ? title : null,
          edited_due_date: decision === 'approve' ? dueDate : null,
          feedback: feedback || null,
        }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? 'The decision could not be saved.');
      setSelected(0);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The decision could not be saved.');
    } finally {
      setBusy(false);
    }
  };

  const savePreference = async (contentType: 'news' | 'activity', item: Story | Activity, decision: Exclude<Preference, null>) => {
    setError('');
    try {
      const context = 'topic' in item ? item.topic : item.reason;
      const response = await fetch(`${API}/api/feedback/${contentType}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item_key: item.url, title: item.title, context, decision }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? 'Feedback could not be saved.');
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Feedback could not be saved.');
    }
  };

  const completeTask = async (task: Task) => {
    setError('');
    try {
      const response = await fetch(`${API}/api/tasks/${task.id}/complete`, { method: 'POST' });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? 'Task could not be completed.');
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Task could not be completed.');
    }
  };

  const reopenTask = async (task: Task) => {
    setError('');
    try {
      const response = await fetch(`${API}/api/tasks/${task.id}/reopen`, { method: 'POST' });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? 'Task could not be reopened.');
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Task could not be reopened.');
    }
  };

  const stats = useMemo(() => [
    { label: 'Open tasks', value: data?.tasks.length ?? '—' },
    { label: 'Needs review', value: data?.approvals.length ?? '—' },
    { label: 'Processed', value: data?.processed ?? '—' },
    { label: 'Learned examples', value: data?.feedback_count ?? '—' },
  ], [data]);

  return (
    <main className="min-h-screen bg-[#f4f1e9] text-[#19211d]">
      <header className="border-b border-[#dcd7ca] bg-[#f9f7f1]/90 px-5 py-5 backdrop-blur sm:px-10">
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-[#69736c]">Personal Assistant</p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight">Decision desk</h1>
          </div>
          <div className="flex items-center gap-2 rounded-full border border-[#d7d2c6] bg-white px-3 py-2 text-xs font-medium text-[#526058]">
            <span className="h-2 w-2 rounded-full bg-[#4e8c69]" /> Local & private
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-6xl gap-8 px-5 py-8 sm:px-10 lg:grid-cols-[minmax(0,1fr)_300px]">
        <section>
          <div className="mb-7 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {stats.map((item) => (
              <div key={item.label} className="rounded-2xl border border-[#ded9ce] bg-[#fbfaf6] p-4 shadow-sm">
                <p className="text-2xl font-semibold">{item.value}</p>
                <p className="mt-1 text-xs font-medium text-[#69736c]">{item.label}</p>
              </div>
            ))}
          </div>

          {error && <div role="alert" className="mb-5 rounded-xl border border-[#dba99d] bg-[#fff1ed] px-4 py-3 text-sm text-[#80483b]">{error}</div>}

          <div className="mb-5 flex items-end justify-between">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#8a6b36]">Review queue</p>
              <h2 className="mt-1 text-3xl font-semibold tracking-tight">One decision at a time</h2>
            </div>
            <span className="text-sm text-[#6d766f]">{approval ? `${selected + 1} of ${data?.approvals.length}` : 'All clear'}</span>
          </div>

          {approval ? (
            <article className="overflow-hidden rounded-[28px] border border-[#d9d4c7] bg-[#fffdf8] shadow-[0_20px_60px_rgba(44,50,45,0.08)]">
              <div className="border-b border-[#e8e3d8] px-6 py-5 sm:px-8">
                <div className="flex items-center justify-between gap-4">
                  <span className="rounded-full bg-[#f2e8d1] px-3 py-1 text-xs font-bold text-[#7a5927]">{Math.round(approval.action.confidence * 100)}% confidence</span>
                  <span className="text-xs text-[#7b827d]">{approval.action.kind.replaceAll('_', ' ')}</span>
                </div>
                <h3 className="mt-5 text-2xl font-semibold tracking-tight">{approval.action.title}</h3>
                <p className="mt-3 max-w-2xl text-sm leading-6 text-[#5e6861]">{approval.action.rationale}</p>
                {approval.action.payload.source_url && (
                  <a className="mt-4 inline-block text-sm font-semibold text-[#315f46] underline decoration-[#9bb7a5] underline-offset-4" href={approval.action.payload.source_url} target="_blank" rel="noreferrer">Open source email</a>
                )}
              </div>
              <div className="grid gap-5 px-6 py-6 sm:grid-cols-2 sm:px-8">
                <label className="text-xs font-bold uppercase tracking-[0.12em] text-[#69736c]">Task title
                  <input className="mt-2 w-full rounded-xl border border-[#d8d3c8] bg-white px-4 py-3 text-sm font-medium normal-case tracking-normal outline-none focus:border-[#447057]" value={title} onChange={(event) => setTitle(event.target.value)} />
                </label>
                <label className="text-xs font-bold uppercase tracking-[0.12em] text-[#69736c]">Due date
                  <input type="date" className="mt-2 w-full rounded-xl border border-[#d8d3c8] bg-white px-4 py-3 text-sm font-medium normal-case tracking-normal outline-none focus:border-[#447057]" value={dueDate} onChange={(event) => setDueDate(event.target.value)} />
                </label>
                <label className="text-xs font-bold uppercase tracking-[0.12em] text-[#69736c] sm:col-span-2">Optional feedback
                  <input className="mt-2 w-full rounded-xl border border-[#d8d3c8] bg-white px-4 py-3 text-sm font-medium normal-case tracking-normal outline-none focus:border-[#447057]" placeholder="Why was this right or wrong?" value={feedback} onChange={(event) => setFeedback(event.target.value)} />
                </label>
              </div>
              <div className="flex flex-col-reverse gap-3 border-t border-[#e8e3d8] bg-[#faf8f2] px-6 py-5 sm:flex-row sm:justify-between sm:px-8">
                <div className="flex gap-2">
                  <button disabled={selected === 0 || busy} onClick={() => setSelected((value) => value - 1)} className="rounded-xl border border-[#d4cfc4] px-4 py-3 text-sm font-semibold disabled:opacity-35">Previous</button>
                  <button disabled={selected >= (data?.approvals.length ?? 1) - 1 || busy} onClick={() => setSelected((value) => value + 1)} className="rounded-xl border border-[#d4cfc4] px-4 py-3 text-sm font-semibold disabled:opacity-35">Next</button>
                </div>
                <div className="flex gap-3">
                  <button disabled={busy} onClick={() => void resolve('reject')} className="rounded-xl border border-[#cabfb4] px-5 py-3 text-sm font-semibold text-[#714d45] hover:bg-[#f6ece8] disabled:opacity-50">Reject</button>
                  <button disabled={busy || !title.trim()} onClick={() => void resolve('approve')} className="rounded-xl bg-[#244e38] px-5 py-3 text-sm font-semibold text-white shadow-sm hover:bg-[#193f2b] disabled:opacity-50">{busy ? 'Saving…' : 'Approve task'}</button>
                </div>
              </div>
            </article>
          ) : (
            <div className="rounded-[28px] border border-[#ced9d1] bg-[#f8fcf8] px-8 py-16 text-center">
              <div className="mx-auto mb-4 h-12 w-12 rounded-full bg-[#dceadf] text-2xl leading-[48px] text-[#315f46]">✓</div>
              <h3 className="text-xl font-semibold">No decisions waiting</h3>
              <p className="mt-2 text-sm text-[#68716b]">New uncertain actions will appear here after the next inbox run.</p>
            </div>
          )}

          <div className="mt-10">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#8a6b36]">Today’s digest</p>
            <h2 className="mt-1 text-3xl font-semibold tracking-tight">News worth your time</h2>
            <p className="mt-2 text-sm text-[#69736c]">Arts, AI, cats, food, and lighter Seattle stories—all linked to their sources.</p>
            <div className="mt-5 grid gap-3">
              {data?.news.map((story) => (
                <div key={`${story.topic}-${story.title}`} className="group flex gap-4 rounded-2xl border border-[#d9d4c7] bg-[#fffdf8] p-5 shadow-sm transition hover:shadow-md">
                  <span className="h-fit shrink-0 rounded-full bg-[#f2e8d1] px-3 py-1 text-xs font-bold text-[#7a5927]">{story.topic}</span>
                  <div className="min-w-0 flex-1">
                    <a href={story.url} target="_blank" rel="noreferrer" className="font-semibold leading-6 group-hover:text-[#315f46]">{story.title}</a>
                    <p className="mt-1 text-xs text-[#7b827d]">{story.source} · {new Date(story.published_at).toLocaleDateString()}</p>
                    <div className="mt-3 flex gap-2">
                      <button onClick={() => void savePreference('news', story, 'interested')} className={`rounded-full px-3 py-1.5 text-xs font-semibold ${story.preference === 'interested' ? 'bg-[#244e38] text-white' : 'border border-[#cfc9bc]'}`}>Interested</button>
                      <button onClick={() => void savePreference('news', story, 'not_interested')} className={`rounded-full px-3 py-1.5 text-xs font-semibold ${story.preference === 'not_interested' ? 'bg-[#714d45] text-white' : 'border border-[#cfc9bc]'}`}>Not interested</button>
                    </div>
                  </div>
                </div>
              ))}
              {data?.news.length === 0 && (
                <div className="rounded-2xl border border-dashed border-[#cfc9bc] p-6 text-sm text-[#69736c]">Run the daily news workflow to create your first digest.</div>
              )}
            </div>
          </div>

          <div className="mt-10">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#315f46]">Weekend discovery</p>
            <h2 className="mt-1 text-3xl font-semibold tracking-tight">Activities for Nora &amp; Ozan</h2>
            <p className="mt-2 text-sm text-[#69736c]">Live matches from trusted local sources for the coming two months.</p>
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              {data?.activities.map((activity) => (
                <div key={`${activity.date}-${activity.title}`} className="rounded-2xl border border-[#d9d4c7] bg-[#fffdf8] p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md">
                  <div className="flex items-start justify-between gap-3">
                    <a href={activity.url} target="_blank" rel="noreferrer" className="text-lg font-semibold leading-6 hover:text-[#315f46]">{activity.title}</a>
                    <span className="shrink-0 rounded-full bg-[#dfece2] px-2.5 py-1 text-xs font-bold text-[#315f46]">{activity.date}</span>
                  </div>
                  <p className="mt-3 text-sm font-medium text-[#5e6861]">{activity.location}</p>
                  <p className="mt-2 text-xs leading-5 text-[#7b827d]">{activity.reason}</p>
                  {activity.calendar_status && (
                    <p className={`mt-3 rounded-lg px-3 py-2 text-xs font-semibold ${activity.calendar_status === 'conflict' ? 'bg-[#fff1ed] text-[#80483b]' : 'bg-[#eef6ef] text-[#315f46]'}`}>
                      {activity.calendar_status === 'conflict'
                        ? `Calendar conflict: ${activity.calendar_conflicts?.map((item) => item.title).join(', ') || 'Busy'}`
                        : 'No calendar conflict found'}
                    </p>
                  )}
                  <div className="mt-4 flex gap-2">
                    <button onClick={() => void savePreference('activity', activity, 'interested')} className={`rounded-full px-3 py-1.5 text-xs font-semibold ${activity.preference === 'interested' ? 'bg-[#244e38] text-white' : 'border border-[#cfc9bc]'}`}>Interested</button>
                    <button onClick={() => void savePreference('activity', activity, 'not_interested')} className={`rounded-full px-3 py-1.5 text-xs font-semibold ${activity.preference === 'not_interested' ? 'bg-[#714d45] text-white' : 'border border-[#cfc9bc]'}`}>Not interested</button>
                  </div>
                </div>
              ))}
              {data?.activities.length === 0 && (
                <div className="rounded-2xl border border-dashed border-[#cfc9bc] p-6 text-sm text-[#69736c] sm:col-span-2">No strong weekend matches found in the latest search.</div>
              )}
            </div>
          </div>
        </section>

        <aside className="space-y-4">
          <div className="rounded-2xl border border-[#ddd8cd] bg-[#fbfaf6] p-5">
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#69736c]">Open tasks</p>
              <button onClick={() => setShowCompleted((value) => !value)} className="text-xs font-semibold text-[#315f46] underline decoration-[#9bb7a5] underline-offset-4">{showCompleted ? 'Hide completed' : 'Show completed'}</button>
            </div>
            <div className="mt-4 space-y-4">
              {data?.tasks.map((task) => (
                <div key={task.id} className="flex gap-3 border-b border-[#e5e1d7] pb-4 last:border-0 last:pb-0">
                  <button aria-label={`Mark ${task.title} complete`} title="Mark complete" onClick={() => void completeTask(task)} className="mt-0.5 h-5 w-5 shrink-0 rounded-md border-2 border-[#9ca69f] bg-white hover:border-[#315f46] hover:bg-[#eef6ef]" />
                  <div>
                    <p className="text-sm font-semibold leading-5">{task.title}</p>
                    <p className="mt-1 text-xs text-[#79817b]">{task.due_date ? `Due ${task.due_date}` : 'No due date'} · {task.status}</p>
                    {task.source_url && <a href={task.source_url} target="_blank" rel="noreferrer" className="mt-2 inline-block text-xs font-semibold text-[#315f46] underline decoration-[#9bb7a5] underline-offset-4">Open email</a>}
                  </div>
                </div>
              ))}
              {data?.tasks.length === 0 && <p className="text-sm text-[#79817b]">No open tasks.</p>}
            </div>
            {showCompleted && (
              <div className="mt-5 border-t border-[#d9d4c7] pt-4">
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-[#8a928d]">Recently completed</p>
                <div className="mt-3 space-y-3">
                  {data?.completed_tasks.map((task) => (
                    <div key={task.id} className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-sm text-[#7b827d] line-through">{task.title}</p>
                        {task.source_url && <a href={task.source_url} target="_blank" rel="noreferrer" className="mt-1 inline-block text-xs font-semibold text-[#315f46] underline decoration-[#9bb7a5] underline-offset-4">Open email</a>}
                      </div>
                      <button onClick={() => void reopenTask(task)} className="shrink-0 rounded-lg border border-[#cfc9bc] px-2.5 py-1.5 text-xs font-semibold text-[#315f46] hover:bg-[#eef6ef]">Reopen</button>
                    </div>
                  ))}
                  {data?.completed_tasks.length === 0 && <p className="text-sm text-[#8a928d]">Nothing completed yet.</p>}
                </div>
              </div>
            )}
          </div>
          <div className="rounded-2xl bg-[#1f3027] p-5 text-[#f5f3ed]">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#b7c5bc]">Safety rule</p>
            <p className="mt-3 text-sm leading-6">Calendar changes and permanent memories always wait for confirmation.</p>
          </div>
        </aside>
      </div>
    </main>
  );
}
