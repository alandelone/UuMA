import { serveStudioFile } from '../../../../lib/studio-downloads';

export async function GET(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  return serveStudioFile(request, path,
    process.env.RSTV4_API ?? process.env.NEXT_PUBLIC_RSTV4_API ?? 'http://127.0.0.1:8874/api');
}
