import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import CodeEditor, { type EditorProblem } from "./components/editor/CodeEditor";
import AstTree, { fromAst, fromParseTree } from "./components/ast-view/AstTree";
import RunOutput, { formatSpan, parseInitialState } from "./components/output/RunOutput";
import SyntaxReference from "./components/reference/SyntaxReference";
import { analyzeSource, runSource, fetchExamples, CompileError } from "./api/compileApi";
import type { AnalyzeResult, Example, RunResult, Span, TreeNode } from "./types/ast";
import "./App.css";

const FALLBACK_SOURCE_CODE = `begin
  R := 1;
  while Y > 0 do
  begin
    R := R * X;
    Y := Y - 1
  end
end
`;

const EXAMPLE_STATES: Record<string, string> = {
  power: "X = 2, Y = 10",
  factorial: "N = 5",
  gcd: "A = 48, B = 18",
};

const ANALYZE_DELAY_MS = 250;
const RUN_DELAY_MS = 400;
const MAX_STEPS_LIMIT = 100_000;

interface Trees {
  parse: TreeNode;
  ast: TreeNode;
}

export default function App() {
  const [sourceCode, setSourceCode] = useState(FALLBACK_SOURCE_CODE);
  const [examples, setExamples] = useState<Example[]>([]);
  const [analysis, setAnalysis] = useState<AnalyzeResult | null>(null);
  const [trees, setTrees] = useState<Trees | null>(null); // last syntactically valid version
  const [initialStateText, setInitialStateText] = useState(EXAMPLE_STATES.power);
  const [maxSteps, setMaxSteps] = useState(10_000);
  const [autoRun, setAutoRun] = useState(true);
  const [result, setResult] = useState<RunResult | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [selectedSpan, setSelectedSpan] = useState<Span | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<number | null>(null);
  const [compileErrorMessage, setCompileErrorMessage] = useState<string | null>(null);
  const [isReferenceOpen, setIsReferenceOpen] = useState(false);
  const runControllerRef = useRef<AbortController | null>(null);

  const parsedState = useMemo(() => parseInitialState(initialStateText), [initialStateText]);
  const initialState = useMemo(() => (parsedState.ok ? parsedState.values : {}), [parsedState]);

  useEffect(() => {
    fetchExamples()
      .then(setExamples)
      .catch(() => {
        // The examples are a convenience, the editor works without them
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const nextAnalysis = await analyzeSource(sourceCode, controller.signal);
        setAnalysis(nextAnalysis);
        setCompileErrorMessage(null);
        if (nextAnalysis.parseTree && nextAnalysis.ast) {
          setTrees({ parse: fromParseTree(nextAnalysis.parseTree), ast: fromAst(nextAnalysis.ast) });
        }
      } catch (error) {
        if (error instanceof CompileError) setCompileErrorMessage(error.message);
      }
    }, ANALYZE_DELAY_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [sourceCode]);

  const handleRun = useCallback(async () => {
    if (!parsedState.ok) return;
    runControllerRef.current?.abort();
    const controller = new AbortController();
    runControllerRef.current = controller;
    setIsRunning(true);
    try {
      const nextResult = await runSource(sourceCode, parsedState.values, maxSteps, controller.signal);
      setResult(nextResult);
      setSelectedEvent(null);
      setCompileErrorMessage(null);
    } catch (error) {
      if (error instanceof CompileError) setCompileErrorMessage(error.message);
    } finally {
      if (runControllerRef.current === controller) setIsRunning(false);
    }
  }, [sourceCode, parsedState, maxSteps]);

  useEffect(() => {
    if (!autoRun) return;
    const timer = setTimeout(handleRun, RUN_DELAY_MS);
    return () => clearTimeout(timer);
  }, [autoRun, handleRun]);

  const handleSourceChange = useCallback((nextSourceCode: string) => {
    setSourceCode(nextSourceCode);
    setSelectedSpan(null);
    setSelectedEvent(null);
  }, []);

  const handleExample = useCallback(
    (example: Example) => {
      handleSourceChange(example.sourceCode);
      setInitialStateText(EXAMPLE_STATES[example.name] ?? "");
    },
    [handleSourceChange],
  );

  const handleSelectNode = useCallback((node: TreeNode) => {
    setSelectedSpan(node.span);
    setSelectedEvent(null);
  }, []);

  const handleSelectEvent = useCallback(
    (index: number) => {
      setSelectedEvent(index);
      setSelectedSpan(result?.events?.[index]?.span ?? null);
    },
    [result],
  );

  const syntaxError = analysis?.error ?? null;

  const problems = useMemo<EditorProblem[]>(() => {
    if (syntaxError) return [{ span: syntaxError.span, message: syntaxError.message, severity: "error" }];
    const runtimeError = result?.error;
    if (runtimeError && runtimeError.stage === "run") {
      return [{ span: runtimeError.span, message: runtimeError.message, severity: "warning" }];
    }
    return [];
  }, [syntaxError, result]);

  return (
    <div className="app-shell">
      <SyntaxReference isOpen={isReferenceOpen} onClose={() => setIsReferenceOpen(false)} />

      <header className="app-header">
        <div className="app-header-left">
          <button
            className="app-reference-button"
            onClick={() => setIsReferenceOpen(true)}
            aria-expanded={isReferenceOpen}
          >
            Синтаксис
          </button>
          <h1 className="app-title">SIPL</h1>
        </div>

        <div className="app-header-actions">
          {examples.length > 0 && (
            <div className="app-examples">
              <span className="app-examples-label">Приклади:</span>
              {examples.map((example) => (
                <button
                  key={example.name}
                  className="app-example-button"
                  onClick={() => handleExample(example)}
                >
                  {example.name}
                </button>
              ))}
            </div>
          )}

          <button className="app-run-button" onClick={handleRun} disabled={isRunning || !parsedState.ok}>
            {isRunning ? "Виконання…" : "Виконати"}
          </button>
        </div>
      </header>

      {compileErrorMessage && <div className="app-error-banner">{compileErrorMessage}</div>}

      <main className="app-columns">
        <section className="app-column app-column--code">
          <h2 className="app-column-heading">
            Програма
            <span className={syntaxError ? "app-status app-status--error" : "app-status"}>
              {analysis === null
                ? ""
                : syntaxError
                  ? `${formatSpan(syntaxError.span)} ${syntaxError.message}`
                  : "синтаксис коректний"}
            </span>
          </h2>
          <CodeEditor
            sourceCode={sourceCode}
            onChange={handleSourceChange}
            problems={problems}
            highlight={selectedSpan}
          />
        </section>

        <section className="app-column app-column--output">
          <h2 className="app-column-heading">Виконання</h2>
          <RunOutput
            initialStateText={initialStateText}
            onInitialStateTextChange={setInitialStateText}
            initialStateError={parsedState.ok ? null : parsedState.message}
            initialState={initialState}
            maxSteps={maxSteps}
            onMaxStepsChange={(value) =>
              setMaxSteps(Math.min(Math.max(Number.isFinite(value) ? value : 1, 1), MAX_STEPS_LIMIT))
            }
            autoRun={autoRun}
            onAutoRunChange={setAutoRun}
            result={result}
            selectedEvent={selectedEvent}
            onSelectEvent={handleSelectEvent}
          />
        </section>

        <section className="app-column app-column--parse-tree">
          <h2 className="app-column-heading">Дерево синтаксичного виводу</h2>
          <AstTree
            root={trees?.parse ?? null}
            emptyText="Дерево з'явиться, щойно програма стане синтаксично коректною"
            stale={syntaxError !== null}
            selectedSpan={selectedSpan}
            onSelect={handleSelectNode}
          />
        </section>

        <section className="app-column app-column--ast">
          <h2 className="app-column-heading">AST</h2>
          <AstTree
            root={trees?.ast ?? null}
            emptyText="AST з'явиться, щойно програма стане синтаксично коректною"
            stale={syntaxError !== null}
            selectedSpan={selectedSpan}
            onSelect={handleSelectNode}
          />
        </section>
      </main>
    </div>
  );
}