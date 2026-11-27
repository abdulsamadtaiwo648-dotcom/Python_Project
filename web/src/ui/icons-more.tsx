import { ICONS } from "../icons";

/** The "More" glyph for the bottom bar. Same markup as the Svg helper in Layout. */
export const moreIcon = (
  <svg className="w-6 h-6" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.9}
    strokeLinecap="round" strokeLinejoin="round" dangerouslySetInnerHTML={{ __html: ICONS.more }} />
);
