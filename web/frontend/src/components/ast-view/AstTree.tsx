import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";
import type { AstNode, ParseTreeNode, Span, TreeNode } from "../../types/ast";
import "./AstTree.css";

interface AstTreeProps {
  root: TreeNode | null;
  emptyText: string;
  stale: boolean; // the program has a syntax error, so this is the last valid tree
  selectedSpan: Span | null;
  onSelect: (node: TreeNode) => void;
}

const NODE_HORIZONTAL_SPACING = 84;
const NODE_VERTICAL_SPACING = 64;
const PADDING = 40;
const MIN_SCALE = 0.1;
const MAX_SCALE = 4;
const MIN_FIT_SCALE = 0.6;
const MAX_FIT_SCALE = 1.4;

// ---- Converting backend trees ----

export function fromParseTree(node: ParseTreeNode, id = "0"): TreeNode {
  return {
    id,
    label: node.label,
    detail: node.rule,
    role: null,
    span: node.span,
    terminal: node.kind === "terminal",
    children: node.children.map((child, index) => fromParseTree(child, `${id}.${index}`)),
  };
}

function isAstNode(value: unknown): value is AstNode {
  return typeof value === "object" && value !== null && "type" in value;
}

export function fromAst(node: AstNode, id = "0", role: string | null = null): TreeNode {
  const children: TreeNode[] = [];
  const values: string[] = [];
  for (const [key, value] of Object.entries(node)) {
    if (key === "type" || key === "span") continue;
    if (isAstNode(value)) {
      children.push(fromAst(value, `${id}.${children.length}`, key));
    } else {
      values.push(String(value));
    }
  }
  return {
    id,
    label: node.type,
    detail: values.length > 0 ? values.join(" ") : null,
    role,
    span: node.span,
    terminal: children.length === 0,
    children,
  };
}

function sameSpan(a: Span | null, b: Span | null): boolean {
  return (
    a !== null &&
    b !== null &&
    a.line === b.line &&
    a.column === b.column &&
    a.end_line === b.end_line &&
    a.end_column === b.end_column
  );
}

