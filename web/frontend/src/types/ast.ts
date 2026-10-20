export interface Span {
  line: number;
  column: number;
  end_line: number;
  end_column: number;
}

export interface SiplErrorInfo {
  stage: string;
  message: string;
  span: Span | null;
}

export interface ParseTreeNode {
  kind: "terminal" | "nonterminal";
  label: string;
  rule: string | null;
  text: string;
  span: Span;
  children: ParseTreeNode[];
}

export interface AstNode {
  type: string;
  span: Span | null;
  [field: string]: unknown;
}

export interface TreeNode {
  id: string;
  label: string;
  detail: string | null; // course rule (parse tree) or node values (AST)
  role: string | null; // field name in the parent AST node
  span: Span | null;
  terminal: boolean;
  children: TreeNode[];
}

// Integers beyond JavaScript's safe range arrive as strings.
export type Value = number | string;

export interface TraceEvent {
  event:
    | "before_statement"
    | "after_statement"
    | "variable_changed"
    | "condition_checked"
    | "execution_finished";
  step: number;
  span: Span | null;
  statement?: string;
  name?: string;
  old?: Value | null;
  new?: Value;
  result?: boolean;
  status?: "ok" | "error";
  state?: Record<string, Value>;
  error?: SiplErrorInfo | null;
}

export interface AnalyzeResult {
  parseTree: ParseTreeNode | null;
  ast: AstNode | null;
  error: SiplErrorInfo | null;
}

export interface RunResult {
  state: Record<string, Value> | null;
  steps: number | null;
  events: TraceEvent[] | null;
  truncated: boolean;
  error: SiplErrorInfo | null;
}

export interface Example {
  name: string;
  sourceCode: string;
}