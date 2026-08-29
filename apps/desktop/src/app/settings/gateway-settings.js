import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useStore } from '@nanostores/react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tip } from '@/components/ui/tooltip';
import { useI18n } from '@/i18n';
import { ExternalLink } from '@/lib/external-link';
import { AlertCircle, Check, Cloud, FileText, Globe, HelpCircle, Loader2, LogIn, Monitor, RefreshCw } from '@/lib/icons';
import { selectableCardClass } from '@/lib/selectable-card';
import { cn } from '@/lib/utils';
import { previewGatewaySwitch } from '@/store/gateway-switch';
import { notify, notifyError } from '@/store/notifications';
import { $profiles, refreshActiveProfile } from '@/store/profile';
import { CONTROL_TEXT } from './constants';
import { EmptyState, ListRow, LoadingState, Pill, SettingsContent } from './primitives';
const EMPTY_STATE = {
    envOverride: false,
    mode: 'local',
    remoteAuthMode: 'token',
    remoteOauthConnected: false,
    remoteTokenPreview: null,
    remoteTokenSet: false,
    remoteUrl: '',
    cloudOrg: ''
};
function ModeCard({ active, description, disabled, hint, icon: Icon, onSelect, title }) {
    return (_jsxs("button", { className: cn('flex h-full min-h-0 w-full flex-col p-3 text-left disabled:cursor-not-allowed disabled:opacity-50', selectableCardClass({ active, prominent: true })), disabled: disabled, onClick: onSelect, type: "button", children: [_jsxs("div", { className: "flex items-center gap-1.5", children: [_jsx(Icon, { className: "size-3.5 shrink-0 text-muted-foreground" }), _jsx("span", { className: "min-w-0 text-[length:var(--conversation-text-font-size)] font-medium", children: title }), hint ? (_jsx(Tip, { label: hint, children: _jsx("span", { className: "grid size-3.5 shrink-0 cursor-help place-items-center text-(--ui-text-tertiary) hover:text-(--ui-text-secondary)", onClick: event => event.stopPropagation(), children: _jsx(HelpCircle, { className: "size-3.5" }) }) })) : null, active ? _jsx(Check, { className: "ml-auto size-3.5 shrink-0 text-primary" }) : null] }), _jsx("p", { className: "mt-1.5 flex-1 text-[length:var(--conversation-caption-font-size)] leading-(--conversation-caption-line-height) text-(--ui-text-tertiary)", children: description })] }));
}
function ScopeChip({ active, label, onSelect }) {
    return (_jsx("button", { className: cn('rounded-full border px-3 py-1 text-[length:var(--conversation-caption-font-size)] transition', active
            ? 'border-(--ui-stroke-secondary) bg-(--ui-bg-tertiary) text-(--ui-text-primary)'
            : 'border-(--ui-stroke-tertiary) bg-(--ui-bg-quinary) text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover)'), onClick: onSelect, type: "button", children: label }));
}
export function GatewaySettings() {
    const { t } = useI18n();
    const g = t.settings.gateway;
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [testing, setTesting] = useState(false);
    const [previewingSwitch, setPreviewingSwitch] = useState(false);
    const [signingIn, setSigningIn] = useState(false);
    const [state, setState] = useState(EMPTY_STATE);
    const [remoteToken, setRemoteToken] = useState('');
    const [lastTest, setLastTest] = useState(null);
    // --- Vaelis Cloud (cloud mode) state ---
    // One portal session powers discovery + the silent per-agent cascade. These
    // track the cloud panel: whether we're signed in, the discovered agent list,
    // and which agent is mid-connect.
    const [cloudSignedIn, setCloudSignedIn] = useState(false);
    const [cloudSigningIn, setCloudSigningIn] = useState(false);
    const [cloudAgents, setCloudAgents] = useState([]);
    const [cloudDiscover, setCloudDiscover] = useState('idle');
    const [cloudConnectingId, setCloudConnectingId] = useState(null);
    // Multi-org users: when discovery returns needsOrgSelection, we hold the org
    // list here and show a picker. `cloudOrg` is the chosen org slug/id (null =
    // not yet chosen / single-org user).
    const [cloudOrgs, setCloudOrgs] = useState([]);
    const [cloudOrg, setCloudOrgState] = useState(null);
    // Mirror the selected org into a ref so connect reads the CURRENT value, not a
    // value captured in a stale render closure. discoverCloud() resolves the org
    // asynchronously (from the NAS response) and a user can click Connect in the
    // same render tick; without the ref, connectCloudAgent could persist a null
    // org even though discovery just resolved one. Always set both together.
    const cloudOrgRef = useRef(null);
    const setCloudOrg = (value) => {
        cloudOrgRef.current = value;
        setCloudOrgState(value);
    };
    // Connection scope: null = the global/default connection (the original
    // behavior); a profile name = that profile's per-profile remote override, so
    // each profile can point at its own backend.
    const [scope, setScope] = useState(null);
    const profiles = useStore($profiles);
    useEffect(() => {
        void refreshActiveProfile();
    }, []);
    // Auth-mode probe: as the user types a remote URL we ask the gateway (via
    // its public /api/status) whether it gates with OAuth or a static session
    // token, so we can show the right control (login button vs token box).
    const [probeStatus, setProbeStatus] = useState('idle');
    const [probe, setProbe] = useState(null);
    const probeSeq = useRef(0);
    useEffect(() => {
        let cancelled = false;
        const desktop = window.hermesDesktop;
        if (!desktop?.getConnectionConfig) {
            setLoading(false);
            return () => void (cancelled = true);
        }
        setLoading(true);
        // Clear scope-local entry state so a token from one scope can't leak into
        // the next when switching profiles.
        setRemoteToken('');
        setLastTest(null);
        desktop
            .getConnectionConfig(scope)
            .then(config => {
            if (cancelled) {
                return;
            }
            setState(config);
        })
            .catch(err => notifyError(err, g.failedLoad))
            .finally(() => {
            if (!cancelled) {
                setLoading(false);
            }
        });
        return () => void (cancelled = true);
        // eslint-disable-next-line react-hooks/exhaustive-deps -- reload on scope change only; copy is stable
    }, [scope]);
    // Debounced probe of the entered remote URL. Only runs in remote mode with a
    // syntactically plausible URL. The probe result drives whether we render the
    // OAuth login button or the session-token entry box. The effective auth mode
    // prefers a fresh probe result over the saved value.
    const trimmedUrl = state.remoteUrl.trim();
    // The dashboardUrl of the currently-connected cloud instance (the saved
    // cloud connection's remoteUrl), normalized for comparison against each
    // discovered agent's dashboardUrl so we can highlight the active one and hide
    // its Connect button. Empty unless the saved connection is a cloud one.
    // The saved cloud URL was stored via the main-side normalizeRemoteBaseUrl
    // (which lowercases the host through URL.toString()), but a discovered agent's
    // dashboardUrl arrives raw from NAS — so normalize both sides the same way
    // (trim, drop trailing slash, lowercase) or a host-casing difference would
    // silently break the connected-highlight.
    const normalizeCloudUrl = (url) => url.trim().replace(/\/+$/, '').toLowerCase();
    const connectedCloudUrl = state.mode === 'cloud' ? normalizeCloudUrl(state.remoteUrl) : '';
    const isConnectedAgent = (agent) => Boolean(connectedCloudUrl && agent.dashboardUrl && normalizeCloudUrl(agent.dashboardUrl) === connectedCloudUrl);
    useEffect(() => {
        if (state.mode !== 'remote' || !trimmedUrl || !/^https?:\/\//i.test(trimmedUrl)) {
            setProbeStatus('idle');
            setProbe(null);
            return;
        }
        const desktop = window.hermesDesktop;
        if (!desktop?.probeConnectionConfig) {
            return;
        }
        const seq = ++probeSeq.current;
        setProbeStatus('probing');
        const timer = setTimeout(() => {
            desktop
                .probeConnectionConfig(trimmedUrl)
                .then(result => {
                if (seq !== probeSeq.current) {
                    return;
                }
                setProbe(result);
                setProbeStatus(result.reachable ? 'done' : 'error');
            })
                .catch(() => {
                if (seq !== probeSeq.current) {
                    return;
                }
                setProbe(null);
                setProbeStatus('error');
            });
        }, 500);
        return () => clearTimeout(timer);
    }, [state.mode, trimmedUrl]);
    // Effective auth mode: a reachable probe wins; otherwise fall back to the
    // saved config's mode so a re-open of settings doesn't flicker.
    const authMode = useMemo(() => {
        if (probeStatus === 'done' && probe && probe.authMode !== 'unknown') {
            return probe.authMode;
        }
        return state.remoteAuthMode;
    }, [probe, probeStatus, state.remoteAuthMode]);
    // Whether we actually KNOW how this gateway authenticates yet. Until we do,
    // neither the OAuth button nor the session-token box should render —
    // `authMode` defaults to 'token', so without this gate the token box flashes
    // for every gateway (including OAuth ones) during the idle/probing window
    // before the first probe lands. The scheme is known when either:
    //   * the live probe finished (probeStatus 'done'), or
    //   * we're idle but showing a previously-saved remote config (re-opening
    //     settings for a gateway already signed-in or with a saved token), so
    //     its control appears immediately with no flicker.
    // While probing (or after a probe error), the scheme is unknown and we show
    // the probe status row instead of a control.
    const hasSavedRemote = state.remoteTokenSet || state.remoteOauthConnected;
    const authResolved = useMemo(() => {
        if (probeStatus === 'done') {
            return true;
        }
        return probeStatus === 'idle' && hasSavedRemote;
    }, [probeStatus, hasSavedRemote]);
    const providerLabel = useMemo(() => {
        const providers = probe?.providers ?? [];
        if (providers.length === 1) {
            return providers[0].displayName || providers[0].name;
        }
        if (providers.length > 1) {
            return providers.map(p => p.displayName || p.name).join(' / ');
        }
        return t.boot.failure.identityProvider;
    }, [probe, t.boot.failure.identityProvider]);
    // A username/password gateway authenticates through a credential form on the
    // gateway's /login page (POST /auth/password-login) rather than an OAuth
    // redirect. Everything downstream — the session cookie, the ws-ticket mint,
    // the persistent partition — is identical, so the desktop drives it through
    // the same sign-in window; only the button copy changes. We treat the
    // gateway as password-style only when EVERY advertised provider supports
    // password, so a mixed deployment keeps the generic OAuth copy.
    const isPasswordProvider = useMemo(() => {
        const providers = probe?.providers ?? [];
        return providers.length > 0 && providers.every(p => p.supportsPassword);
    }, [probe]);
    // The 'default' profile uses the global ("All profiles") connection, so the
    // per-profile scopes are the named, non-default profiles.
    const namedProfiles = useMemo(() => profiles.filter(profile => profile.name !== 'default'), [profiles]);
    const oauthConnected = state.remoteOauthConnected;
    const canUseRemote = useMemo(() => {
        if (!trimmedUrl) {
            return false;
        }
        if (authMode === 'oauth') {
            return oauthConnected;
        }
        return Boolean(remoteToken.trim()) || state.remoteTokenSet;
    }, [authMode, oauthConnected, remoteToken, state.remoteTokenSet, trimmedUrl]);
    const payload = () => ({
        mode: state.mode,
        profile: scope ?? undefined,
        remoteAuthMode: authMode,
        remoteToken: authMode === 'token' ? remoteToken.trim() || undefined : undefined,
        remoteUrl: trimmedUrl
    });
    const save = async (apply) => {
        if (state.mode === 'remote' && !canUseRemote) {
            notify({
                kind: 'warning',
                title: g.incompleteTitle,
                message: authMode === 'oauth' ? g.incompleteSignIn : g.incompleteToken
            });
            return;
        }
        setSaving(true);
        try {
            const next = apply
                ? await window.hermesDesktop.applyConnectionConfig(payload())
                : await window.hermesDesktop.saveConnectionConfig(payload());
            setState(next);
            setRemoteToken('');
            notify({
                kind: 'success',
                title: apply ? g.restartingTitle : g.savedTitle,
                message: apply ? g.restartingMessage : g.savedMessage
            });
        }
        catch (err) {
            notifyError(err, apply ? g.applyFailed : g.saveFailed);
        }
        finally {
            setSaving(false);
        }
    };
    // OAuth sign-in: persist the URL + oauth mode first (so the saved config has
    // the URL the login window needs), then open the gateway login window and
    // refresh the connection status from the saved config once it completes.
    const signIn = async () => {
        if (!trimmedUrl) {
            notify({ kind: 'warning', title: g.incompleteTitle, message: g.enterUrlFirst });
            return;
        }
        setSigningIn(true);
        try {
            // Save (don't apply/restart) so the login window has a URL to use and the
            // oauth mode is persisted, without yet flipping the live connection.
            const saved = await window.hermesDesktop.saveConnectionConfig({
                mode: state.mode,
                profile: scope ?? undefined,
                remoteAuthMode: 'oauth',
                remoteUrl: trimmedUrl
            });
            setState(saved);
            const result = await window.hermesDesktop.oauthLoginConnectionConfig(trimmedUrl);
            if (result.connected) {
                const refreshed = await window.hermesDesktop.getConnectionConfig(scope);
                setState(refreshed);
                notify({ kind: 'success', title: g.signedIn, message: g.connectedTo(providerLabel) });
            }
            else {
                notify({
                    kind: 'warning',
                    title: t.boot.failure.signInIncompleteTitle,
                    message: t.boot.failure.signInIncompleteMessage
                });
            }
        }
        catch (err) {
            notifyError(err, g.signInFailed);
        }
        finally {
            setSigningIn(false);
        }
    };
    const signOut = async () => {
        setSigningIn(true);
        try {
            await window.hermesDesktop.oauthLogoutConnectionConfig(trimmedUrl || undefined);
            const refreshed = await window.hermesDesktop.getConnectionConfig(scope);
            setState(refreshed);
            notify({ kind: 'success', title: g.signedOutTitle, message: g.signedOutMessage });
        }
        catch (err) {
            notifyError(err, g.signOutFailed);
        }
        finally {
            setSigningIn(false);
        }
    };
    // --- Vaelis Cloud handlers ---
    // Pull the discovered agent list over the shared portal session. Tolerant of
    // a lapsed session: a needsCloudLogin error flips us back to signed-out.
    // `org` scopes discovery for multi-org users; when discovery comes back with
    // needsOrgSelection we surface the org list and show a picker instead.
    const discoverCloud = async (org) => {
        const desktop = window.hermesDesktop;
        if (!desktop?.cloud) {
            return;
        }
        setCloudDiscover('loading');
        try {
            const result = await desktop.cloud.discover(org);
            if ('needsOrgSelection' in result && result.needsOrgSelection) {
                // Multi-org user with no org chosen yet: show the picker. Don't clear a
                // previously-chosen org list on a refresh.
                setCloudOrgs(result.orgs);
                setCloudAgents([]);
                setCloudDiscover('done');
                return;
            }
            // Single org (or org now chosen): we have agents.
            setCloudAgents('agents' in result ? result.agents : []);
            // Record the org AUTHORITATIVELY from the response (NAS echoes the org the
            // list was scoped to), falling back to the org we requested. This is what
            // gets persisted on connect, so it must be set even on single-membership
            // auto-resolve where no picker ran and no `org` arg was passed.
            const resolvedOrgRef = 'org' in result && result.org ? (result.org.slug ?? result.org.id) : null;
            if (resolvedOrgRef) {
                setCloudOrg(resolvedOrgRef);
            }
            else if (org) {
                setCloudOrg(org);
            }
            setCloudDiscover('done');
        }
        catch (err) {
            setCloudAgents([]);
            setCloudDiscover('error');
            // A lapsed/absent portal session means we're effectively signed out.
            if (err && typeof err === 'object' && 'needsCloudLogin' in err) {
                setCloudSignedIn(false);
            }
            notifyError(err, g.cloudDiscoverFailed);
        }
    };
    // User picked an org from the multi-org picker: remember it and re-run
    // discovery scoped to it.
    const selectCloudOrg = (org) => {
        const ref = org.slug ?? org.id;
        setCloudOrg(ref);
        void discoverCloud(ref);
    };
    // "Change org": clear the selected org and re-discover with no org arg. A
    // multi-org user gets NAS's 409 → the picker; a single-org user auto-resolves
    // back to their one org. Also clear the agent list so the current org's
    // agents don't linger under the picker while discovery re-runs.
    const changeCloudOrg = () => {
        setCloudOrg(null);
        setCloudAgents([]);
        void discoverCloud();
    };
    // On entering cloud mode (or scope change), read the portal session status and
    // auto-discover when already signed in, so the picker is populated on open.
    useEffect(() => {
        if (state.mode !== 'cloud') {
            return;
        }
        const desktop = window.hermesDesktop;
        if (!desktop?.cloud) {
            return;
        }
        let cancelled = false;
        desktop.cloud
            .status()
            .then(status => {
            if (cancelled) {
                return;
            }
            setCloudSignedIn(status.signedIn);
            if (status.signedIn) {
                // Restore the persisted org (if any) so we reopen straight into that
                // org's agent list instead of the picker; discoverCloud(org) also
                // records it as the selected org. Empty → normal discovery (single-org
                // resolves automatically; multi-org shows the picker).
                const savedOrg = state.cloudOrg || '';
                if (savedOrg) {
                    setCloudOrg(savedOrg);
                }
                void discoverCloud(savedOrg || undefined);
            }
            else {
                setCloudAgents([]);
                setCloudOrgs([]);
                setCloudOrg(null);
                setCloudDiscover('idle');
            }
        })
            .catch(() => {
            if (!cancelled) {
                setCloudSignedIn(false);
            }
        });
        return () => void (cancelled = true);
        // eslint-disable-next-line react-hooks/exhaustive-deps -- reload on mode/scope change only
    }, [state.mode, scope]);
    const cloudSignIn = async () => {
        const desktop = window.hermesDesktop;
        if (!desktop?.cloud) {
            return;
        }
        setCloudSigningIn(true);
        try {
            const result = await desktop.cloud.login();
            setCloudSignedIn(result.signedIn);
            if (result.signedIn) {
                await discoverCloud();
            }
        }
        catch (err) {
            notifyError(err, g.cloudSignInFailed);
        }
        finally {
            setCloudSigningIn(false);
        }
    };
    const cloudSignOut = async () => {
        const desktop = window.hermesDesktop;
        if (!desktop?.cloud) {
            return;
        }
        setCloudSigningIn(true);
        try {
            await desktop.cloud.logout();
            setCloudSignedIn(false);
            setCloudAgents([]);
            setCloudOrgs([]);
            setCloudOrg(null);
            setCloudDiscover('idle');
            notify({ kind: 'success', title: g.cloudSignedOutTitle, message: g.cloudSignedOutMessage });
        }
        catch (err) {
            notifyError(err, g.signOutFailed);
        }
        finally {
            setCloudSigningIn(false);
        }
    };
    // Select a discovered agent: drive the silent per-agent cascade (no second
    // prompt — the shared portal session auto-approves), then persist a cloud-mode
    // connection pointed at its dashboardUrl and apply it (soft-reconnects in place).
    const connectCloudAgent = async (agent) => {
        if (!agent.dashboardUrl) {
            return;
        }
        const desktop = window.hermesDesktop;
        if (!desktop?.cloud) {
            return;
        }
        setCloudConnectingId(agent.id);
        try {
            const result = await desktop.cloud.agentSignIn(agent.dashboardUrl);
            if (!result.connected) {
                notify({
                    kind: 'warning',
                    title: t.boot.failure.signInIncompleteTitle,
                    message: t.boot.failure.signInIncompleteMessage
                });
                return;
            }
            // Persist a cloud-mode connection (remote-shaped, oauth) and soft-reconnect.
            // Include the selected org so Settings reopens into the same org + instance.
            // Read the REF (not the cloudOrg state) so a just-resolved org from
            // discovery in this same render tick is captured, not a stale null.
            const next = await desktop.applyConnectionConfig({
                mode: 'cloud',
                profile: scope ?? undefined,
                remoteAuthMode: 'oauth',
                remoteUrl: agent.dashboardUrl,
                cloudOrg: cloudOrgRef.current ?? undefined
            });
            setState(next);
            notify({ kind: 'success', title: g.cloudConnectedTitle, message: g.cloudConnectedTo(agent.name) });
        }
        catch (err) {
            if (err && typeof err === 'object' && 'needsCloudLogin' in err) {
                setCloudSignedIn(false);
            }
            notifyError(err, g.cloudConnectFailed);
        }
        finally {
            setCloudConnectingId(null);
        }
    };
    const testRemote = async () => {
        if (!canUseRemote) {
            notify({
                kind: 'warning',
                title: g.incompleteTitle,
                message: authMode === 'oauth' ? g.incompleteSignInTest : g.incompleteTokenTest
            });
            return;
        }
        setTesting(true);
        setLastTest(null);
        try {
            const result = await window.hermesDesktop.testConnectionConfig({
                mode: 'remote',
                profile: scope ?? undefined,
                remoteAuthMode: authMode,
                remoteToken: authMode === 'token' ? remoteToken.trim() || undefined : undefined,
                remoteUrl: trimmedUrl
            });
            const message = g.connectedTo(result.baseUrl, result.version ?? undefined);
            setLastTest(message);
            notify({ kind: 'success', title: g.reachableTitle, message });
        }
        catch (err) {
            notifyError(err, g.testFailed);
        }
        finally {
            setTesting(false);
        }
    };
    if (loading) {
        return _jsx(LoadingState, { label: g.loading });
    }
    if (!window.hermesDesktop?.getConnectionConfig) {
        return _jsx(EmptyState, { description: g.unavailableDesc, title: g.unavailableTitle });
    }
    return (_jsxs(SettingsContent, { children: [_jsxs("div", { className: "mb-5", children: [_jsxs("div", { className: "flex items-center gap-2 text-[length:var(--conversation-text-font-size)] font-medium", children: [_jsx(Globe, { className: "size-4 text-muted-foreground" }), g.title, state.envOverride ? _jsx(Pill, { tone: "primary", children: g.envOverride }) : null] }), _jsx("p", { className: "mt-2 max-w-2xl text-[length:var(--conversation-caption-font-size)] leading-(--conversation-caption-line-height) text-(--ui-text-tertiary)", children: g.intro })] }), namedProfiles.length > 0 ? (_jsxs("div", { className: "mb-5 grid gap-2", children: [_jsx("div", { className: "text-[length:var(--conversation-caption-font-size)] font-medium text-(--ui-text-secondary)", children: g.appliesTo }), _jsxs("div", { className: "flex flex-wrap gap-1.5", children: [_jsx(ScopeChip, { active: scope === null, label: g.allProfiles, onSelect: () => setScope(null) }), namedProfiles.map(profile => (_jsx(ScopeChip, { active: scope === profile.name, label: profile.name, onSelect: () => setScope(profile.name) }, profile.name)))] }), _jsx("p", { className: "text-[length:var(--conversation-caption-font-size)] leading-(--conversation-caption-line-height) text-(--ui-text-tertiary)", children: scope === null ? g.defaultConnection : g.profileConnection(scope) })] })) : null, state.envOverride ? (_jsxs("div", { className: "mb-5 flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-[length:var(--conversation-caption-font-size)] text-destructive", children: [_jsx(AlertCircle, { className: "mt-0.5 size-4 shrink-0" }), _jsxs("div", { children: [_jsx("div", { className: "font-medium", children: g.envOverrideTitle }), _jsx("div", { className: "mt-1 leading-5", children: g.envOverrideDesc })] })] })) : null, _jsxs("div", { className: "mb-5 grid gap-2", children: [_jsx("div", { className: "text-[length:var(--conversation-caption-font-size)] font-medium text-(--ui-text-secondary)", children: g.modeTitle }), _jsxs("div", { className: "grid auto-rows-fr grid-cols-1 gap-2 min-[42rem]:grid-cols-3", children: [_jsx(ModeCard, { active: state.mode === 'local', description: g.localDesc, disabled: state.envOverride, icon: Monitor, onSelect: () => setState(current => ({ ...current, mode: 'local' })), title: g.localTitle }), _jsx(ModeCard, { active: state.mode === 'cloud', description: g.cloudDesc, disabled: state.envOverride, icon: Cloud, onSelect: () => setState(current => ({ ...current, mode: 'cloud' })), title: g.cloudTitle }), _jsx(ModeCard, { active: state.mode === 'remote', description: g.remoteDesc, disabled: state.envOverride, hint: g.remoteAuthHint, icon: Globe, onSelect: () => setState(current => ({ ...current, mode: 'remote' })), title: g.remoteTitle })] })] }), state.mode === 'cloud' && !state.envOverride ? (_jsxs("div", { className: "mt-5 grid gap-1", children: [_jsx(ListRow, { action: cloudSignedIn ? (_jsxs("div", { className: "flex items-center gap-2", children: [_jsxs(Pill, { tone: "primary", children: [_jsx(Check, { className: "size-3" }), " ", g.cloudSignedIn] }), _jsxs(Button, { disabled: cloudSigningIn, onClick: () => void cloudSignOut(), variant: "outline", children: [cloudSigningIn ? _jsx(Loader2, { className: "animate-spin" }) : null, g.signOut] })] })) : (_jsxs(Button, { disabled: cloudSigningIn, onClick: () => void cloudSignIn(), children: [cloudSigningIn ? _jsx(Loader2, { className: "animate-spin" }) : _jsx(LogIn, {}), g.cloudSignIn] })), description: cloudSignedIn ? g.cloudSignedInDesc : g.cloudNeedsSignIn, title: g.cloudSignInTitle }), cloudSignedIn ? (cloudOrgs.length > 0 && !cloudOrg ? (_jsxs("div", { className: "mt-3", children: [_jsx("div", { className: "mb-2 text-[length:var(--conversation-caption-font-size)] font-medium text-(--ui-text-secondary)", children: g.cloudOrgPickerTitle }), _jsx("div", { className: "grid gap-1", children: cloudOrgs.map(orgEntry => (_jsx(ListRow, { action: _jsx(Button, { onClick: () => selectCloudOrg(orgEntry), size: "sm", children: g.cloudOrgSelect }), description: g.cloudOrgRole(orgEntry.role), title: orgEntry.name }, orgEntry.id))) })] })) : (_jsxs("div", { className: "mt-3", children: [_jsxs("div", { className: "mb-2 flex items-center justify-between", children: [_jsx("div", { className: "text-[length:var(--conversation-caption-font-size)] font-medium text-(--ui-text-secondary)", children: g.cloudAgentsTitle }), _jsxs("div", { className: "flex items-center gap-2", children: [cloudOrg ? (_jsx(Button, { onClick: () => changeCloudOrg(), size: "sm", variant: "text", children: g.cloudOrgChange })) : null, _jsxs(Button, { disabled: cloudDiscover === 'loading', onClick: () => void discoverCloud(cloudOrg ?? undefined), size: "sm", variant: "text", children: [cloudDiscover === 'loading' ? _jsx(Loader2, { className: "animate-spin" }) : _jsx(RefreshCw, {}), g.cloudRefresh] })] })] }), cloudDiscover === 'loading' ? (_jsxs("div", { className: "flex items-center gap-2 py-3 text-[length:var(--conversation-caption-font-size)] text-(--ui-text-tertiary)", children: [_jsx(Loader2, { className: "size-4 animate-spin" }), g.cloudLoadingAgents] })) : cloudAgents.length === 0 ? (_jsxs("div", { className: "flex items-start gap-2 py-3 text-[length:var(--conversation-caption-font-size)] text-(--ui-text-tertiary)", children: [_jsx(AlertCircle, { className: "mt-0.5 size-4 shrink-0" }), _jsxs("span", { children: [g.cloudNoAgents.before, _jsx(ExternalLink, { href: "https://portal.nousresearch.com/agents", showExternalIcon: false, children: g.cloudNoAgents.linkText }), g.cloudNoAgents.after] })] })) : (_jsx("div", { className: "grid gap-1", children: cloudAgents.map(agent => {
                                    const connected = isConnectedAgent(agent);
                                    return (_jsx("div", { className: cn('rounded-md px-2', connected && 'bg-primary/5 ring-1 ring-primary/25'), children: _jsx(ListRow, { action: connected ? (_jsxs(Pill, { tone: "primary", children: [_jsx(Check, { className: "mr-1 inline size-3" }), g.cloudConnectedPill] })) : (_jsxs(Button, { disabled: !agent.dashboardUrl || cloudConnectingId !== null, onClick: () => void connectCloudAgent(agent), size: "sm", children: [cloudConnectingId === agent.id ? _jsx(Loader2, { className: "animate-spin" }) : null, agent.dashboardUrl
                                                        ? cloudConnectingId === agent.id
                                                            ? g.cloudConnecting
                                                            : g.cloudConnect
                                                        : g.cloudAgentProvisioning] })), description: g.cloudStatusLabel(agent.dashboardGatewayState), title: agent.name }) }, agent.id));
                                }) }))] }))) : null] })) : null, state.mode === 'remote' && !state.envOverride ? (_jsxs("div", { className: "mt-5 grid gap-1", children: [_jsx(ListRow, { action: _jsx(Input, { className: cn('h-8', CONTROL_TEXT), disabled: state.envOverride, onChange: event => setState(current => ({ ...current, remoteUrl: event.target.value })), placeholder: "https://gateway.example.com/hermes", value: state.remoteUrl }), description: g.remoteUrlDesc, title: g.remoteUrlTitle }), state.mode === 'remote' && probeStatus === 'probing' ? (_jsxs("div", { className: "flex items-center gap-2 py-3 text-[length:var(--conversation-caption-font-size)] text-(--ui-text-tertiary)", children: [_jsx(Loader2, { className: "size-4 animate-spin" }), g.probing] })) : null, state.mode === 'remote' && probeStatus === 'error' ? (_jsxs("div", { className: "flex items-start gap-2 py-3 text-[length:var(--conversation-caption-font-size)] text-(--ui-text-tertiary)", children: [_jsx(AlertCircle, { className: "mt-0.5 size-4 shrink-0" }), g.probeError] })) : null, state.mode === 'remote' && authResolved && authMode === 'oauth' ? (_jsx(ListRow, { action: oauthConnected ? (_jsxs("div", { className: "flex items-center gap-2", children: [_jsxs(Pill, { tone: "primary", children: [_jsx(Check, { className: "size-3" }), " ", g.signedIn] }), _jsxs(Button, { disabled: signingIn || state.envOverride, onClick: () => void signOut(), variant: "outline", children: [signingIn ? _jsx(Loader2, { className: "animate-spin" }) : null, g.signOut] })] })) : (_jsxs(Button, { disabled: signingIn || state.envOverride || !trimmedUrl, onClick: () => void signIn(), children: [signingIn ? _jsx(Loader2, { className: "animate-spin" }) : _jsx(LogIn, {}), isPasswordProvider ? g.signIn : g.signInWith(providerLabel)] })), description: oauthConnected
                            ? isPasswordProvider
                                ? g.authSignedInPassword
                                : g.authSignedInOauth
                            : isPasswordProvider
                                ? g.authNeedsPassword
                                : g.authNeedsOauth(providerLabel), title: g.authTitle })) : null, state.mode === 'remote' && authResolved && authMode === 'token' ? (_jsx(ListRow, { action: _jsx(Input, { autoComplete: "off", className: cn('h-8 font-mono', CONTROL_TEXT), disabled: state.envOverride, onChange: event => setRemoteToken(event.target.value), placeholder: state.remoteTokenSet
                                ? g.existingToken(state.remoteTokenPreview ?? g.savedToken)
                                : g.pasteSessionToken, type: "password", value: remoteToken }), description: g.tokenDesc, title: g.tokenTitle })) : null] })) : null, lastTest ? _jsx("div", { className: "mt-4 text-xs text-primary", children: lastTest }) : null, state.mode !== 'cloud' ? (_jsxs("div", { className: "mt-6 flex flex-wrap items-center justify-end gap-4", children: [state.mode === 'remote' ? (_jsxs(Button, { className: "mr-auto", disabled: state.envOverride || testing || !canUseRemote, onClick: () => void testRemote(), size: "sm", variant: "text", children: [testing ? _jsx(Loader2, { className: "animate-spin" }) : null, g.testRemote] })) : null, _jsx(Button, { disabled: state.envOverride || saving, onClick: () => void save(false), size: "sm", variant: "textStrong", children: g.saveForRestart }), _jsxs(Button, { disabled: state.envOverride || saving, onClick: () => void save(true), size: "sm", children: [saving ? _jsx(Loader2, { className: "animate-spin" }) : null, g.saveAndReconnect] })] })) : null, _jsxs("div", { className: "mt-6 grid gap-1", children: [_jsx(ListRow, { action: _jsxs(Button, { onClick: () => void window.hermesDesktop?.revealLogs(), size: "sm", variant: "textStrong", children: [_jsx(FileText, {}), g.openLogs] }), description: g.diagnosticsDesc, title: g.diagnostics }), import.meta.env.DEV ? (_jsx(ListRow, { action: _jsxs(Button, { disabled: previewingSwitch, onClick: () => {
                                setPreviewingSwitch(true);
                                void previewGatewaySwitch().finally(() => setPreviewingSwitch(false));
                            }, size: "sm", variant: "textStrong", children: [previewingSwitch ? _jsx(Loader2, { className: "animate-spin" }) : null, "Preview soft switch"] }), description: "Wipe session lists so sidebar skeletons retrigger \u2014 no real backend teardown.", title: "Dev \u00B7 soft switch" })) : null] })] }));
}
