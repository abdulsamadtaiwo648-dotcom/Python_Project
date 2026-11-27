/** A small clock with "Not synced" for items recorded offline that have not reached the server yet. */
export default function SyncPending() {
  return (
    <span className="ui-sync-pending" role="status">
      <svg aria-hidden="true" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4}>
        <circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" />
      </svg>
      Not synced
    </span>
  );
}
