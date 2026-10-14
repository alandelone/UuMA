export interface CommentPreview {
  text: string;
  original_text: string;
  include: boolean;
  imported?: boolean;
}

// Keep the original array positions and source metadata until every chosen batch is done.
// Unchecked opinions remain an explicit author choice; successful rows cannot be reselected.
export function afterCommentImport(preview: CommentPreview[]): {
  preview: CommentPreview[];
  draft: string;
  remaining: number;
} {
  const remaining = preview.filter((item) => !item.imported && (!item.include || !item.text.trim()));
  if (!remaining.length) return { preview: [], draft: '', remaining: 0 };
  return {
    preview: preview.map((item) => item.imported || (item.include && item.text.trim())
      ? { ...item, include: false, imported: true } : { ...item }),
    draft: remaining.map((item) => item.text).join('\n\n'),
    remaining: remaining.length,
  };
}
