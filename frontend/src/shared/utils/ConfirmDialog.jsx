// A small pop-up that asks a yes / no question before something that cannot be undone.
// Show it with:  {ask && <ConfirmDialog question="..." onYes={...} onNo={() => setAsk(false)} />}
export default function ConfirmDialog({ question, detail, onYes, onNo }) {
  return (
    <div className="modal-backdrop" onClick={onNo}>
      {/* a click inside the box must not close it */}
      <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <h3>{question}</h3>
        {detail && <p className="muted small">{detail}</p>}
        <div className="modal-buttons">
          <button type="button" className="secondary" onClick={onNo}>No</button>
          <button type="button" onClick={onYes} autoFocus>Yes</button>
        </div>
      </div>
    </div>
  );
}
