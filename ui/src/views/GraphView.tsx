import { useEffect, useMemo, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Network } from "lucide-react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import type { Graph } from "@/types"
import { Button } from "@/components/ui/button"

interface Node {
  id: string
  title: string
  type: string
  x: number
  y: number
}

const W = 1000
const H = 700

const TYPE_COLOR: Record<string, string> = {
  concept: "#2bb673",
  entity: "#a855f7",
  synthesis: "#06b6d4",
  decision: "#e8873a",
  research: "#3b82f6",
  project: "#eab308",
}
function colorFor(type: string) {
  return TYPE_COLOR[type] ?? "#94a3b8"
}

/** Run a few hundred force-sim iterations to lay out the graph deterministically. */
function layout(graph: Graph): Node[] {
  const nodes: Node[] = graph.nodes.map((n, i) => {
    const angle = (i / Math.max(1, graph.nodes.length)) * Math.PI * 2
    return {
      ...n,
      x: W / 2 + Math.cos(angle) * 250,
      y: H / 2 + Math.sin(angle) * 250,
    }
  })
  const index = new Map<string, number>()
  nodes.forEach((n, i) => {
    index.set(n.id, i)
    index.set(n.title.toLowerCase(), i)
  })
  const idx = (key: string) =>
    index.get(key) ?? index.get(key.toLowerCase())
  const edges = graph.edges
    .map((e) => [idx(e.from), idx(e.to)] as const)
    .filter((e): e is readonly [number, number] => e[0] != null && e[1] != null)

  const REPULSION = 12000
  const SPRING = 0.02
  const SPRING_LEN = 120
  const CENTER = 0.008

  for (let iter = 0; iter < 350; iter++) {
    const fx = new Array(nodes.length).fill(0)
    const fy = new Array(nodes.length).fill(0)
    // repulsion
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        let dx = nodes[i].x - nodes[j].x
        let dy = nodes[i].y - nodes[j].y
        const d2 = dx * dx + dy * dy || 0.01
        const f = REPULSION / d2
        const d = Math.sqrt(d2)
        dx /= d
        dy /= d
        fx[i] += dx * f
        fy[i] += dy * f
        fx[j] -= dx * f
        fy[j] -= dy * f
      }
    }
    // springs
    for (const [a, b] of edges) {
      const dx = nodes[b].x - nodes[a].x
      const dy = nodes[b].y - nodes[a].y
      const d = Math.sqrt(dx * dx + dy * dy) || 0.01
      const f = (d - SPRING_LEN) * SPRING
      fx[a] += (dx / d) * f
      fy[a] += (dy / d) * f
      fx[b] -= (dx / d) * f
      fy[b] -= (dy / d) * f
    }
    // centering + integrate
    for (let i = 0; i < nodes.length; i++) {
      fx[i] += (W / 2 - nodes[i].x) * CENTER
      fy[i] += (H / 2 - nodes[i].y) * CENTER
      nodes[i].x += Math.max(-15, Math.min(15, fx[i]))
      nodes[i].y += Math.max(-15, Math.min(15, fy[i]))
    }
  }
  return nodes
}

