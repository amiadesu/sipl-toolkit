import { useEffect, useMemo, useRef, type KeyboardEvent } from "react";
import type { RunResult, Span, TraceEvent, Value } from "../../types/ast";
import "./RunOutput.css";

interface RunOutputProps {
  initialStateText: string;
  onInitialStateTextChange: (text: string) => void;
  initialStateError: string | null;
  initialState: Record<string, string>;
  maxSteps: number;
  onMaxStepsChange: (value: number) => void;
  autoRun: boolean;
  onAutoRunChange: (value: boolean) => void;
  result: RunResult | null;
  selectedEvent: number | null;
  onSelectEvent: (index: number) => void;
}

const NAME = /^[A-Za-z][A-Za-z0-9_]*$/;
const INTEGER = /^-?\d+$/;

export type ParsedState =
  | { ok: true; values: Record<string, string> }
  | { ok: false; message: string };

// "X = 2, Y = -3" -> {X: "2", Y: "-3"}. Separators: commas, semicolons, new lines.
export function parseInitialState(text: string): ParsedState {
  const values: Record<string, string> = {};
  for (const part of text.split(/[,;\n]/)) {
    const item = part.trim();
    if (item === "") continue;
    const [name, value, ...rest] = item.split("=").map((piece) => piece.trim());
    if (rest.length > 0 || value === undefined || !NAME.test(name) || !INTEGER.test(value)) {
      return { ok: false, message: `очікувалось ІМ'Я = ЧИСЛО, отримано «${item}»` };
    }
    values[name] = value;
  }
  return { ok: true, values };
}

function stateAt(initial: Record<string, string>, events: TraceEvent[], index: number): Record<string, Value> {
  const state: Record<string, Value> = { ...initial };
  for (const event of events.slice(0, index + 1)) {
    if (event.event === "variable_changed" && event.name !== undefined && event.new !== undefined) {
      state[event.name] = event.new;
    }
  }
  return state;
}

export function formatSpan(span: Span | null): string {
  return span ? `${span.line}:${span.column}` : "";
}

function describe(event: TraceEvent): string {
  switch (event.event) {
    case "before_statement":
      return `▶ ${event.statement}`;
    case "after_statement":
      return `◀ ${event.statement}`;
    case "variable_changed":
      return `${event.name} := ${event.new}` + (event.old === null ? "" : `  (було ${event.old})`);
    case "condition_checked":
      return `умова ${event.statement}: ${event.result ? "істина" : "хиба"}`;
    case "execution_finished":
      return event.status === "ok" ? "■ завершено" : `■ помилка: ${event.error?.message}`;
  }
}

function StateTable({ state }: { state: Record<string, Value> }) {
  const entries = Object.entries(state).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  if (entries.length === 0) return <div className="run-output-muted">стан порожній</div>;
  return (
    <table className="run-output-state">
      <tbody>
        {entries.map(([name, value]) => (
          <tr key={name}>
            <td className="run-output-state-name">{name}</td>
            <td className="run-output-state-value">{String(value)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function RunOutput(props: RunOutputProps) {
  const { result, selectedEvent, onSelectEvent } = props;
  const events = result?.events ?? null;
  const selectedRowRef = useRef<HTMLLIElement>(null);

  const selectedState = useMemo(
    () => (events && selectedEvent !== null ? stateAt(props.initialState, events, selectedEvent) : null),
    [events, selectedEvent, props.initialState],
  );

  useEffect(() => {
    selectedRowRef.current?.scrollIntoView({ block: "nearest" });
  }, [selectedEvent]);

  function handleKeyDown(event: KeyboardEvent) {
    if (!events || events.length === 0) return;
    const current = selectedEvent ?? -1;
    if (event.key === "ArrowDown") onSelectEvent(Math.min(current + 1, events.length - 1));
    else if (event.key === "ArrowUp") onSelectEvent(Math.max(current - 1, 0));
    else return;
    event.preventDefault();
  }

  return (
    <div className="run-output">
      <div className="run-output-controls">
        <label className="run-output-field run-output-field--wide">
          <span>Початковий стан</span>
          <input
            className={props.initialStateError ? "run-output-input run-output-input--invalid" : "run-output-input"}
            value={props.initialStateText}
            placeholder="X = 2, Y = 10"
            onChange={(event) => props.onInitialStateTextChange(event.target.value)}
            spellCheck={false}
          />
        </label>
        <label className="run-output-field">
          <span>Ліміт кроків</span>
          <input
            className="run-output-input run-output-input--number"
            type="number"
            min={1}
            max={100000}
            value={props.maxSteps}
            onChange={(event) => props.onMaxStepsChange(Number(event.target.value))}
          />
        </label>
        <label className="run-output-checkbox">
          <input
            type="checkbox"
            checked={props.autoRun}
            onChange={(event) => props.onAutoRunChange(event.target.checked)}
          />
          автозапуск
        </label>
      </div>
      {props.initialStateError && <div className="run-output-error">{props.initialStateError}</div>}

      {!result && (
        <div className="run-output-muted run-output-placeholder">Результат з'явиться після виконання</div>
      )}

      {result && (
        <div className="run-output-results">
          <section className="run-output-section">
            <h3 className="run-output-heading">
              {result.error
                ? `Помилка${result.error.span ? ` (${formatSpan(result.error.span)})` : ""}`
                : "Кінцевий стан"}
              {result.steps !== null && <span className="run-output-count">кроків: {result.steps}</span>}
            </h3>
            {result.error && <div className="run-output-error">{result.error.message}</div>}
            {result.state && <StateTable state={result.state} />}
          </section>

          {events && (
            <section className="run-output-section run-output-section--trace">
              <h3 className="run-output-heading">
                Trace
                <span className="run-output-count">
                  подій: {events.length}
                  {result.truncated && " (показано лише перші)"}
                </span>
              </h3>
              <div className="run-output-trace-layout">
                <ol className="run-output-trace" tabIndex={0} onKeyDown={handleKeyDown}>
                  {events.map((event, index) => (
                    <li
                      key={index}
                      ref={index === selectedEvent ? selectedRowRef : undefined}
                      className={[
                        "run-output-event",
                        `run-output-event--${event.event}`,
                        index === selectedEvent ? "run-output-event--selected" : "",
                      ].join(" ")}
                      onClick={() => onSelectEvent(index)}
                    >
                      <span className="run-output-event-step">{event.step}</span>
                      <span className="run-output-event-where">{formatSpan(event.span)}</span>
                      <span className="run-output-event-text">{describe(event)}</span>
                    </li>
                  ))}
                </ol>
                <div className="run-output-trace-state">
                  <div className="run-output-muted">
                    {selectedEvent === null ? "Оберіть подію" : `Стан після події ${selectedEvent + 1}`}
                  </div>
                  {selectedState && <StateTable state={selectedState} />}
                </div>
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}