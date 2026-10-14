'use client';

import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import {
  useDndContext,
  useDroppable,
  type KeyboardCoordinateGetter,
} from '@dnd-kit/core';
import { ChevronDown, ChevronRight } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import {
  blocks,
  canMove,
  groupParagraphs,
  moveBlocks,
  ungroupParagraphs,
  type BlockKind,
  type BlockLocation,
  type BlockTarget,
} from '@/lib/studio-blocks';
import { sameDocument } from '@/lib/offline-outbox';
import type { StudioDocument } from '@/lib/studio-types';

export interface EditorUi {
  document: StudioDocument;
  folded: string[];
  toggleFold: (id: string) => void;
  selectBlock: (id: string) => void;
  unfold: (ids: string[]) => void;
  direction: 'upright' | 'rotated' | 'horizontal';
  setDirection: (direction: EditorUi['direction']) => void;
  commit: (change: (document: StudioDocument) => void, kind?: string) => void;
}
interface Controls extends EditorUi {
  locations: ReadonlyMap<string, BlockLocation>;
  selecting: boolean;
  selected: string[];
  select: (id: string) => void;
  startMove: (ids: string[]) => void;
  notice: (text: string) => void;
}
const EditorContext = createContext<Controls | null>(null);
export function useEditorControls() {
  const value = useContext(EditorContext);
  if (!value)
    throw new Error('Writing block controls require the editor provider');
  return value;
}

