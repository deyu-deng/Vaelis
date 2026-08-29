import { jsx as _jsx, Fragment as _Fragment, jsxs as _jsxs } from "react/jsx-runtime";
import { Tooltip as TooltipPrimitive } from 'radix-ui';
import { cn } from '@/lib/utils';
function TooltipProvider({ delayDuration = 0, 
// Tips are labels, not interactive surfaces. Hoverable content + Radix's
// pointer-grace bridge is what leaves tips stuck open — especially over
// Electron `-webkit-app-region: drag` chrome where pointermove never fires
// to clear the grace area. Default off so open state tracks the trigger only.
disableHoverableContent = true, ...props }) {
    return (_jsx(TooltipPrimitive.Provider, { "data-slot": "tooltip-provider", delayDuration: delayDuration, disableHoverableContent: disableHoverableContent, ...props }));
}
function Tooltip({ ...props }) {
    return _jsx(TooltipPrimitive.Root, { "data-slot": "tooltip", ...props });
}
function TooltipTrigger({ ...props }) {
    return _jsx(TooltipPrimitive.Trigger, { "data-slot": "tooltip-trigger", ...props });
}
function TooltipContent({ className, sideOffset = 6, children, ...props }) {
    return (_jsx(TooltipPrimitive.Portal, { children: _jsx(TooltipPrimitive.Content
        // Transparent, width-capped wrapper. The visible chip is the inner inline
        // span so `box-decoration-break: clone` gives a marker-style background
        // that hugs EACH wrapped line (bg only on the text, ragged right — no
        // rectangular dead space). Instant, no transition (delayDuration=0).
        // pointer-events-none: the tip must never steal hover/clicks from the
        // chrome underneath (titlebar tools, adjacent tabs, etc.).
        , { 
            // Transparent, width-capped wrapper. The visible chip is the inner inline
            // span so `box-decoration-break: clone` gives a marker-style background
            // that hugs EACH wrapped line (bg only on the text, ragged right — no
            // rectangular dead space). Instant, no transition (delayDuration=0).
            // pointer-events-none: the tip must never steal hover/clicks from the
            // chrome underneath (titlebar tools, adjacent tabs, etc.).
            className: cn('pointer-events-none z-[200] w-fit max-w-64 select-none', className), "data-slot": "tooltip-content", sideOffset: sideOffset, ...props, children: _jsx("span", { className: "box-decoration-clone inline bg-foreground px-1.5 py-1 text-[11px] font-bold leading-normal text-background [font-family:Arial,sans-serif]", children: children }) }) }));
}
// Drop-in replacement for native `title=`: wrap any single element. Instant,
// position-aware, themed. Self-contained (carries its own Provider) so it works
// anywhere without a provider ancestor. Renders the child untouched when label
// is falsy. Open state is trigger-hover only — never sticky, never click-blocking.
function Tip({ label, children, delayDuration = 0, ...props }) {
    if (!label) {
        return _jsx(_Fragment, { children: children });
    }
    return (_jsx(TooltipProvider, { delayDuration: delayDuration, disableHoverableContent: true, children: _jsxs(Tooltip, { disableHoverableContent: true, children: [_jsx(TooltipTrigger, { asChild: true, children: children }), _jsx(TooltipContent, { ...props, children: label })] }) }));
}
export { Tip, Tooltip, TooltipContent, TooltipProvider, TooltipTrigger };
