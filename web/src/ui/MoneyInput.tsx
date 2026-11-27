import { useId } from "react";
import { formatMoneyInput, parseMoneyInput } from "./money-input";

/** Big naira amount field with a numeric keypad. Calls onValue with the parsed amount, or null when empty. */
export default function MoneyInput({ label, display, onDisplay, autoFocus }: {
  label: string; display: string; onDisplay: (display: string, amount: number | null) => void; autoFocus?: boolean;
}) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="ui-stat-label">{label}</label>
      <div className="ui-money">
        <span className="ui-money-sign" aria-hidden="true">₦</span>
        <input id={id} className="ui-money-input" inputMode="decimal" autoComplete="off" autoFocus={autoFocus} placeholder="0" value={display}
          onChange={(e) => { const next = formatMoneyInput(e.target.value); onDisplay(next, parseMoneyInput(next)); }} />
      </div>
    </div>
  );
}