export function EditorControls({
  ui,
  children,
}: {
  ui: EditorUi;
  children: ReactNode;
}) {
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [moving, setMoving] = useState<string[]>([]);
  const [targetId, setTargetId] = useState('');
  const [placement, setPlacement] =
    useState<BlockTarget['placement']>('inside');
  const [groupLabel, setGroupLabel] = useState('');
  const [notice, setNotice] = useState('');
  const index = useMemo(() => blocks(ui.document), [ui.document]);
  const locations = useMemo(() => new Map(index.map((item) => [item.id, item])), [index]);
  const selectedNodes = index.filter((item) => selected.includes(item.id));
  const startMove = (ids: string[]) => {
    setMoving(ids);
    setTargetId('');
    setPlacement('inside');
    setNotice('');
  };
  const select = (id: string) => {
    const kind = index.find((item) => item.id === id)?.kind;
    if (
      !selected.includes(id) &&
      selectedNodes.length &&
      kind !== selectedNodes[0].kind
    ) {
      setNotice('请多选同一种内容；可先结束当前多选再选择其他类型。');
      return;
    }
    setSelected((current) =>
      current.includes(id)
        ? current.filter((item) => item !== id)
        : [...current, id],
    );
  };
  const targets = index.filter((item) =>
    canMove(ui.document, moving, { kind: item.kind, id: item.id, placement }, locations),
  );
  const apply = (document: StudioDocument, kind: string) => {
    if (sameDocument(document, ui.document)) {
      setNotice('内容已在所选位置。');
      return;
    }
    ui.commit((draft) => Object.assign(draft, document), kind);
    setSelected([]);
  };
  const group = () => {
    try {
      apply(
        groupParagraphs(
          ui.document,
          selected,
          `paragraph_group_${crypto.randomUUID()}`,
          groupLabel.trim(),
        ),
        'GROUP_PARAGRAPHS',
      );
      setNotice('已将所选段落集中为一组，思想、引用和素材保留；可撤销。');
    } catch (error) {
      setNotice(
        error instanceof Error ? error.message : '分组失败，请重新选择。',
      );
    }
  };
  return (
    <EditorContext.Provider
      value={{
        ...ui,
        locations,
        selecting,
        selected,
        select,
        startMove,
        notice: setNotice,
      }}
    >
      <div className="structure-tools" aria-label="结构选择与移动">
        <Button
          size="sm"
          variant="ghost"
          aria-pressed={selecting}
          onClick={() => {
            setSelecting((value) => !value);
            setSelected([]);
          }}
        >
          {selecting ? '结束多选' : '多选／分组'}
        </Button>
        {selecting ? (
          <>
            <span>{selectedNodes.length} 项</span>
            <Button
              size="sm"
              variant="outline"
              disabled={!selectedNodes.length}
              onClick={() => startMove(selected)}
            >
              移动所选内容
            </Button>
            {selectedNodes.length &&
            selectedNodes.every((item) => item.kind === 'paragraph') ? (
              <>
                <Input
                  aria-label="新段落组标签"
                  placeholder="段落组用途…"
                  value={groupLabel}
                  onChange={(event) => setGroupLabel(event.target.value)}
                />
                <Button size="sm" variant="outline" onClick={group}>
                  集中为段落组
                </Button>
              </>
            ) : null}
          </>
        ) : null}
        <output aria-live="polite">{notice}</output>
      </div>
      {children}
      <Dialog
        open={moving.length > 0}
        onOpenChange={(value) => {
          if (!value) setMoving([]);
        }}
      >
        <DialogContent className="max-h-[85dvh] overflow-y-auto sm:max-w-xl">
          <DialogTitle>移动原内容</DialogTitle>
          <DialogDescription>
            选择正确的容器或前后位置。思想、引用、素材及原编号会一起移动，保存后可撤销。
          </DialogDescription>
          <div className="space-y-2">
            {index
              .filter((item) => moving.includes(item.id))
              .map((item) => (
                <p key={item.id}>{item.label}</p>
              ))}
          </div>
          <label className="grid gap-1">
            放置方式
            <select
              value={placement}
              onChange={(event) => {
                setPlacement(event.target.value as BlockTarget['placement']);
                setTargetId('');
              }}
            >
              <option value="inside">放入容器里面</option>
              <option value="before">放在目标前面</option>
              <option value="after">放在目标后面</option>
            </select>
          </label>
          <label className="grid gap-1">
            目标位置
            <select
              value={targetId}
              onChange={(event) => setTargetId(event.target.value)}
            >
              <option value="">选择目标…</option>
              {targets.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          {!targets.length ? (
            <p>当前方式没有合法目标。请选择同类型内容或切换放置方式。</p>
          ) : null}
          <output aria-live="polite">{notice}</output>
          <Button
            disabled={!targetId}
            onClick={() => {
              try {
                const target = targets.find((item) => item.id === targetId);
                if (!target) throw new Error('原目标已变化，请重新选择。');
                apply(
                  moveBlocks(ui.document, moving, {
                    kind: target.kind,
                    id: target.id,
                    placement,
                  }),
                  'MOVE_BLOCKS',
                );
                ui.unfold([target.id]);
                setMoving([]);
                setNotice('已移动原内容，引用和编号保留；可撤销。');
              } catch (error) {
                setNotice(
                  error instanceof Error
                    ? error.message
                    : '移动失败，请重新选择。',
                );
              }
            }}
          >
            移动到所选位置
          </Button>
        </DialogContent>
      </Dialog>
    </EditorContext.Provider>
  );
}

export function BlockControls({
  id,
  kind,
  label,
  children,
}: {
  id: string;
  kind: BlockKind;
  label: string;
  children: ReactNode;
}) {
  const ui = useEditorControls();
  const folded = ui.folded.includes(id);
  return (
    <div className="block-controls" onFocusCapture={() => ui.selectBlock(id)}>
      {ui.selecting ? (
        <Checkbox
          aria-label={`多选 ${label}`}
          checked={ui.selected.includes(id)}
          onCheckedChange={() => ui.select(id)}
        />
      ) : null}
      {children}
      {kind !== 'thought' ? (
        <button
          className="block-fold"
          type="button"
          aria-label={`${folded ? '展开' : '折叠'} ${label}`}
          aria-expanded={!folded}
          aria-controls={`body-${id}`}
          onClick={() => ui.toggleFold(id)}
        >
          {folded ? (
            <ChevronRight aria-hidden="true" />
          ) : (
            <ChevronDown aria-hidden="true" />
          )}
        </button>
      ) : null}
    </div>
  );
}

export function BlockMove({ id }: { id: string }) {
  const ui = useEditorControls();
  return (
    <button type="button" onClick={() => ui.startMove([id])}>
      移动原内容…
    </button>
  );
}

export function Ungroup({ id }: { id: string }) {
  const ui = useEditorControls();
  return (
    <button
      type="button"
      onClick={() => {
        try {
          const next = ungroupParagraphs(ui.document, id);
          ui.commit(
            (draft) => Object.assign(draft, next),
            'UNGROUP_PARAGRAPHS',
          );
          ui.notice('已解除分组，思想、引用和当前顺序保留；可撤销。');
        } catch (error) {
          ui.notice(error instanceof Error ? error.message : '原组已不可用。');
        }
      }}
    >
      解除分组，保留内容
    </button>
  );
}

export function DropZone({
  target,
  empty = false,
}: {
  target: BlockTarget;
  empty?: boolean;
}) {
  const ui = useEditorControls();
  const { active } = useDndContext();
  const activeId = active?.id;
  const { kind, id, placement } = target;
  const enabled = useMemo(
    () =>
      activeId !== undefined &&
      canMove(ui.document, [String(activeId)], { kind, id, placement }, ui.locations),
    [activeId, ui.document, ui.locations, kind, id, placement],
  );
  const { setNodeRef, isOver } = useDroppable({
    id: `drop-${target.kind}-${target.id}-${target.placement}`,
    disabled: !enabled,
    data: { dropTarget: target },
  });
  const label =
    ui.locations.get(target.id)?.label ||
    '原对象';
  const instruction =
    target.placement === 'inside'
      ? `放入 ${label} 里面`
      : `放在 ${label} ${target.placement === 'before' ? '前面' : '后面'}`;
  return (
    <div
      className={`structure-drop ${target.placement === 'inside' ? 'structure-drop--inside' : ''} ${empty ? 'structure-drop--empty' : ''}`}
    >
      <div
        ref={setNodeRef}
        className={`structure-drop__target ${enabled ? 'structure-drop__target--enabled' : ''} ${isOver ? 'structure-drop__target--over' : ''}`}
      >
        {isOver || (empty && target.placement === 'inside') ? (
          <span>{instruction}</span>
        ) : null}
      </div>
    </div>
  );
}

export const blockKeyboardCoordinates: KeyboardCoordinateGetter = (
  event,
  { currentCoordinates, context },
) => {
  if (
    !['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(event.code) ||
    !context.collisionRect
  )
    return;
  event.preventDefault();
  const rect = context.collisionRect;
  const center = {
    x: rect.left + rect.width / 2,
    y: rect.top + rect.height / 2,
  };
  const candidates = context.droppableContainers
    .getEnabled()
    .flatMap((item) => {
      if (!item.data.current?.dropTarget) return [];
      const candidate = context.droppableRects.get(item.id);
      if (!candidate || !candidate.width || !candidate.height) return [];
      const x = candidate.left + candidate.width / 2;
      const y = candidate.top + candidate.height / 2;
      const dx = x - center.x;
      const dy = y - center.y;
      if (
        (event.code === 'ArrowUp' && dy >= -1) ||
        (event.code === 'ArrowDown' && dy <= 1) ||
        (event.code === 'ArrowLeft' && dx >= -1) ||
        (event.code === 'ArrowRight' && dx <= 1)
      )
        return [];
      return [
        {
          x,
          y,
          distance:
            Math.abs(
              event.code === 'ArrowUp' || event.code === 'ArrowDown' ? dy : dx,
            ) +
            0.3 *
              Math.abs(
                event.code === 'ArrowUp' || event.code === 'ArrowDown'
                  ? dx
                  : dy,
              ),
        },
      ];
    })
    .sort((a, b) => a.distance - b.distance);
  const target = candidates[0];
  return target
    ? {
        x: currentCoordinates.x + target.x - center.x,
        y: currentCoordinates.y + target.y - center.y,
      }
    : undefined;
};
