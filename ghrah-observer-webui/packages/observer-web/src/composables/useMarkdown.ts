import MarkdownIt from "markdown-it";

const BASE_URL = new URL("https://chat.ghrah.invalid/");
const ALLOWED_PROTOCOLS = new Set(["http:", "https:", "mailto:", "tel:"]);

function validateLink(rawUrl: string): boolean {
  try {
    const parsed = new URL(rawUrl.trim(), BASE_URL);
    return ALLOWED_PROTOCOLS.has(parsed.protocol);
  } catch {
    return false;
  }
}

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: false,
});
md.validateLink = validateLink;

export function useMarkdown() {
  const render = (src: string): string => md.render(src ?? "");
  return { render };
}

export { validateLink };
