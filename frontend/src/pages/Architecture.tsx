import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { api } from '../lib/api';
import { Card, Empty, Loading, Metric, PageHeader, Badge } from '../components/UI';
import { Icon } from '../components/Icons';
import { useRepo } from '../main';
import { getLanguageColor } from '../lib/utils';

interface NodePosition {
  id: string;
  path: string;
  name: string;
  dir: string;
  language: string;
  inbound_count: number;
  outbound_count: number;
  symbol_count: number;
  chunk_count: number;
  totalConnections: number;
  x: number;
  y: number;
  radius: number;
  color: string;
  isCentral: boolean;
}

interface EdgePath {
  sourceId: string;
  targetId: string;
  sourcePath: string;
  targetPath: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  d: string;
}

export function Architecture() {
  const { repoId, repo } = useRepo();
  const [overview, setOverview] = useState<any>();
  const [graph, setGraph] = useState<any>();
  const [selected, setSelected] = useState<any>();
  const [hoveredNode, setHoveredNode] = useState<NodePosition | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [layoutMode, setLayoutMode] = useState<'concentric' | 'force' | 'hierarchical'>('concentric');

  // Zoom and Pan state
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const canvasRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!repoId) return;
    setLoading(true);
    Promise.all([
      api.architectureOverview(repoId),
      api.architectureGraph(repoId),
    ])
      .then(([a, b]) => {
        setOverview(a);
        setGraph(b);
      })
      .finally(() => setLoading(false));
  }, [repoId]);

  const rawNodes = useMemo(() => graph?.nodes || [], [graph]);
  const rawEdges = useMemo(() => graph?.edges || [], [graph]);

  // Compute Layout & Coordinates with Collision Prevention
  const { nodes, edges, width, height } = useMemo(() => {
    if (!rawNodes.length) {
      return { nodes: [] as NodePosition[], edges: [] as EdgePath[], width: 1000, height: 700 };
    }

    const W = 1100;
    const H = 750;
    const centerX = W / 2;
    const centerY = H / 2;

    const maxDegree = Math.max(
      ...rawNodes.map((n: any) => (n.inbound_count || 0) + (n.outbound_count || 0)),
      1
    );

    // Prepare Node Objects
    const computedNodes: NodePosition[] = rawNodes.map((n: any) => {
      const pathParts = n.path.split('/');
      const name = pathParts.pop() || n.path;
      const dir = pathParts.join('/') || 'root';
      const ext = name.includes('.') ? `.${name.split('.').pop()?.toLowerCase()}` : '';
      const lang = n.language || ext.replace('.', '') || 'text';
      const color = getLanguageColor(lang);
      const totalConnections = (n.inbound_count || 0) + (n.outbound_count || 0);
      const radius = Math.max(16, Math.min(34, 16 + (totalConnections / maxDegree) * 18));
      const isCentral = (n.inbound_count || 0) >= 3 || totalConnections >= 5;

      return {
        id: n.path,
        path: n.path,
        name,
        dir,
        language: lang,
        inbound_count: n.inbound_count || 0,
        outbound_count: n.outbound_count || 0,
        symbol_count: n.symbol_count || 0,
        chunk_count: n.chunk_count || 0,
        totalConnections,
        x: centerX,
        y: centerY,
        radius,
        color,
        isCentral,
      };
    });

    // Layout Algorithms
    if (layoutMode === 'concentric') {
      // Sort by connectivity: highest degree in inner circles, peripheral in outer orbits
      const sorted = [...computedNodes].sort((a, b) => b.totalConnections - a.totalConnections);
      const core = sorted.filter((n) => n.totalConnections >= 3);
      const intermediate = sorted.filter((n) => n.totalConnections > 0 && n.totalConnections < 3);
      const peripheral = sorted.filter((n) => n.totalConnections === 0);

      const rings = [
        { nodes: core, radius: 130 },
        { nodes: intermediate, radius: 250 },
        { nodes: peripheral, radius: 340 },
      ];

      rings.forEach(({ nodes: ringNodes, radius: r }) => {
        if (!ringNodes.length) return;
        const step = (Math.PI * 2) / ringNodes.length;
        ringNodes.forEach((n, idx) => {
          const angle = idx * step - Math.PI / 2;
          n.x = centerX + Math.cos(angle) * r;
          n.y = centerY + Math.sin(angle) * (r * 0.82);
        });
      });
    } else if (layoutMode === 'hierarchical') {
      // Top-to-bottom or Left-to-Right by in/out degree
      const entrypoints = computedNodes.filter((n) => n.inbound_count === 0 && n.outbound_count > 0);
      const coreModules = computedNodes.filter((n) => n.inbound_count > 0 && n.outbound_count > 0);
      const leafUtilities = computedNodes.filter((n) => n.inbound_count > 0 && n.outbound_count === 0);
      const isolated = computedNodes.filter((n) => n.totalConnections === 0);

      const layers = [
        { nodes: entrypoints, y: 120 },
        { nodes: coreModules, y: 320 },
        { nodes: leafUtilities, y: 520 },
        { nodes: isolated, y: 650 },
      ];

      layers.forEach(({ nodes: layerNodes, y }) => {
        if (!layerNodes.length) return;
        const spacing = Math.min(180, (W - 160) / Math.max(layerNodes.length, 1));
        const startX = centerX - ((layerNodes.length - 1) * spacing) / 2;
        layerNodes.forEach((n, idx) => {
          n.x = startX + idx * spacing;
          n.y = y;
        });
      });
    } else {
      // Force / Balanced grid layout
      const cols = Math.ceil(Math.sqrt(computedNodes.length * 1.6));
      const rows = Math.ceil(computedNodes.length / cols);
      const cellW = (W - 140) / Math.max(cols, 1);
      const cellH = (H - 140) / Math.max(rows, 1);

      computedNodes.forEach((n, idx) => {
        const c = idx % cols;
        const r = Math.floor(idx / cols);
        n.x = 90 + c * cellW + cellW / 2;
        n.y = 90 + r * cellH + cellH / 2;
      });
    }

    // Collision Resolution Pass (Prevent Overlap)
    for (let iter = 0; iter < 40; iter++) {
      for (let i = 0; i < computedNodes.length; i++) {
        for (let j = i + 1; j < computedNodes.length; j++) {
          const a = computedNodes[i];
          const b = computedNodes[j];
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const dist = Math.hypot(dx, dy) || 1;
          const minDist = a.radius + b.radius + 32; // 32px safe gap

          if (dist < minDist) {
            const overlap = (minDist - dist) / 2;
            const nx = dx / dist;
            const ny = dy / dist;
            a.x -= nx * overlap;
            a.y -= ny * overlap;
            b.x += nx * overlap;
            b.y += ny * overlap;
          }
        }
      }
    }

    // Node Lookup Map
    const nodeMap = new Map<string, NodePosition>();
    computedNodes.forEach((n) => nodeMap.set(n.id, n));

    // Compute Directional Edges
    const computedEdges: EdgePath[] = [];
    rawEdges.forEach((e: any) => {
      const src = nodeMap.get(e.source);
      const tgt = nodeMap.get(e.target);
      if (!src || !tgt || src.id === tgt.id) return;

      const dx = tgt.x - src.x;
      const dy = tgt.y - src.y;
      const dist = Math.hypot(dx, dy) || 1;
      const ux = dx / dist;
      const uy = dy / dist;

      // Start from source node boundary and end at target node boundary
      const x1 = src.x + ux * src.radius;
      const y1 = src.y + uy * src.radius;
      const x2 = tgt.x - ux * (tgt.radius + 8); // gap for arrowhead
      const y2 = tgt.y - uy * (tgt.radius + 8);

      // Curved Bezier path with offset control point
      const midX = (x1 + x2) / 2;
      const midY = (y1 + y2) / 2;
      const curveOffset = Math.min(30, dist * 0.12);
      const cx = midX - uy * curveOffset;
      const cy = midY + ux * curveOffset;
      const d = `M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`;

      computedEdges.push({
        sourceId: src.id,
        targetId: tgt.id,
        sourcePath: src.path,
        targetPath: tgt.path,
        x1,
        y1,
        x2,
        y2,
        d,
      });
    });

    return { nodes: computedNodes, edges: computedEdges, width: W, height: H };
  }, [rawNodes, rawEdges, layoutMode]);

  // Connected nodes & edges for highlighting
  const activeFocusId = selected?.path || hoveredNode?.path;
  const connectedNodeIds = useMemo(() => {
    if (!activeFocusId) return new Set<string>();
    const set = new Set<string>([activeFocusId]);
    edges.forEach((e) => {
      if (e.sourcePath === activeFocusId) set.add(e.targetPath);
      if (e.targetPath === activeFocusId) set.add(e.sourcePath);
    });
    return set;
  }, [activeFocusId, edges]);

  // Filtered nodes by search query
  const searchMatches = useMemo(() => {
    if (!searchQuery.trim()) return new Set<string>();
    const q = searchQuery.toLowerCase().trim();
    return new Set(nodes.filter((n) => n.path.toLowerCase().includes(q)).map((n) => n.path));
  }, [searchQuery, nodes]);

  // Zoom & Pan Handlers
  const handleZoomIn = () => setZoom((z) => Math.min(2.5, z + 0.2));
  const handleZoomOut = () => setZoom((z) => Math.max(0.4, z - 0.2));
  const handleResetView = useCallback(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, []);

  const handleMouseDown = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).tagName !== 'svg' && (e.target as HTMLElement).tagName !== 'DIV') {
      return;
    }
    setIsDragging(true);
    dragStartRef.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    setPan({
      x: e.clientX - dragStartRef.current.x,
      y: e.clientY - dragStartRef.current.y,
    });
  };

  const handleMouseUp = () => setIsDragging(false);

  const handleWheel = useCallback((e: WheelEvent) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.08 : 0.92;
    setZoom((z) => Math.max(0.4, Math.min(2.5, z * zoomFactor)));
  }, []);

  // Attach wheel handler as non-passive so preventDefault() works.
  // React's synthetic onWheel is passive by default in modern browsers,
  // which prevents calling preventDefault() and causes a console warning.
  useEffect(() => {
    const el = canvasRef.current;
    if (!el) return;
    el.addEventListener('wheel', handleWheel, { passive: false });
    return () => {
      el.removeEventListener('wheel', handleWheel);
    };
  }, [handleWheel]);

  if (!repoId) {
    return (
      <Empty
        title="Select a Repository"
        description="Architecture explorer requires an active repository with analyzed import relationships."
      />
    );
  }

  if (loading || !overview || !graph) {
    return <Loading label="Synthesizing architectural dependency graph…" />;
  }

  return (
    <>
      <PageHeader
        eyebrow="ARCHITECTURE INTELLIGENCE"
        title="Codebase Dependency Graph"
        description="Topological dependency mapping parsed from AST module imports, exports, and call hierarchies."
        actions={
          <Badge
            status="info"
            label={`${overview.file_count} Files · ${overview.dependency_edge_count} Dependency Edges`}
          />
        }
      />

      {/* Top 4 Metrics */}
      <div className="metrics">
        <Metric
          label="Analyzed Files"
          value={overview.file_count.toLocaleString()}
          icon={Icon.File}
          accent="cyan"
        />
        <Metric
          label="Dependency Edges"
          value={overview.dependency_edge_count.toLocaleString()}
          icon={Icon.Git}
          accent="purple"
        />
        <Metric
          label="Directories"
          value={overview.directory_count.toLocaleString()}
          icon={Icon.Grid}
          accent="blue"
        />
        <Metric
          label="Indexed Symbols"
          value={overview.symbol_count.toLocaleString()}
          icon={Icon.Code}
          accent="emerald"
        />
      </div>

      {/* Main Architecture Layout */}
      <div className="architecture-layout">
        {/* Interactive Radial Graph Canvas */}
        <Card className="graph-card" style={{ display: 'flex', flexDirection: 'column' }}>
          {/* Graph Toolbar */}
          <div className="card-title" style={{ flexWrap: 'wrap', gap: 12 }}>
            <div>
              <span className="eyebrow">DEPENDENCY TOPOLOGY</span>
              <h2>{graph.total_nodes} Nodes · {graph.total_edges} Edges</h2>
            </div>

            {/* Controls Bar */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              {/* Search input */}
              <div style={{ position: 'relative' }}>
                <input
                  type="text"
                  placeholder="Filter files in graph…"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  style={{
                    padding: '6px 12px',
                    fontSize: 12,
                    borderRadius: 6,
                    border: '1px solid var(--border-default)',
                    background: 'var(--bg-secondary)',
                    color: 'var(--text-primary)',
                    width: 170,
                  }}
                />
              </div>

              {/* Layout Switcher */}
              <div className="mode-pills" style={{ padding: 2 }}>
                <button
                  type="button"
                  className={`mode-pill ${layoutMode === 'concentric' ? 'active' : ''}`}
                  onClick={() => setLayoutMode('concentric')}
                  style={{ fontSize: 11, padding: '4px 8px' }}
                >
                  Concentric
                </button>
                <button
                  type="button"
                  className={`mode-pill ${layoutMode === 'hierarchical' ? 'active' : ''}`}
                  onClick={() => setLayoutMode('hierarchical')}
                  style={{ fontSize: 11, padding: '4px 8px' }}
                >
                  Flow
                </button>
                <button
                  type="button"
                  className={`mode-pill ${layoutMode === 'force' ? 'active' : ''}`}
                  onClick={() => setLayoutMode('force')}
                  style={{ fontSize: 11, padding: '4px 8px' }}
                >
                  Grid
                </button>
              </div>

              {/* Zoom Controls */}
              <div style={{ display: 'flex', gap: 4 }}>
                <button
                  type="button"
                  className="icon-btn"
                  onClick={handleZoomIn}
                  title="Zoom in"
                  style={{ width: 28, height: 28 }}
                >
                  +
                </button>
                <button
                  type="button"
                  className="icon-btn"
                  onClick={handleZoomOut}
                  title="Zoom out"
                  style={{ width: 28, height: 28 }}
                >
                  −
                </button>
                <button
                  type="button"
                  className="icon-btn"
                  onClick={handleResetView}
                  title="Reset view"
                  style={{ width: 28, height: 28, fontSize: 11 }}
                >
                  Fit
                </button>
              </div>
            </div>
          </div>

          {/* Interactive Graph Canvas Viewport */}
          <div
            ref={canvasRef}
            className="graph-canvas-viewport"
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
            style={{
              position: 'relative',
              width: '100%',
              minHeight: 520,
              flex: 1,
              overflow: 'hidden',
              background: 'radial-gradient(circle at center, rgba(34, 211, 238, 0.03) 0%, rgba(11, 10, 26, 0.95) 100%)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-default)',
              cursor: isDragging ? 'grabbing' : 'grab',
              userSelect: 'none',
            }}
          >
            {/* SVG Renderer for Nodes and Directed Edges */}
            <svg
              width="100%"
              height="100%"
              viewBox={`0 0 ${width} ${height}`}
              style={{
                width: '100%',
                height: '100%',
                overflow: 'visible',
                transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
                transformOrigin: 'center center',
                transition: isDragging ? 'none' : 'transform 120ms ease-out',
              }}
            >
              <defs>
                {/* Default Arrowhead */}
                <marker
                  id="arrow-default"
                  viewBox="0 0 10 10"
                  refX="8"
                  refY="5"
                  markerWidth="6"
                  markerHeight="6"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 1 L 10 5 L 0 9 z" fill="rgba(161, 161, 181, 0.4)" />
                </marker>
                {/* Active Outbound Arrowhead */}
                <marker
                  id="arrow-outbound"
                  viewBox="0 0 10 10"
                  refX="8"
                  refY="5"
                  markerWidth="7"
                  markerHeight="7"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 1 L 10 5 L 0 9 z" fill="#818CF8" />
                </marker>
                {/* Active Inbound Arrowhead */}
                <marker
                  id="arrow-inbound"
                  viewBox="0 0 10 10"
                  refX="8"
                  refY="5"
                  markerWidth="7"
                  markerHeight="7"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 1 L 10 5 L 0 9 z" fill="#34D399" />
                </marker>
                {/* Glow Filter */}
                <filter id="node-glow" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="3" result="blur" />
                  <feComposite in="SourceGraphic" in2="blur" operator="over" />
                </filter>
              </defs>

              {/* Background Grid Rings in Concentric Mode */}
              {layoutMode === 'concentric' && (
                <g opacity="0.12">
                  <circle cx={width / 2} cy={height / 2} r="130" fill="none" stroke="#22D3EE" strokeDasharray="4 4" />
                  <circle cx={width / 2} cy={height / 2} r="250" fill="none" stroke="#818CF8" strokeDasharray="4 4" />
                  <circle cx={width / 2} cy={height / 2} r="340" fill="none" stroke="#F43F5E" strokeDasharray="4 4" />
                </g>
              )}

              {/* Layer 1: Edges */}
              <g className="graph-edges">
                {edges.map((e, idx) => {
                  const isOutbound = activeFocusId && e.sourcePath === activeFocusId;
                  const isInbound = activeFocusId && e.targetPath === activeFocusId;
                  const isHighlighted = isOutbound || isInbound;
                  const isDimmed = Boolean(activeFocusId && !isHighlighted);

                  let strokeColor = 'rgba(255, 255, 255, 0.14)';
                  let markerId = 'url(#arrow-default)';
                  let strokeWidth = 1.2;

                  if (isOutbound) {
                    strokeColor = '#818CF8';
                    markerId = 'url(#arrow-outbound)';
                    strokeWidth = 2.4;
                  } else if (isInbound) {
                    strokeColor = '#34D399';
                    markerId = 'url(#arrow-inbound)';
                    strokeWidth = 2.4;
                  }

                  return (
                    <path
                      key={`${e.sourcePath}->${e.targetPath}-${idx}`}
                      d={e.d}
                      fill="none"
                      stroke={strokeColor}
                      strokeWidth={strokeWidth}
                      markerEnd={markerId}
                      opacity={isDimmed ? 0.06 : isHighlighted ? 1 : 0.6}
                      style={{ transition: 'opacity 150ms ease, stroke 150ms ease' }}
                    />
                  );
                })}
              </g>

              {/* Layer 2: Nodes */}
              <g className="graph-nodes">
                {nodes.map((n) => {
                  const isSelected = selected?.path === n.path;
                  const isHovered = hoveredNode?.path === n.path;
                  const isFocused = isSelected || isHovered;
                  const isConnected = connectedNodeIds.has(n.path);
                  const isSearchMatch = searchMatches.has(n.path);
                  const isDimmed = activeFocusId && !isConnected && !isSearchMatch;

                  return (
                    <g
                      key={n.id}
                      transform={`translate(${n.x}, ${n.y})`}
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelected(n);
                      }}
                      onMouseEnter={() => setHoveredNode(n)}
                      onMouseLeave={() => setHoveredNode(null)}
                      style={{
                        cursor: 'pointer',
                        opacity: isDimmed ? 0.22 : 1,
                        transition: 'opacity 150ms ease, transform 150ms ease',
                      }}
                    >
                      {/* Central pulsing ring */}
                      {n.isCentral && (
                        <circle
                          r={n.radius + 6}
                          fill="none"
                          stroke={n.color}
                          strokeWidth="1.5"
                          opacity="0.4"
                          strokeDasharray="3 3"
                        />
                      )}

                      {/* Search match highlight ring */}
                      {isSearchMatch && (
                        <circle
                          r={n.radius + 8}
                          fill="none"
                          stroke="#FACC15"
                          strokeWidth="2.5"
                          filter="url(#node-glow)"
                        />
                      )}

                      {/* Selection / Focus Ring */}
                      {isFocused && (
                        <circle
                          r={n.radius + 5}
                          fill="none"
                          stroke={n.color}
                          strokeWidth="2.5"
                          filter="url(#node-glow)"
                        />
                      )}

                      {/* Main Node Circle */}
                      <circle
                        r={n.radius}
                        fill={isFocused ? 'rgba(30, 27, 75, 0.95)' : 'rgba(17, 17, 38, 0.92)'}
                        stroke={n.color}
                        strokeWidth={isFocused ? 2.5 : 1.6}
                      />

                      {/* Node Center Dot or Initial */}
                      <text
                        textAnchor="middle"
                        dy=".35em"
                        fill={n.color}
                        fontSize={Math.max(10, n.radius * 0.6)}
                        fontWeight="600"
                        fontFamily="var(--font-mono)"
                        style={{ pointerEvents: 'none' }}
                      >
                        {n.name.slice(0, 1).toUpperCase()}
                      </text>

                      {/* Node Label Below */}
                      <text
                        textAnchor="middle"
                        y={n.radius + 14}
                        fill={isFocused ? '#FFFFFF' : 'var(--text-secondary)'}
                        fontSize={11}
                        fontFamily="var(--font-sans)"
                        fontWeight={isFocused ? '600' : '400'}
                        style={{
                          pointerEvents: 'none',
                          paintOrder: 'stroke',
                          stroke: 'rgba(11, 10, 26, 0.9)',
                          strokeWidth: 3,
                        }}
                      >
                        {n.name.length > 18 ? `${n.name.slice(0, 16)}…` : n.name}
                      </text>
                    </g>
                  );
                })}
              </g>
            </svg>

            {/* Hover Tooltip Overlay */}
            {hoveredNode && (
              <div
                style={{
                  position: 'absolute',
                  bottom: 16,
                  left: 16,
                  zIndex: 20,
                  background: 'rgba(17, 17, 38, 0.95)',
                  border: `1px solid ${hoveredNode.color}`,
                  borderRadius: 'var(--radius-sm)',
                  padding: '8px 12px',
                  boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
                  pointerEvents: 'none',
                  maxWidth: 320,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: hoveredNode.color,
                    }}
                  />
                  <strong style={{ fontSize: 12, color: 'var(--text-primary)' }}>
                    {hoveredNode.name}
                  </strong>
                  <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                    ({hoveredNode.language})
                  </span>
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', wordBreak: 'break-all' }}>
                  {hoveredNode.path}
                </div>
                <div style={{ display: 'flex', gap: 12, marginTop: 6, fontSize: 11 }}>
                  <span>
                    <b style={{ color: '#34D399' }}>{hoveredNode.inbound_count}</b> in
                  </span>
                  <span>
                    <b style={{ color: '#818CF8' }}>{hoveredNode.outbound_count}</b> out
                  </span>
                  <span>
                    <b style={{ color: '#22D3EE' }}>{hoveredNode.symbol_count}</b> symbols
                  </span>
                </div>
              </div>
            )}
          </div>
        </Card>

        {/* Central Files Ranking */}
        <Card>
          <div className="card-title">
            <div>
              <span className="eyebrow">CENTRALITY RANKINGS</span>
              <h2>Highest Impact Files</h2>
            </div>
            <Icon.Spark style={{ width: 16, height: 16, color: 'var(--accent-violet)' }} />
          </div>

          <div className="file-list">
            {overview.top_files_by_centrality &&
              overview.top_files_by_centrality.slice(0, 10).map((f: any, idx: number) => (
                <button
                  key={f.path || idx}
                  type="button"
                  className="file-row"
                  onClick={() => {
                    const match = nodes.find((n) => n.path === f.path) || {
                      path: f.path,
                      inbound_count: f.inbound,
                      outbound_count: f.outbound,
                      symbol_count: f.symbols || 0,
                    };
                    setSelected(match);
                  }}
                >
                  <span className="file-rank">#{idx + 1}</span>
                  <div className="file-info">
                    <b>{f.path}</b>
                    <small>
                      {f.inbound} inbound imports · {f.outbound} outbound
                    </small>
                  </div>
                  <Icon.Chevron />
                </button>
              ))}
          </div>
        </Card>
      </div>

      {/* Slide-over Detail Drawer */}
      {selected && (
        <div className="drawer" onClick={() => setSelected(null)}>
          <div
            className="drawer-inner"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              className="drawer-close"
              onClick={() => setSelected(null)}
              aria-label="Close drawer"
            >
              <Icon.Close />
            </button>

            <span className="eyebrow">FILE NODE DETAILS</span>
            <h2 style={{ marginTop: 12, wordBreak: 'break-all', fontSize: 20 }}>
              {selected.path}
            </h2>

            <div className="drawer-metrics">
              <Metric
                label="Inbound Imports"
                value={selected.inbound_count || 0}
                accent="cyan"
              />
              <Metric
                label="Outbound Imports"
                value={selected.outbound_count || 0}
                accent="purple"
              />
              <Metric
                label="AST Symbols"
                value={selected.symbol_count || 0}
                accent="emerald"
              />
            </div>

            <p style={{ fontSize: 13.5, lineHeight: 1.7, color: 'var(--text-secondary)' }}>
              This node represents an analyzed source file in the repository topology. High inbound dependency counts indicate core modules or shared utilities, while high outbound links identify coordinating services.
            </p>

            {/* Inbound & Outbound Connections Lists */}
            <div style={{ marginTop: 20 }}>
              <strong style={{ fontSize: 13, color: 'var(--text-primary)', display: 'block', marginBottom: 8 }}>
                Connected Imports
              </strong>

              {edges.filter((e) => e.sourcePath === selected.path || e.targetPath === selected.path).length === 0 ? (
                <div style={{ fontSize: 12, color: 'var(--text-muted)', fontStyle: 'italic' }}>
                  No direct internal imports resolved for this module.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 220, overflowY: 'auto' }}>
                  {edges
                    .filter((e) => e.sourcePath === selected.path)
                    .map((e, i) => (
                      <div
                        key={`out-${i}`}
                        style={{
                          fontSize: 12,
                          padding: '6px 8px',
                          background: 'rgba(129, 140, 248, 0.08)',
                          borderRadius: 6,
                          border: '1px solid rgba(129, 140, 248, 0.2)',
                          color: '#818CF8',
                        }}
                      >
                        → Imports <b>{e.targetPath}</b>
                      </div>
                    ))}
                  {edges
                    .filter((e) => e.targetPath === selected.path)
                    .map((e, i) => (
                      <div
                        key={`in-${i}`}
                        style={{
                          fontSize: 12,
                          padding: '6px 8px',
                          background: 'rgba(52, 211, 153, 0.08)',
                          borderRadius: 6,
                          border: '1px solid rgba(52, 211, 153, 0.2)',
                          color: '#34D399',
                        }}
                      >
                        ← Imported by <b>{e.sourcePath}</b>
                      </div>
                    ))}
                </div>
              )}
            </div>

            <div style={{ marginTop: 24, paddingTop: 20, borderTop: '1px solid var(--border-default)' }}>
              <button
                type="button"
                className="primary"
                style={{ width: '100%' }}
                onClick={() => setSelected(null)}
              >
                Close Inspector
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
