/** Shared ReactMarkdown component overrides -- no @tailwindcss/typography
 * plugin is installed, so every element is styled explicitly here instead
 * of relying on a `prose` class. Used by both the AI Assistant chat and the
 * Appeals document viewer so generated content looks consistent everywhere. */
export const markdownComponents = {
  h1: (props: any) => <h4 className="mb-1.5 mt-3 text-sm font-semibold text-proxy-text first:mt-0" {...props} />,
  h2: (props: any) => <h4 className="mb-1.5 mt-3 text-sm font-semibold text-proxy-text first:mt-0" {...props} />,
  h3: (props: any) => <h5 className="mb-1 mt-3 text-[13px] font-semibold text-cyan-100 first:mt-0" {...props} />,
  p: (props: any) => <p className="mb-2 text-sm leading-6 text-proxy-text last:mb-0" {...props} />,
  strong: (props: any) => <strong className="font-semibold text-proxy-text" {...props} />,
  ul: (props: any) => <ul className="mb-2 ml-4 list-disc space-y-1 text-sm leading-6 text-proxy-text" {...props} />,
  ol: (props: any) => <ol className="mb-2 ml-4 list-decimal space-y-1 text-sm leading-6 text-proxy-text" {...props} />,
  li: (props: any) => <li className="pl-0.5" {...props} />,
  a: (props: any) => <a className="text-cyan-200 underline decoration-cyan-300/30 hover:text-cyan-100" target="_blank" rel="noreferrer" {...props} />,
};