export function GraphView() {
  const navigate = useNavigate()
  const [graph, setGraph] = useState<Graph | null>(null)
  const [nodes, setNodes] = useState<Node[]>([])
  const [selected, setSelected] = useState<Node | null>(null)
  const [filter, setFilter] = useState<string | null>(null)
  const dragRef = useRef<{ id: string; ox: number; oy: number } | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    api
      .graph()
      .then((g) => {
        setGraph(g)
        setNodes(layout(g))
      })
      .catch((e) => toast.error((e as Error).message))
  }, [])

  const types = useMemo(
    () => [...new Set(nodes.map((n) => n.type))],
    [nodes],
  )
  // Edges may reference a node by path (id) or by title (raw wikilink target),
  // so index by both for resolution.
  const nodePos = useMemo(() => {
    const m = new Map<string, Node>()
    for (const n of nodes) {
      m.set(n.id, n)
      m.set(n.title.toLowerCase(), n)
    }
    return m
  }, [nodes])
  const resolve = (key: string) =>
    nodePos.get(key) ?? nodePos.get(key.toLowerCase())

  function toSvg(e: React.PointerEvent): { x: number; y: number } {
    const svg = svgRef.current!
    const rect = svg.getBoundingClientRect()
    return {
      x: ((e.clientX - rect.left) / rect.width) * W,
      y: ((e.clientY - rect.top) / rect.height) * H,
    }
  }

  return (
    <div className="relative flex-1 overflow-hidden">
      {/* controls */}
      <div className="absolute left-4 top-4 z-10 flex items-center gap-2">
        <h1 className="flex items-center gap-1.5 rounded-md border bg-card px-2.5 py-1.5 font-display text-[13px] font-semibold shadow-sm">
          <Network className="size-4 text-primary" /> Graph
        </h1>
        <div className="flex gap-1 rounded-md border bg-card p-1 shadow-sm">
          <button
            onClick={() => setFilter(null)}
            className={`rounded px-2 py-0.5 text-[11px] ${!filter ? "bg-secondary font-medium" : "text-muted-foreground"}`}
          >
            all
          </button>
          {types.map((t) => (
            <button
              key={t}
              onClick={() => setFilter(t)}
              className={`rounded px-2 py-0.5 text-[11px] ${filter === t ? "bg-secondary font-medium" : "text-muted-foreground"}`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {graph && graph.nodes.length === 0 && (
        <div className="flex h-full items-center justify-center text-[13px] text-muted-foreground">
          No pages to graph yet.
        </div>
      )}

      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="h-full w-full"
        onPointerMove={(e) => {
          if (!dragRef.current) return
          const { x, y } = toSvg(e)
          const id = dragRef.current.id
          setNodes((ns) => ns.map((n) => (n.id === id ? { ...n, x, y } : n)))
        }}
        onPointerUp={() => (dragRef.current = null)}
        onPointerLeave={() => (dragRef.current = null)}
      >
        {/* edges */}
        {graph?.edges.map((e, i) => {
          const a = resolve(e.from)
          const b = resolve(e.to)
          if (!a || !b) return null
          const dim = filter && a.type !== filter && b.type !== filter
          return (
            <line
              key={i}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke="currentColor"
              className="text-border"
              strokeWidth={1}
              opacity={dim ? 0.15 : 0.5}
            />
          )
        })}
        {/* nodes */}
        {nodes.map((n) => {
          const dim = filter && n.type !== filter
          return (
            <g
              key={n.id}
              transform={`translate(${n.x},${n.y})`}
              opacity={dim ? 0.25 : 1}
              className="cursor-pointer"
              onPointerDown={(e) => {
                e.preventDefault()
                dragRef.current = { id: n.id, ox: n.x, oy: n.y }
                setSelected(n)
              }}
              onDoubleClick={() =>
                navigate(`/wiki?q=${encodeURIComponent(n.title)}`)
              }
            >
              <circle
                r={selected?.id === n.id ? 9 : 6}
                fill={colorFor(n.type)}
                stroke={selected?.id === n.id ? "var(--foreground)" : "white"}
                strokeWidth={selected?.id === n.id ? 2 : 1.5}
              />
              <text
                x={10}
                y={4}
                className="fill-foreground"
                style={{ fontSize: 11, fontFamily: "var(--font-body)" }}
              >
                {n.title}
              </text>
            </g>
          )
        })}
      </svg>

      {/* side panel */}
      {selected && (
        <div className="absolute right-4 top-4 z-10 w-[260px] rounded-lg border bg-card p-4 shadow-md">
          <div className="flex items-center gap-2">
            <span
              className="size-3 rounded-full"
              style={{ background: colorFor(selected.type) }}
            />
            <span className="font-display text-[14px] font-semibold">
              {selected.title}
            </span>
          </div>
          <div className="mt-1 text-[12px] text-muted-foreground">
            {selected.type}
          </div>
          <Button
            size="sm"
            className="mt-3 w-full"
            onClick={() => navigate(`/wiki?q=${encodeURIComponent(selected.title)}`)}
          >
            Open page →
          </Button>
        </div>
      )}
    </div>
  )
}
