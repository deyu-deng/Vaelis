import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useStore } from '@nanostores/react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { PageLoader } from '@/components/page-loader';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { confirmAgendaEvent, createAgendaEvent, deleteAgendaEvent, dismissAgendaEvent, getAgenda, updateAgendaEvent } from '@/hermes';
import { useI18n } from '@/i18n';
import { $agendaError, $agendaEvents, $agendaLoading, $agendaPendingCount, $agendaSelected, removeAgendaEvent, setAgendaError, setAgendaEvents, setAgendaLoading, setAgendaSelectedId, upsertAgendaEvent } from '@/store/agenda';
import { notify, notifyError } from '@/store/notifications';
import { Panel, PanelAction, PanelAddButton, PanelBlock, PanelBody, PanelDetail, PanelEmpty, PanelHeader, PanelList, PanelListRow, PanelMeta, PanelPill, PanelRowMenu, PanelSectionLabel } from '../overlays/panel';
// Board refresh cadence. The spec allows up to 10s staleness (ADR-0008), and
// polling keeps us off SSE/WebSocket plumbing for a single-user desktop.
const POLL_INTERVAL_MS = 8000;
const KINDS = ['meeting', 'ddl', 'class', 'task'];
const STATUS_TONE = {
    cancelled: 'muted',
    confirmed: 'good',
    pending: 'warn'
};
const STATUS_DOT = {
    cancelled: 'bg-muted-foreground/40',
    confirmed: 'bg-emerald-500',
    pending: 'bg-amber-500'
};
function startOfToday() {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}
/** Backend speaks naive local ISO strings; keep the desktop on the same shape. */
function toLocalIso(date) {
    const pad = (value) => String(value).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:00`;
}
function toInputValue(iso) {
    return iso.length >= 16 ? iso.slice(0, 16) : iso;
}
function fromInputValue(value) {
    return value.length === 16 ? `${value}:00` : value;
}
function clockOf(iso) {
    return iso.length >= 16 ? iso.slice(11, 16) : iso;
}
function dayKeyOf(iso) {
    return iso.slice(0, 10);
}
function dayLabel(dayKey, a) {
    const today = toLocalIso(startOfToday()).slice(0, 10);
    const tomorrowDate = startOfToday();
    tomorrowDate.setDate(tomorrowDate.getDate() + 1);
    const tomorrow = toLocalIso(tomorrowDate).slice(0, 10);
    if (dayKey === today) {
        return a.today;
    }
    if (dayKey === tomorrow) {
        return a.tomorrow;
    }
    return dayKey;
}
function isDeleted(value) {
    return typeof value === 'object' && value !== null && 'deleted' in value;
}
export function AgendaView({ onClose }) {
    const { t } = useI18n();
    const a = t.agenda;
    const events = useStore($agendaEvents);
    const loading = useStore($agendaLoading);
    const error = useStore($agendaError);
    const selected = useStore($agendaSelected);
    const pendingCount = useStore($agendaPendingCount);
    const [editor, setEditor] = useState({ mode: 'closed' });
    const [busyId, setBusyId] = useState(null);
    const refresh = useCallback(async () => {
        try {
            const rows = await getAgenda();
            setAgendaEvents(rows);
            setAgendaError(null);
        }
        catch (cause) {
            setAgendaError(cause instanceof Error ? cause.message : String(cause));
        }
        finally {
            setAgendaLoading(false);
        }
    }, []);
    useEffect(() => {
        void refresh();
        const intervalId = window.setInterval(() => {
            if (document.visibilityState === 'visible') {
                void refresh();
            }
        }, POLL_INTERVAL_MS);
        return () => window.clearInterval(intervalId);
    }, [refresh]);
    const grouped = useMemo(() => {
        const buckets = new Map();
        for (const event of events) {
            const key = dayKeyOf(event.start_at);
            const bucket = buckets.get(key);
            if (bucket) {
                bucket.push(event);
            }
            else {
                buckets.set(key, [event]);
            }
        }
        return [...buckets.entries()].sort(([left], [right]) => left.localeCompare(right));
    }, [events]);
    async function handleConfirm(event) {
        setBusyId(event.id);
        try {
            upsertAgendaEvent(await confirmAgendaEvent(event.id));
            notify({ message: a.confirmed });
        }
        catch (cause) {
            notifyError(cause, a.actionFailed);
        }
        finally {
            setBusyId(null);
        }
    }
    async function handleDismiss(event) {
        setBusyId(event.id);
        try {
            const result = await dismissAgendaEvent(event.id);
            if (isDeleted(result)) {
                removeAgendaEvent(event.id);
            }
            else {
                upsertAgendaEvent(result);
            }
            notify({ message: a.dismissed });
        }
        catch (cause) {
            notifyError(cause, a.actionFailed);
        }
        finally {
            setBusyId(null);
        }
    }
    async function handleDelete(event) {
        setBusyId(event.id);
        try {
            await deleteAgendaEvent(event.id);
            removeAgendaEvent(event.id);
            notify({ message: a.deleted });
        }
        catch (cause) {
            notifyError(cause, a.actionFailed);
        }
        finally {
            setBusyId(null);
        }
    }
    async function handleEditorSave(values) {
        if (editor.mode === 'edit' && editor.event) {
            upsertAgendaEvent(await updateAgendaEvent(editor.event.id, {
                kind: values.kind,
                start_at: values.startAt,
                title: values.title
            }));
        }
        else {
            const created = await createAgendaEvent({
                kind: values.kind,
                start_at: values.startAt,
                title: values.title
            });
            upsertAgendaEvent(created);
            setAgendaSelectedId(created.id);
        }
        setEditor({ mode: 'closed' });
    }
    return (_jsxs(Panel, { closeLabel: a.close, onClose: onClose, children: [loading && events.length === 0 ? (_jsx(PageLoader, { label: a.loading })) : error && events.length === 0 ? (_jsx(PanelEmpty, { description: error, icon: "warning", title: a.loadFailed })) : events.length === 0 ? (_jsx(PanelEmpty, { action: _jsx(Button, { onClick: () => setEditor({ mode: 'create' }), size: "sm", children: a.newEvent }), description: a.emptyDesc, icon: "calendar", title: a.emptyTitle })) : (_jsxs(_Fragment, { children: [_jsx(PanelHeader, { subtitle: pendingCount > 0 ? a.pendingCount(pendingCount) : a.count(events.length), title: a.title }), _jsxs(PanelBody, { children: [_jsxs(PanelList, { children: [grouped.map(([dayKey, dayEvents]) => (_jsxs("div", { children: [_jsx(PanelSectionLabel, { className: "px-2 pb-1 pt-2", children: dayLabel(dayKey, a) }), dayEvents.map(event => (_jsx(PanelListRow, { active: selected?.id === event.id, dotClassName: STATUS_DOT[event.status] ?? 'bg-muted-foreground', menu: _jsx(PanelRowMenu, { items: [
                                                        { icon: 'edit', label: a.edit, onSelect: () => setEditor({ event, mode: 'edit' }) },
                                                        {
                                                            icon: 'trash',
                                                            label: t.common.delete,
                                                            onSelect: () => void handleDelete(event),
                                                            tone: 'danger'
                                                        }
                                                    ] }), meta: clockOf(event.start_at), onSelect: () => setAgendaSelectedId(event.id), rowKey: event.id, title: event.title }, event.id)))] }, dayKey))), _jsx(PanelAddButton, { label: a.newEvent, onClick: () => setEditor({ mode: 'create' }) })] }), selected ? (_jsx(AgendaDetail, { a: a, busy: busyId === selected.id, event: selected, onConfirm: () => void handleConfirm(selected), onDismiss: () => void handleDismiss(selected), onEdit: () => setEditor({ event: selected, mode: 'edit' }) })) : (_jsx(PanelEmpty, { description: a.emptyDesc, icon: "calendar" }))] })] })), _jsx(AgendaEditorDialog, { a: a, editor: editor, onClose: () => setEditor({ mode: 'closed' }), onSave: handleEditorSave })] }));
}
function AgendaDetail({ a, busy, event, onConfirm, onDismiss, onEdit }) {
    const isPending = event.status === 'pending';
    const previous = event.prev_value;
    return (_jsxs(PanelDetail, { children: [_jsxs("header", { className: "space-y-3", children: [_jsxs("div", { className: "flex flex-wrap items-start justify-between gap-3", children: [_jsxs("div", { className: "flex min-w-0 flex-wrap items-center gap-2", children: [_jsx("h3", { className: "text-[0.95rem] font-semibold tracking-tight text-foreground", children: event.title }), _jsx(PanelPill, { tone: STATUS_TONE[event.status] ?? 'muted', children: a.statuses[event.status] })] }), _jsx("div", { className: "flex shrink-0 items-center gap-0.5", children: isPending ? (_jsxs(_Fragment, { children: [_jsx(PanelAction, { disabled: busy, icon: "check", onClick: onConfirm, children: a.confirm }), _jsx(PanelAction, { disabled: busy, icon: "discard", onClick: onDismiss, children: a.dismiss })] })) : (_jsx(PanelAction, { disabled: busy, icon: "edit", onClick: onEdit, children: a.edit })) })] }), _jsx(PanelMeta, { rows: [
                            { label: a.startLabel, value: event.start_at.replace('T', ' ') },
                            { label: a.kindLabel, value: a.kinds[event.kind] },
                            { label: a.sourceLabel, value: a.sources[event.source] }
                        ] })] }), isPending && previous ? (_jsxs("section", { className: "space-y-1.5", children: [_jsx(PanelSectionLabel, { children: a.changeLabel }), _jsx(PanelMeta, { rows: [
                            ...(previous.title && previous.title !== event.title
                                ? [{ label: a.titleField, value: `${previous.title} → ${event.title}` }]
                                : []),
                            ...(previous.start_at && previous.start_at !== event.start_at
                                ? [{ label: a.startLabel, value: `${previous.start_at.replace('T', ' ')} → ${event.start_at.replace('T', ' ')}` }]
                                : [])
                        ] })] })) : null, event.evidence?.snippet ? (_jsxs("section", { className: "space-y-1.5", children: [_jsx(PanelSectionLabel, { children: a.evidenceLabel }), _jsx(PanelBlock, { children: event.evidence.snippet })] })) : null] }));
}
function AgendaEditorDialog({ a, editor, onClose, onSave }) {
    const { t } = useI18n();
    const open = editor.mode !== 'closed';
    const initial = editor.mode === 'edit' ? editor.event : undefined;
    const [title, setTitle] = useState('');
    const [startAt, setStartAt] = useState('');
    const [kind, setKind] = useState('task');
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState(null);
    useEffect(() => {
        if (!open) {
            return;
        }
        const fallback = new Date();
        fallback.setMinutes(0, 0, 0);
        fallback.setHours(fallback.getHours() + 1);
        setTitle(initial?.title ?? '');
        setStartAt(toInputValue(initial?.start_at ?? toLocalIso(fallback)));
        setKind(initial?.kind ?? 'task');
        setError(null);
        setSaving(false);
    }, [initial, open]);
    async function handleSubmit(submitEvent) {
        submitEvent.preventDefault();
        if (!title.trim() || !startAt) {
            setError(a.titleTimeRequired);
            return;
        }
        setSaving(true);
        setError(null);
        try {
            await onSave({ kind, startAt: fromInputValue(startAt), title: title.trim() });
        }
        catch (cause) {
            setError(cause instanceof Error ? cause.message : String(cause));
            setSaving(false);
        }
    }
    return (_jsx(Dialog, { onOpenChange: value => !value && !saving && onClose(), open: open, children: _jsxs(DialogContent, { className: "max-w-md", children: [_jsx(DialogHeader, { children: _jsx(DialogTitle, { children: editor.mode === 'edit' ? a.editTitle : a.createTitle }) }), _jsxs("form", { className: "space-y-3", onSubmit: handleSubmit, children: [_jsx(Input, { "aria-label": a.titleField, onChange: changeEvent => setTitle(changeEvent.target.value), placeholder: a.titlePlaceholder, value: title }), _jsx(Input, { "aria-label": a.startLabel, onChange: changeEvent => setStartAt(changeEvent.target.value), type: "datetime-local", value: startAt }), _jsxs(Select, { onValueChange: value => setKind(value), value: kind, children: [_jsx(SelectTrigger, { "aria-label": a.kindLabel, children: _jsx(SelectValue, {}) }), _jsx(SelectContent, { children: KINDS.map(value => (_jsx(SelectItem, { value: value, children: a.kinds[value] }, value))) })] }), error ? _jsx("p", { className: "text-xs text-destructive", children: error }) : null, _jsxs(DialogFooter, { children: [_jsx(Button, { disabled: saving, onClick: onClose, type: "button", variant: "outline", children: t.common.cancel }), _jsx(Button, { disabled: saving, type: "submit", children: t.common.save })] })] })] }) }));
}
