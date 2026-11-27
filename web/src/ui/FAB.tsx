/** The one main action for a tab. Sits above the bottom bar on phones. */
export default function FAB({ label, onClick }: { label: string; onClick: () => void }) {
  return <button type="button" className="ui-fab" aria-label={label} onClick={onClick}>+</button>;
}
