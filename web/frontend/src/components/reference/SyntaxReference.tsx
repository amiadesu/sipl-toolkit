import { useEffect } from "react";
import { SYNTAX_REFERENCE } from "./referenceContent";
import "./SyntaxReference.css";

interface SyntaxReferenceProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function SyntaxReference({ isOpen, onClose }: SyntaxReferenceProps) {
  useEffect(() => {
    if (!isOpen) return;
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <>
      <div className="syntax-reference-backdrop" onClick={onClose} />
      <aside className="syntax-reference" aria-label="Довідка з синтаксису">
        <header className="syntax-reference-header">
          <h2 className="syntax-reference-title">Синтаксис мови</h2>
          <button className="syntax-reference-close" onClick={onClose} aria-label="Закрити">
            ✕
          </button>
        </header>

        <div className="syntax-reference-body">
          {SYNTAX_REFERENCE.map((section) => (
            <section key={section.title} className="syntax-reference-section">
              <h3 className="syntax-reference-section-title">{section.title}</h3>
              {section.description && (
                <p className="syntax-reference-section-description">{section.description}</p>
              )}
              <dl className="syntax-reference-list">
                {section.entries.map((entry) => (
                  <div key={entry.code} className="syntax-reference-entry">
                    <dt className="syntax-reference-code">{entry.code}</dt>
                    <dd className="syntax-reference-note">{entry.note}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>
      </aside>
    </>
  );
}