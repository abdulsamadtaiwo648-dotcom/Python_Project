import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

/** One button for every screen. 48px tall on phones; primary is the brand colour. */
export default function Button({ variant = "secondary", block, className = "", ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; block?: boolean }) {
  return <button type="button" {...rest} className={`ui-btn ui-btn-${variant} ${block ? "ui-btn-block" : ""} ${className}`.trim()} />;
}
