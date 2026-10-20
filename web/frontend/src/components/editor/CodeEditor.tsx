import { useEffect, useMemo, useRef } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { StreamLanguage } from "@codemirror/language";
import { lintGutter, setDiagnostics, type Diagnostic } from "@codemirror/lint";
import { StateEffect, StateField, type Text } from "@codemirror/state";
import { Decoration, EditorView, type DecorationSet } from "@codemirror/view";
import type { Span } from "../../types/ast";
import "./CodeEditor.css";

export interface EditorProblem {
  span: Span | null;
  message: string;
  severity: "error" | "warning";
}

interface CodeEditorProps {
  sourceCode: string;
  onChange: (nextSourceCode: string) => void;
  problems: EditorProblem[];
  highlight: Span | null; // fragment selected in a tree or in the trace
}

// Syntax highlighting only: the real grammar lives in the sipl package.
const KEYWORDS = new Set(["begin", "end", "if", "then", "else", "while", "do", "skip", "or", "not"]);

const sipl = StreamLanguage.define({
  name: "sipl",
  token(stream) {
    if (stream.eatSpace()) return null;
    if (stream.match(/^\d+/)) return "number";
    if (stream.match(/^[A-Za-z][A-Za-z0-9_]*/)) {
      return KEYWORDS.has(stream.current()) ? "keyword" : "variableName";
    }
    if (stream.match(":=") || stream.match(/^[-+*=>¬∨]/)) return "operator";
    if (stream.match(/^[()]/)) return "bracket";
    if (stream.match(";")) return "punctuation";
    stream.next();
    return "invalid";
  },
});

// Lines and columns are 1-based; returns CodeMirror document offsets.
function spanToRange(doc: Text, span: Span): { from: number; to: number } {
  const offset = (line: number, column: number) => {
    if (line > doc.lines) return doc.length;
    const docLine = doc.line(Math.max(line, 1));
    return Math.min(docLine.from + Math.max(column, 1) - 1, docLine.to);
  };
  const from = offset(span.line, span.column);
  const to = Math.max(offset(span.end_line, span.end_column), from);
  return { from, to };
}

const highlightMark = Decoration.mark({ class: "cm-sipl-highlight" });

const setHighlight = StateEffect.define<{ from: number; to: number } | null>();

const highlightField = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(decorations, transaction) {
    let next = decorations.map(transaction.changes);
    for (const effect of transaction.effects) {
      if (effect.is(setHighlight)) {
        next =
          effect.value && effect.value.to > effect.value.from
            ? Decoration.set([highlightMark.range(effect.value.from, effect.value.to)])
            : Decoration.none;
      }
    }
    return next;
  },
  provide: (field) => EditorView.decorations.from(field),
});

export default function CodeEditor({ sourceCode, onChange, problems, highlight }: CodeEditorProps) {
  const viewRef = useRef<EditorView | null>(null);
  const extensions = useMemo(() => [sipl, lintGutter(), highlightField], []);

  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const doc = view.state.doc;
    const diagnostics: Diagnostic[] = problems.map((problem) => {
      // A problem without a position (or at the very end) is shown on the last character.
      let { from, to } = problem.span ? spanToRange(doc, problem.span) : { from: doc.length, to: doc.length };
      if (to === from) {
        if (to < doc.length) to += 1;
        else from = Math.max(0, from - 1);
      }
      return { from, to, severity: problem.severity, message: problem.message };
    });
    view.dispatch(setDiagnostics(view.state, diagnostics));
  }, [problems, sourceCode]);

  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const range = highlight ? spanToRange(view.state.doc, highlight) : null;
    view.dispatch({
      effects: [
        setHighlight.of(range),
        ...(range ? [EditorView.scrollIntoView(range.from, { y: "nearest" })] : []),
      ],
    });
  }, [highlight]);

  return (
    <div className="code-editor">
      <CodeMirror
        value={sourceCode}
        height="100%"
        theme="dark"
        extensions={extensions}
        onChange={onChange}
        onCreateEditor={(view) => {
          viewRef.current = view;
        }}
        basicSetup={{ lineNumbers: true, foldGutter: false }}
      />
    </div>
  );
}