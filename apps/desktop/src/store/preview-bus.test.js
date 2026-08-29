import { beforeEach, describe, expect, it, vi } from 'vitest';
vi.mock('./preview', () => ({
    setCurrentSessionPreviewTarget: vi.fn(),
    setPreviewTarget: vi.fn()
}));
vi.mock('./panes', () => ({
    setPaneOpen: vi.fn()
}));
vi.mock('./layout', () => ({
    PREVIEW_PANE_ID: 'preview',
    RIGHT_RAIL_PREVIEW_TAB_ID: 'preview-live',
    selectRightRailTab: vi.fn()
}));
import { setPaneOpen } from './panes';
import { selectRightRailTab } from './layout';
import { $previewBusItems, applyHighestPriorityPreview, openPreviewPanelManual, pushPreviewBusItem } from './preview-bus';
import { setCurrentSessionPreviewTarget } from './preview';
describe('preview-bus', () => {
    beforeEach(() => {
        $previewBusItems.set([]);
        vi.clearAllMocks();
    });
    it('sorts artifact before progress and resource', () => {
        pushPreviewBusItem({ title: 'r', priority: 'resource', autoOpen: false });
        pushPreviewBusItem({ title: 'a', priority: 'artifact', autoOpen: false });
        pushPreviewBusItem({ title: 'p', priority: 'progress', autoOpen: false });
        expect($previewBusItems.get().map(i => i.title)).toEqual(['a', 'p', 'r']);
    });
    it('auto-opens artifact into session preview', () => {
        pushPreviewBusItem({
            title: 'out.html',
            priority: 'artifact',
            kind: 'file',
            path: 'D:/tmp/out.html',
            autoOpen: true
        });
        expect(setCurrentSessionPreviewTarget).toHaveBeenCalled();
    });
    it('openPreviewPanelManual opens the rail', () => {
        openPreviewPanelManual();
        expect(setPaneOpen).toHaveBeenCalledWith('preview', true);
        expect(selectRightRailTab).toHaveBeenCalled();
    });
    it('applyHighestPriorityPreview prefers artifact', () => {
        $previewBusItems.set([
            { title: 'r', priority: 'resource' },
            { title: 'a', priority: 'artifact', path: 'D:/a.md', kind: 'file' }
        ]);
        const hit = applyHighestPriorityPreview();
        expect(hit?.title).toBe('a');
    });
});