export default function AstTree({ root, emptyText, stale, selectedSpan, onSelect }: AstTreeProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const canvasRef = useRef<SVGGElement>(null);
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const userMovedRef = useRef(false);
  const positionsRef = useRef<{ node: TreeNode; x: number; y: number }[]>([]);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [isFullscreen, setIsFullscreen] = useState(false);

  const nodeCount = useMemo(() => (root ? countNodes(root) : 0), [root]);

  useEffect(() => {
    if (!isFullscreen) return;
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setIsFullscreen(false);
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isFullscreen]);

  const fitToView = useCallback(() => {
    const svgElement = svgRef.current;
    const canvasElement = canvasRef.current;
    const zoom = zoomRef.current;
    if (!svgElement || !canvasElement || !zoom) return;

    const bounds = canvasElement.getBBox();
    if (bounds.width === 0 || bounds.height === 0) return;
    const { width, height } = svgElement.getBoundingClientRect();
    if (width === 0 || height === 0) return;

    const fitScale = Math.min(
      MAX_FIT_SCALE,
      (width - PADDING) / bounds.width,
      (height - PADDING) / bounds.height,
    );
    const scale = Math.max(fitScale, MIN_FIT_SCALE);
    const centerX = fitScale >= MIN_FIT_SCALE ? bounds.x + bounds.width / 2 : 0;
    const translateX = width / 2 - scale * centerX;
    const translateY = PADDING / 2 - scale * bounds.y;

    userMovedRef.current = false;
    d3.select(svgElement)
      .transition()
      .duration(250)
      .call(zoom.transform, d3.zoomIdentity.translate(translateX, translateY).scale(scale));
  }, []);

  const toggleNode = useCallback((id: string) => {
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  useEffect(() => {
    const svgElement = svgRef.current;
    const canvasElement = canvasRef.current;
    if (!svgElement || !canvasElement || !root) return;

    const svg = d3.select(svgElement);
    const canvas = d3.select(canvasElement);
    canvas.selectAll("*").remove();

    if (!zoomRef.current) {
      const zoom = d3
        .zoom<SVGSVGElement, unknown>()
        .scaleExtent([MIN_SCALE, MAX_SCALE])
        .on("zoom", (event) => {
          if (event.sourceEvent) userMovedRef.current = true;
          canvas.attr("transform", event.transform.toString());
        });
      svg.call(zoom);
      svg.on("dblclick.zoom", null);
      zoomRef.current = zoom;
    }

    const hierarchyRoot = d3.hierarchy(root, (node) =>
      collapsed.has(node.id) ? undefined : node.children,
    );
    const layoutRoot = d3
      .tree<TreeNode>()
      .nodeSize([NODE_HORIZONTAL_SPACING, NODE_VERTICAL_SPACING])
      .separation((a, b) => (a.parent === b.parent ? 1 : 1.25))(hierarchyRoot);

    canvas
      .selectAll("path.ast-link")
      .data(layoutRoot.links())
      .join("path")
      .attr("class", "ast-link")
      .attr(
        "d",
        d3
          .linkVertical<d3.HierarchyPointLink<TreeNode>, d3.HierarchyPointNode<TreeNode>>()
          .x((node) => node.x)
          .y((node) => node.y),
      );

    positionsRef.current = layoutRoot.descendants().map((node) => ({ node: node.data, x: node.x, y: node.y }));

    const nodeGroups = canvas
      .selectAll("g.ast-node")
      .data(layoutRoot.descendants())
      .join("g")
      .attr("class", (node) =>
        [
          "ast-node",
          node.data.terminal ? "ast-node--terminal" : "",
          collapsed.has(node.data.id) ? "ast-node--collapsed" : "",
          sameSpan(node.data.span, selectedSpan) ? "ast-node--selected" : "",
        ].join(" "),
      )
      .attr("transform", (node) => `translate(${node.x}, ${node.y})`)
      .on("click", (event, node) => {
        event.stopPropagation();
        onSelect(node.data);
      })
      .on("dblclick", (event, node) => {
        event.stopPropagation();
        if (node.data.children.length > 0) toggleNode(node.data.id);
      });

    nodeGroups.append("title").text((node) => {
      const span = node.data.span;
      return span ? `${span.line}:${span.column}-${span.end_line}:${span.end_column}` : "";
    });

    nodeGroups.append("circle").attr("class", "ast-node-hit").attr("r", 22).attr("cy", 2);
    nodeGroups.append("circle").attr("class", "ast-node-dot").attr("r", 5);

    nodeGroups
      .filter((node) => node.data.role !== null)
      .append("text")
      .attr("class", "ast-node-role")
      .attr("dy", -22)
      .attr("text-anchor", "middle")
      .text((node) => node.data.role as string);

    nodeGroups
      .append("text")
      .attr("class", "ast-node-type")
      .attr("dy", -10)
      .attr("text-anchor", "middle")
      .text((node) => node.data.label);

    nodeGroups
      .filter((node) => node.data.detail !== null)
      .append("text")
      .attr("class", "ast-node-label")
      .attr("dy", 18)
      .attr("text-anchor", "middle")
      .text((node) => node.data.detail as string);

    nodeGroups
      .filter((node) => collapsed.has(node.data.id))
      .append("text")
      .attr("class", "ast-node-count")
      .attr("dy", 4)
      .attr("dx", 12)
      .text((node) => `+${countNodes(node.data) - 1}`);
  }, [root, collapsed, selectedSpan, onSelect, toggleNode]);

  useEffect(() => {
    const svgElement = svgRef.current;
    const zoom = zoomRef.current;
    if (!svgElement || !zoom || !selectedSpan) return;
    const target = positionsRef.current.find((position) => sameSpan(position.node.span, selectedSpan));
    if (!target) return;

    const transform = d3.zoomTransform(svgElement);
    const { width, height } = svgElement.getBoundingClientRect();
    const x = transform.applyX(target.x);
    const y = transform.applyY(target.y);
    const margin = 40;
    if (x >= margin && x <= width - margin && y >= margin && y <= height - margin) return;

    d3.select(svgElement)
      .transition()
      .duration(300)
      .call(
        zoom.transform,
        d3.zoomIdentity
          .translate(width / 2 - transform.k * target.x, height / 2 - transform.k * target.y)
          .scale(transform.k),
      );
  }, [selectedSpan]);

  useEffect(() => {
    if (root && !userMovedRef.current) fitToView();
  }, [nodeCount, root, fitToView]);

  const hasRoot = root !== null;
  useEffect(() => {
    if (!hasRoot) return;
    const frame = requestAnimationFrame(fitToView);
    return () => cancelAnimationFrame(frame);
  }, [isFullscreen, hasRoot, fitToView]);

  if (!root) {
    return <div className="ast-tree ast-tree--empty">{emptyText}</div>;
  }

  return (
    <div
      className={[
        "ast-tree",
        isFullscreen ? "ast-tree--fullscreen" : "",
        stale ? "ast-tree--stale" : "",
      ].join(" ")}
    >
      <div className="ast-tree-toolbar">
        <span className="ast-tree-hint">
          {stale
            ? "Програма має помилку, показано останнє коректне дерево"
            : "Клік: показати в коді. Подвійний клік: згорнути"}
        </span>
        <div className="ast-tree-actions">
          <button className="ast-tree-button" onClick={fitToView}>
            Вмістити
          </button>
          <button className="ast-tree-button" onClick={() => setIsFullscreen((current) => !current)}>
            {isFullscreen ? "Згорнути (Esc)" : "На весь екран"}
          </button>
        </div>
      </div>
      <svg ref={svgRef} className="ast-tree-canvas">
        <g ref={canvasRef} />
      </svg>
    </div>
  );
}

function countNodes(node: TreeNode): number {
  return node.children.reduce((total, child) => total + countNodes(child), 1);
}